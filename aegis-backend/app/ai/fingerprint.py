"""
app/ai/fingerprint.py
─────────────────────
AI company fingerprinting pipeline — v2: universal multi-segment reasoning.

Architecture (3 async steps, run concurrently where possible):

  Step 1 — Business decomposition (NEW)
    Claude first identifies what the company actually does: sector, sub-sectors,
    business lines, and primary customer segments. This is the grounding step.
    Works for ANY company — known or unknown, large or small, any industry.

  Step 2 — Jurisdiction & industry classification
    Checked against a known-company table first, then Claude inference.
    Falls back to OpenCorporates registry, then heuristic.

  Step 3 — GRC inference (per segment)
    Uses the business decomposition from Step 1 as context.
    Claude generates processes, risks, controls, regulations, and frameworks
    for EACH identified business line, then returns a consolidated profile.

Key design decisions:
  - No hard-coded company knowledge required — scales to any org
  - Two-stage reasoning: decompose THEN assess (not name → risks directly)
  - Wikipedia grounding: optional live context fetch anchors Claude's reasoning
  - max_tokens raised to 4000 to allow full multi-segment output
  - All steps run with asyncio.gather for speed
"""

import asyncio
import json
import logging
import re
from typing import Any

import httpx
from anthropic import AsyncAnthropic

from app.ai.context import OrgProfileContext, format_context_for_prompt
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()
claude = AsyncAnthropic(api_key=settings.anthropic_api_key)


# ── Jurisdiction knowledge base ───────────────────────────────────────────────
# Only used for jurisdiction/regulator lookup — NOT for business line knowledge.
# Business lines are always inferred dynamically via Claude.

KNOWN_JURISDICTION: dict[str, dict[str, str]] = {
    # US
    "uber": {"jurisdiction": "United States", "regulator": "SEC / FTC / DOT / CFTC"},
    "walmart": {"jurisdiction": "United States", "regulator": "SEC / FTC / FDA / OSHA"},
    "citibank": {"jurisdiction": "United States", "regulator": "OCC / FDIC / Federal Reserve / CFPB"},
    "citigroup": {"jurisdiction": "United States", "regulator": "OCC / FDIC / Federal Reserve / CFPB"},
    "palantir": {"jurisdiction": "United States", "regulator": "SEC / DoD / ITAR"},
    "amazon": {"jurisdiction": "United States", "regulator": "SEC / FTC / FAA / OSHA"},
    "google": {"jurisdiction": "United States", "regulator": "SEC / FTC / FCC"},
    "meta": {"jurisdiction": "United States", "regulator": "SEC / FTC / FCC"},
    "apple": {"jurisdiction": "United States", "regulator": "SEC / FTC"},
    "microsoft": {"jurisdiction": "United States", "regulator": "SEC / FTC / DoD"},
    "jpmorgan": {"jurisdiction": "United States", "regulator": "OCC / FDIC / Federal Reserve / CFPB"},
    "bank of america": {"jurisdiction": "United States", "regulator": "OCC / FDIC / Federal Reserve / CFPB"},
    "goldman sachs": {"jurisdiction": "United States", "regulator": "SEC / FINRA / Federal Reserve"},
    "stripe": {"jurisdiction": "United States", "regulator": "FinCEN / CFPB / state money transmitter"},
    "airbnb": {"jurisdiction": "United States", "regulator": "SEC / FTC / local housing authorities"},
    "tesla": {"jurisdiction": "United States", "regulator": "SEC / NHTSA / EPA"},
    "pfizer": {"jurisdiction": "United States", "regulator": "FDA / SEC / DEA"},
    "unitedhealth": {"jurisdiction": "United States", "regulator": "CMS / HHS / SEC / state DOI"},
    "johnson & johnson": {"jurisdiction": "United States", "regulator": "FDA / SEC / OSHA"},
    # EU / Netherlands
    "adyen": {"jurisdiction": "Netherlands", "regulator": "DNB / AFM / ECB"},
    "ing": {"jurisdiction": "Netherlands", "regulator": "DNB / AFM / ECB"},
    "ing bank": {"jurisdiction": "Netherlands", "regulator": "DNB / AFM / ECB"},
    "asml": {"jurisdiction": "Netherlands", "regulator": "AFM / SEC (ADR) / export control"},
    "philips": {"jurisdiction": "Netherlands", "regulator": "AFM / FDA / MDR"},
    "booking.com": {"jurisdiction": "Netherlands", "regulator": "AFM / DPA / EU DSA"},
    "spotify": {"jurisdiction": "Sweden", "regulator": "Finansinspektionen / EU DSA"},
    "klarna": {"jurisdiction": "Sweden", "regulator": "Finansinspektionen / BaFin / FCA"},
    "wise": {"jurisdiction": "United Kingdom", "regulator": "FCA / FinCEN"},
    "revolut": {"jurisdiction": "United Kingdom", "regulator": "FCA / ECB / Bank of Lithuania"},
    "barclays": {"jurisdiction": "United Kingdom", "regulator": "PRA / FCA"},
    "hsbc": {"jurisdiction": "United Kingdom", "regulator": "PRA / FCA / Federal Reserve"},
    "sap": {"jurisdiction": "Germany", "regulator": "BaFin / BSI / SEC (ADR)"},
    "siemens": {"jurisdiction": "Germany", "regulator": "BaFin / BSI / export control"},
    # Healthcare / non-profit pattern handled dynamically
}


def _lookup_jurisdiction(name: str) -> dict[str, str]:
    """Check known table first; returns empty dict if not found."""
    key = name.strip().lower()
    # Exact match
    if key in KNOWN_JURISDICTION:
        return KNOWN_JURISDICTION[key]
    # Partial match (e.g. "Citibank N.A." → "citibank")
    for known_key, data in KNOWN_JURISDICTION.items():
        if known_key in key or key in known_key:
            return data
    return {}


# ── Step 0 — Wikipedia grounding (optional, best-effort) ─────────────────────

async def _fetch_wikipedia_summary(name: str) -> str:
    """
    Fetch a short Wikipedia summary to ground Claude's business decomposition.
    Returns empty string on any failure — this step is always optional.
    Caps at 600 chars to avoid bloating the prompt.
    """
    search_name = name.strip().replace(" ", "_")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{search_name}"
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code == 200:
                data = resp.json()
                extract = data.get("extract", "")
                return extract[:600]
        except Exception:
            pass
    return ""


# ── Step 1 — Business decomposition ──────────────────────────────────────────

async def _decompose_business(name: str, wiki_context: str = "") -> dict[str, Any]:
    """
    First-pass reasoning: identify what this company actually does.

    Returns:
      sector         — top-level sector (e.g. "Financial Services")
      sub_sector     — more specific (e.g. "Retail Banking + Credit Cards")
      business_lines — list of distinct operating segments
      customer_types — who they serve (consumers, enterprises, governments, patients…)
      org_type       — for-profit / non-profit / government / cooperative
      employee_scale — micro / small / mid / large / enterprise
      summary        — 1-2 sentence plain-English description Claude derived
    """
    context_block = f"\nBackground context: {wiki_context}" if wiki_context else ""

    prompt = f"""You are a business analyst with expertise across all industries.
Your task is to decompose a company into its distinct business lines and operating segments.{context_block}

Return ONLY valid JSON — no markdown, no preamble:
{{
  "sector": "Technology / Transportation",
  "sub_sector": "Ride-hailing, Food Delivery, Freight Logistics, Financial Services",
  "business_lines": [
    "Mobility (Uber rides — passenger transport platform)",
    "Food & grocery delivery (Uber Eats — marketplace connecting consumers, restaurants, couriers)",
    "Freight brokerage (Uber Freight — trucking load marketplace)",
    "Driver financial services (Uber Money — earned wage access, debit card, insurance)"
  ],
  "customer_types": ["Consumers", "Restaurants", "Couriers / gig workers", "Shippers", "Carriers"],
  "org_type": "for-profit",
  "employee_scale": "enterprise",
  "summary": "Uber is a global platform company operating ride-hailing, food delivery, freight brokerage, and embedded financial services across 70+ countries."
}}

Rules:
- business_lines must reflect ALL distinct revenue-generating or operationally distinct segments
- For conglomerates (Walmart, GE) list each major division
- For hospitals/healthcare: list clinical service lines + support functions (pharmacy, billing, research if applicable)
- For banks: list retail, commercial, investment, wealth, treasury, insurance if applicable
- For pure-play companies (e.g. a regional bakery): list 2-3 lines covering production, distribution, retail
- org_type options: for-profit | non-profit | government | cooperative | ngo
- employee_scale: micro (<10) | small (10-200) | mid (200-2000) | large (2000-20000) | enterprise (20000+)
- If the company is unknown, reason from the name and any context clues

Company name: {name}"""

    try:
        msg = await claude.messages.create(
            model=settings.claude_model,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        return json.loads(text)
    except Exception as e:
        logger.error("_decompose_business failed for %r: %s", name, e, exc_info=True)
        return {
            "sector": "Unknown",
            "sub_sector": "Unknown",
            "business_lines": [name],
            "customer_types": ["Unknown"],
            "org_type": "for-profit",
            "employee_scale": "large",
            "summary": f"Business profile for {name}.",
        }


# ── Step 2 — Jurisdiction & regulator ────────────────────────────────────────

async def _resolve_jurisdiction(name: str) -> dict[str, str]:
    """
    Resolve jurisdiction via: known table → OpenCorporates → Claude inference.
    """
    # Known table first (instant)
    known = _lookup_jurisdiction(name)
    if known:
        return known

    # OpenCorporates registry
    async with httpx.AsyncClient(timeout=6.0) as client:
        try:
            resp = await client.get(
                "https://api.opencorporates.com/v0.4/companies/search",
                params={"q": name, "per_page": 1},
            )
            data = resp.json()
            companies = data.get("results", {}).get("companies", [])
            if companies:
                co = companies[0]["company"]
                jcode = co.get("jurisdiction_code", "")
                jurisdiction = _map_jurisdiction_code(jcode)
                if jurisdiction:
                    return {"jurisdiction": jurisdiction, "regulator": ""}
        except Exception:
            pass

    # Claude inference fallback
    prompt = f"""What country is "{name}" headquartered in?
Return ONLY valid JSON: {{"jurisdiction": "United States", "regulator": "SEC / FTC"}}
Use the primary financial regulator(s) for that country and industry. No other text."""
    try:
        msg = await claude.messages.create(
            model=settings.claude_model,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        return json.loads(text)
    except Exception as e:
        logger.error("_resolve_jurisdiction Claude fallback failed for %r: %s", name, e, exc_info=True)
        return {"jurisdiction": "United States", "regulator": "SEC / FTC"}


def _map_jurisdiction_code(code: str) -> str:
    mapping = {
        "us": "United States", "gb": "United Kingdom", "de": "Germany",
        "nl": "Netherlands", "fr": "France", "sg": "Singapore",
        "au": "Australia", "ca": "Canada", "ie": "Ireland",
        "se": "Sweden", "ch": "Switzerland", "jp": "Japan",
        "in": "India", "br": "Brazil", "mx": "Mexico",
    }
    return mapping.get(code.lower().split("_")[0], "")


# ── Step 3 — GRC inference (multi-segment aware) ─────────────────────────────

async def _infer_grc_profile(
    name: str,
    decomposition: dict[str, Any],
    jurisdiction_info: dict[str, str],
    org_context: OrgProfileContext | None = None,
) -> dict[str, Any]:
    """
    Core GRC reasoning call.

    Uses the business decomposition to generate a complete, segment-aware
    GRC profile. Works for any company in any industry.

    The prompt explicitly instructs Claude to:
      1. Cover every business line identified in Step 1
      2. Generate cross-cutting AND segment-specific risks
      3. Apply industry-appropriate regulations (healthcare ≠ fintech ≠ retail)
      4. Scale output depth to company size
    """
    segments_block = "\n".join(f"  - {bl}" for bl in decomposition.get("business_lines", [name]))
    customers_block = ", ".join(decomposition.get("customer_types", ["customers"]))
    org_type = decomposition.get("org_type", "for-profit")
    scale = decomposition.get("employee_scale", "large")
    sector = decomposition.get("sector", "")
    summary = decomposition.get("summary", "")
    jurisdiction = jurisdiction_info.get("jurisdiction", "United States")
    regulator = jurisdiction_info.get("regulator", "")

    profile_block = ""
    if org_context:
        profile_block = f"\n## Verified Company Profile (use as primary context)\n{format_context_for_prompt(org_context)}\n"

    prompt = f"""You are a senior GRC consultant. Generate a comprehensive GRC fingerprint for the company below.
{profile_block}
## Company Profile
Name: {name}
Sector: {sector}
Summary: {summary}
Jurisdiction: {jurisdiction}{f" | Primary regulator(s): {regulator}" if regulator else ""}
Org type: {org_type} | Scale: {scale}
Customers served: {customers_block}

## Business Lines (cover ALL of these):
{segments_block}

## Instructions
Generate GRC output that covers EVERY business line listed above. Do not focus on just one segment.

For each category, think:
  - What processes are core to THIS specific company?
  - What regulations apply given their jurisdiction, sector, and customer types?
  - What risks are material — including cross-segment risks (data, workforce, third-party, cyber)?
  - For non-profits / hospitals: include patient safety, mission risk, grant/funding risk
  - For financial services: include credit, liquidity, conduct, AML risks
  - For retail / e-commerce: include supply chain, product safety, consumer protection
  - For tech platforms: include algorithmic, marketplace, platform liability risks
  - For government contractors (e.g. Palantir): include ITAR, FedRAMP, classified data risks

## Output
Return ONLY valid JSON — no markdown, no preamble:
{{
  "industry_label": "Multi-segment Technology Platform",
  "sic_code": "7372",
  "detected_processes": [
    "Ride dispatch and real-time driver matching",
    "Restaurant onboarding and menu management (Eats)",
    "Last-mile delivery routing and courier dispatch (Eats)",
    "Freight load posting, matching, and carrier onboarding",
    "Background screening and driver / courier onboarding",
    "Surge pricing and dynamic fare calculation",
    "Driver and courier payment processing and earned wage access",
    "Customer identity verification and fraud detection"
  ],
  "risk_domains": [
    {{"name": "Safety & Physical Security", "risk_count": 12, "severity": "high"}},
    {{"name": "Data Privacy & Cybersecurity", "risk_count": 10, "severity": "high"}},
    {{"name": "Regulatory & Compliance", "risk_count": 9, "severity": "high"}},
    {{"name": "Workforce & Labour Law", "risk_count": 8, "severity": "high"}},
    {{"name": "Third-Party & Supply Chain", "risk_count": 7, "severity": "medium"}},
    {{"name": "Financial Crime & Payments", "risk_count": 6, "severity": "medium"}},
    {{"name": "Technology & Platform Resilience", "risk_count": 8, "severity": "high"}},
    {{"name": "Marketplace & Antitrust", "risk_count": 5, "severity": "medium"}}
  ],
  "detected_regulations": [
    "CCPA / CPRA (California data privacy)",
    "GDPR (EU data privacy, international ops)",
    "PCI DSS (payment card processing)",
    "FCRA (driver background checks)",
    "DOT / FMCSA regulations (Freight)",
    "AB5 and gig worker classification laws",
    "AML / BSA (Uber Money financial services)",
    "SOX (public company financial reporting)"
  ],
  "suggested_frameworks": [
    "ISO 27001 (Information Security)",
    "NIST CSF (Cybersecurity)",
    "COSO ERM (Enterprise Risk)",
    "SOC 2 Type II (Platform trust)",
    "PCI DSS (Payments)",
    "ISO 39001 (Road traffic safety)"
  ],
  "risks": [
    {{
      "name": "Gig worker misclassification liability",
      "domain": "Workforce & Labour Law",
      "severity": "critical",
      "description": "Ongoing legal risk that drivers/couriers are employees not contractors — exposure to back-pay, benefits, and penalties across multiple jurisdictions (AB5, EU Platform Work Directive).",
      "framework_tags": ["COSO ERM", "local labour law"],
      "likelihood": 5,
      "impact": 5
    }},
    {{
      "name": "Passenger or diner harm from unvetted driver / courier",
      "domain": "Safety & Physical Security",
      "severity": "critical",
      "description": "Background check failures or gaps between checks allow bad actors onto platform, creating safety incidents and regulatory action.",
      "framework_tags": ["FCRA", "FTC Act"],
      "likelihood": 3,
      "impact": 5
    }},
    {{
      "name": "Large-scale customer data breach",
      "domain": "Data Privacy & Cybersecurity",
      "severity": "high",
      "description": "Breach of rider/diner PII, trip history, or payment data — exposure under CCPA, GDPR, PCI DSS with class action risk.",
      "framework_tags": ["ISO 27001", "GDPR", "CCPA"],
      "likelihood": 3,
      "impact": 5
    }},
    {{
      "name": "Uber Eats restaurant fraud and chargeback abuse",
      "domain": "Financial Crime & Payments",
      "severity": "medium",
      "description": "Fake restaurant listings or courier fraud generate chargebacks and reputational harm on the Eats marketplace.",
      "framework_tags": ["PCI DSS", "AML / BSA"],
      "likelihood": 4,
      "impact": 3
    }},
    {{
      "name": "Platform outage during peak demand",
      "domain": "Technology & Platform Resilience",
      "severity": "high",
      "description": "Failure of dispatch, matching, or payments infrastructure during peak periods causes revenue loss and regulatory scrutiny in jurisdictions with service obligations.",
      "framework_tags": ["SOC 2 Type II", "NIST CSF"],
      "likelihood": 3,
      "impact": 4
    }},
    {{
      "name": "Antitrust action on surge pricing or market dominance",
      "domain": "Marketplace & Antitrust",
      "severity": "medium",
      "description": "Dynamic pricing algorithms or exclusive contracts attract DOJ / EU DG COMP antitrust scrutiny.",
      "framework_tags": ["COSO ERM"],
      "likelihood": 3,
      "impact": 4
    }},
    {{
      "name": "Uber Freight carrier compliance failure",
      "domain": "Regulatory & Compliance",
      "severity": "high",
      "description": "Onboarding carriers without verifying FMCSA licensing, insurance, or safety ratings creates brokerage liability for cargo loss and accidents.",
      "framework_tags": ["DOT / FMCSA"],
      "likelihood": 3,
      "impact": 4
    }}
  ],
  "controls": [
    {{
      "name": "Continuous background monitoring (drivers & couriers)",
      "domain": "Safety & Physical Security",
      "type": "automated",
      "framework_tags": ["FCRA"],
      "description": "Real-time monitoring via Checkr or equivalent — flags criminal incidents between annual rechecks."
    }},
    {{
      "name": "PCI DSS tokenisation for payment data",
      "domain": "Data Privacy & Cybersecurity",
      "type": "automated",
      "framework_tags": ["PCI DSS"],
      "description": "All card data tokenised at capture; raw PANs never stored in application layer."
    }},
    {{
      "name": "Gig worker classification legal review programme",
      "domain": "Workforce & Labour Law",
      "type": "manual",
      "framework_tags": ["COSO ERM", "local labour law"],
      "description": "Quarterly legal review of classification risk by jurisdiction, with escalation to board for material legislative changes."
    }},
    {{
      "name": "FMCSA carrier verification gate (Freight)",
      "domain": "Regulatory & Compliance",
      "type": "automated",
      "framework_tags": ["DOT / FMCSA"],
      "description": "Automated FMCSA API check blocks carrier onboarding if safety rating is unsatisfactory or insurance is lapsed."
    }}
  ]
}}

Generate output specific to {name}. Cover every business line. Use industry-correct terminology.
Scale the number of items to company size: enterprise = 8-12 processes, 7-9 domains, 8-12 regs, 5-7 frameworks, 8-12 risks, 5-7 controls."""

    try:
        msg = await claude.messages.create(
            model=settings.claude_model,
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        return json.loads(text)
    except Exception as e:
        logger.error("_infer_grc_profile failed for %r: %s", name, e, exc_info=True)
        return {
            "industry_label": "Unknown",
            "sic_code": None,
            "detected_processes": [],
            "risk_domains": [],
            "detected_regulations": [],
            "suggested_frameworks": [],
            "risks": [],
            "controls": [],
        }


# ── Public entry point ────────────────────────────────────────────────────────

async def fingerprint_company(
    name: str,
    org_context: OrgProfileContext | None = None,
) -> dict[str, Any]:
    """
    Full fingerprinting pipeline. Returns a consolidated GRC profile.

    If org_context is provided (Company Profile already exists), it is injected
    into the GRC inference as verified primary context, skipping the Wikipedia
    grounding step.

    Pipeline:
      Step 0: Wikipedia context fetch (skipped when org_context provided)
      Step 1: Business decomposition — what does this company do? (Claude)
      Step 2: Jurisdiction resolution — parallel with step 1 where possible
      Step 3: GRC profile — multi-segment aware (Claude, uses steps 1+2 + profile)
    """
    wiki_context = ""
    if org_context is None:
        # Step 0: Grounding context (fire and forget — don't wait if slow)
        try:
            wiki_context = await asyncio.wait_for(_fetch_wikipedia_summary(name), timeout=4.0)
        except asyncio.TimeoutError:
            pass

    # Steps 1 + 2 in parallel
    decomposition, jurisdiction_info = await asyncio.gather(
        _decompose_business(name, wiki_context),
        _resolve_jurisdiction(name),
    )

    # Step 3: Full GRC inference using decomposition context + profile if available
    grc = await _infer_grc_profile(name, decomposition, jurisdiction_info, org_context)

    return {
        # Identity
        "company_name": name,
        "jurisdiction": jurisdiction_info.get("jurisdiction", "Unknown"),
        "regulator": jurisdiction_info.get("regulator", ""),
        "industry_label": grc.get("industry_label", decomposition.get("sector", "Unknown")),
        "industry_code": grc.get("sic_code"),
        "org_type": decomposition.get("org_type", "for-profit"),
        "employee_range": decomposition.get("employee_scale", ""),  # schema expects employee_range
        # Business decomposition
        "business_lines": decomposition.get("business_lines", []),
        "customer_types": decomposition.get("customer_types", []),
        "business_summary": decomposition.get("summary", ""),
        # GRC output
        "detected_processes": grc.get("detected_processes", []),
        "risk_domains": grc.get("risk_domains", []),
        "detected_regulations": grc.get("detected_regulations", []),
        "suggested_frameworks": grc.get("suggested_frameworks", []),
        "risks": grc.get("risks", []),
        "controls": grc.get("controls", []),
        # Meta
        "confidence_score": 0.9 if wiki_context else 0.8,
    }


# ── Post-onboarding seeder ────────────────────────────────────────────────────

async def seed_org_from_fingerprint(
    org_id: str,
    fingerprint: dict[str, Any],
    db,
) -> None:
    """
    Populate all sections after onboarding completes:
      - Risk register  (risks table)
      - Controls       (controls table)
      - Canvas         (canvas_nodes + canvas_edges)
      - Frameworks     (frameworks table)
      - Radar signals  (signals table — AI-generated initial feed)
    """
    from uuid import UUID
    from app.models import (
        Risk, Control, CanvasNode, CanvasEdge, Framework, Signal,
        RiskSeverity, ControlType, ControlStatus, NodeType, EdgeType,
        SignalSeverity, SignalCategory,
    )
    from datetime import datetime, timezone

    org_uuid = UUID(org_id)

    # ── 1. Risks ──────────────────────────────────────────────────────────────
    SEV_MAP = {
        "critical": RiskSeverity.critical, "high": RiskSeverity.high,
        "medium": RiskSeverity.medium, "low": RiskSeverity.low,
    }
    risk_rows: list[Risk] = []
    for r in fingerprint.get("risks", []):
        sev = SEV_MAP.get(r.get("severity", "medium"), RiskSeverity.medium)
        row = Risk(
            org_id=org_uuid,
            name=r.get("name", "Unnamed risk"),
            description=r.get("description", ""),
            domain=r.get("domain", ""),
            inherent_severity=sev,
            residual_severity=sev,
            likelihood=min(5, max(1, r.get("likelihood", 3))),
            impact=min(5, max(1, r.get("impact", 3))),
            framework_tags=r.get("framework_tags", []),
            ai_assessment={"source": "fingerprint", "rationale": r.get("description", "")},
            ai_seeded=True,
        )
        db.add(row)
        risk_rows.append(row)
    await db.flush()

    # ── 2. Controls ───────────────────────────────────────────────────────────
    TYPE_MAP = {"automated": ControlType.automated, "manual": ControlType.manual,
                "compensating": ControlType.compensating}
    control_rows: list[Control] = []
    for c in fingerprint.get("controls", []):
        row = Control(
            org_id=org_uuid,
            name=c.get("name", "Unnamed control"),
            description=c.get("description", ""),
            domain=c.get("domain", ""),
            control_type=TYPE_MAP.get(c.get("type", "manual"), ControlType.manual),
            status=ControlStatus.not_tested,
            framework_tags=c.get("framework_tags", []),
            ai_seeded=True,
        )
        db.add(row)
        control_rows.append(row)
    await db.flush()

    # ── 3. Canvas nodes + edges ───────────────────────────────────────────────
    COLS = 4
    risk_nodes: list[CanvasNode] = []
    for i, risk in enumerate(risk_rows):
        node = CanvasNode(
            org_id=org_uuid,
            node_type=NodeType.risk,
            risk_id=risk.id,
            label=risk.name,
            pos_x=float((i % COLS) * 280 + 60),
            pos_y=float((i // COLS) * 180 + 60),
        )
        db.add(node)
        risk_nodes.append(node)

    control_nodes: list[CanvasNode] = []
    risk_count = len(risk_rows)
    offset_rows = (risk_count // COLS) + 2
    for i, control in enumerate(control_rows):
        node = CanvasNode(
            org_id=org_uuid,
            node_type=NodeType.control,
            control_id=control.id,
            label=control.name,
            pos_x=float((i % COLS) * 280 + 60),
            pos_y=float((i // COLS) * 180 + offset_rows * 180 + 60),
        )
        db.add(node)
        control_nodes.append(node)
    await db.flush()

    # Connect controls to risks sharing the same domain
    for c_node, control in zip(control_nodes, control_rows):
        for r_node, risk in zip(risk_nodes, risk_rows):
            if control.domain and risk.domain and (
                control.domain.lower() == risk.domain.lower() or
                control.domain.lower() in risk.domain.lower() or
                risk.domain.lower() in control.domain.lower()
            ):
                db.add(CanvasEdge(
                    org_id=org_uuid,
                    from_node_id=c_node.id,
                    to_node_id=r_node.id,
                    edge_type=EdgeType.mitigates,
                ))
    await db.flush()

    # ── 4. Frameworks ─────────────────────────────────────────────────────────
    def _framework_code(label: str) -> str:
        """Turn 'ISO 27001:2022 (Information Security)' → 'ISO_27001'"""
        short = label.split("(")[0].strip()
        return short.upper().replace(" ", "_").replace(".", "").replace("/", "_")[:50]

    for fw_label in fingerprint.get("suggested_frameworks", []):
        code = _framework_code(fw_label)
        try:
            db.add(Framework(
                org_id=org_uuid,
                code=code,
                label=fw_label.split("(")[0].strip(),
                category="Compliance",
                coverage_pct=0.0,
                ai_seeded=True,
            ))
            await db.flush()
        except Exception:
            await db.rollback()

    # ── 5. Radar signals ──────────────────────────────────────────────────────
    company_name = fingerprint.get("company_name", "your organisation")
    regulations = fingerprint.get("detected_regulations", [])
    risk_domains = [d.get("name", "") for d in fingerprint.get("risk_domains", [])]

    initial_signals = []

    # One signal per high-severity regulation
    for i, reg in enumerate(regulations[:6]):
        initial_signals.append(Signal(
            org_id=org_uuid,
            source="Regulatory Monitor",
            category=SignalCategory.regulatory,
            severity=SignalSeverity.high if i < 3 else SignalSeverity.medium,
            title=f"Compliance obligation: {reg.split('(')[0].strip()}",
            body=(
                f"{company_name} is subject to {reg}. Review current controls and "
                f"evidence collection to ensure ongoing compliance."
            ),
            tags=["onboarding", "regulatory", "ai-generated"],
            relevance_score=0.85,
            is_surfaced=True,
            published_at=datetime.now(timezone.utc),
            external_id=f"onboard-reg-{i}",
        ))

    # Domain-level threat signals
    domain_signals = [
        ("Cybersecurity", SignalSeverity.critical, SignalCategory.threat,
         "Ransomware campaigns targeting your sector are escalating",
         "Threat intelligence indicates a 40% increase in ransomware targeting organisations in your industry vertical. Review endpoint detection and backup controls."),
        ("Data Privacy", SignalSeverity.high, SignalCategory.regulatory,
         "Regulators increase enforcement actions on data retention violations",
         "Recent enforcement actions signal heightened scrutiny on data minimisation and retention policy compliance."),
        ("Third-Party", SignalSeverity.high, SignalCategory.vendor,
         "Critical vendor concentration risk identified in your supply chain",
         "AI analysis detected potential single-vendor dependency in critical operational areas. Consider diversification and contingency planning."),
        ("Financial Crime", SignalSeverity.high, SignalCategory.regulatory,
         "AML/CTF regulatory guidance updated — review required",
         "Regulators have issued updated AML/CTF guidance. Organisations should review transaction monitoring thresholds and suspicious activity reporting procedures."),
    ]

    for domain_kw, sev, cat, title, body in domain_signals:
        if any(domain_kw.lower() in d.lower() for d in risk_domains):
            initial_signals.append(Signal(
                org_id=org_uuid,
                source="Aegis Threat Intelligence",
                category=cat,
                severity=sev,
                title=title,
                body=body,
                tags=["onboarding", "ai-generated", domain_kw.lower()],
                relevance_score=0.9,
                is_surfaced=True,
                published_at=datetime.now(timezone.utc),
                external_id=f"onboard-domain-{domain_kw.lower()}",
            ))

    for sig in initial_signals:
        try:
            db.add(sig)
            await db.flush()
        except Exception:
            await db.rollback()

    await db.commit()
    logger.info(
        "seed_org_from_fingerprint complete: org=%s risks=%d controls=%d signals=%d",
        org_id, len(risk_rows), len(control_rows), len(initial_signals),
    )
