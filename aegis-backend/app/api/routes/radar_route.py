"""app/api/routes/radar_route.py"""
import json
import logging
from typing import Annotated
from uuid import UUID
from datetime import datetime, timezone, timedelta

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import build_org_profile_context, format_context_for_prompt
from app.api.auth import get_org_id
from app.config import get_settings
from app.database import get_db
from app.models import Signal, SignalSeverity, SignalCategory
from app.schemas import SignalListResponse, SignalResponse

logger = logging.getLogger(__name__)
settings = get_settings()
_claude = AsyncAnthropic(api_key=settings.anthropic_api_key)

router = APIRouter(prefix="/radar", tags=["radar"])

# ─────────────────────────────────────────────────────────────────────────────
# Curated multi-category signal catalogue
# Auto-seeded on first request so the Radar shows the full spectrum of risk
# signals — not just external regulations. Source "Aegis Radar" marks these so
# the seed is idempotent (won't duplicate, won't re-run once present).
# ─────────────────────────────────────────────────────────────────────────────

_CRIT = SignalSeverity.critical
_HIGH = SignalSeverity.high
_MED  = SignalSeverity.medium
_INFO = SignalSeverity.info

_REG  = SignalCategory.regulatory
_THR  = SignalCategory.threat
_VEN  = SignalCategory.vendor
_MAC  = SignalCategory.macro

# (category, severity, source, title, body, ai_recommendation, tags, days_ago)
_RADAR_CATALOG = [
    # ── Threat intelligence ────────────────────────────────────────────────
    (_THR, _CRIT, "MITRE / CISA",
     "Akira ransomware actively exploiting SSL-VPN appliances in financial sector",
     "CISA and sector ISACs report an active Akira ransomware campaign exploiting unpatched SSL-VPN appliances (CVE-2024-40766). Multiple mid-size financial institutions have been hit with double-extortion since the start of the month.",
     "Confirm SSL-VPN appliances are patched to the fixed firmware. Force-rotate VPN credentials, enable MFA on all remote access, and validate that immutable backups are tested and offline.",
     ["ransomware", "cyber", "cve", "vpn"], 2),
    (_THR, _HIGH, "Aegis Threat Intelligence",
     "Credential-stuffing campaign targeting retail banking login portals",
     "Automated credential-stuffing traffic against retail banking authentication endpoints has risen sharply across the sector, using breach-compilation password lists. Account-takeover attempts are bypassing weak rate-limiting.",
     "Review WAF rate-limiting and bot-management rules on the auth tier. Enforce step-up authentication on anomalous logins and monitor for impossible-travel patterns.",
     ["account-takeover", "fraud", "cyber"], 4),
    (_THR, _HIGH, "NVD",
     "High-severity zero-day in managed file-transfer software (active exploitation)",
     "A pre-authentication remote code execution vulnerability in a widely deployed managed file-transfer product is being actively exploited for data theft. Financial services are a primary target given regulatory data volumes.",
     "Inventory MFT exposure across the estate. Apply the emergency patch or take the service offline; hunt for indicators of compromise in transfer logs over the last 30 days.",
     ["zero-day", "cve", "data-exfiltration"], 6),
    (_THR, _MED, "Aegis Threat Intelligence",
     "Phishing kit impersonating regulator correspondence in circulation",
     "A phishing kit spoofing supervisory-authority correspondence (enforcement notice lures) is circulating. Targets are compliance and finance staff, with credential-harvesting landing pages.",
     "Brief compliance and finance teams. Add the campaign indicators to mail-filtering and run a targeted simulated-phishing exercise for those functions.",
     ["phishing", "social-engineering"], 9),

    # ── Third-party / vendor risk ──────────────────────────────────────────
    (_VEN, _CRIT, "Vendor Monitor",
     "KYC / identity-verification provider reporting major service degradation",
     "A critical KYC/identity-verification provider in the onboarding pipeline is reporting sustained service degradation. Customer onboarding and remediation screening are partially blocked, creating a regulatory SLA risk.",
     "Activate the manual KYC fallback runbook. Notify the MLRO of potential onboarding backlog and document the incident for the third-party risk register and regulator if SLA thresholds are breached.",
     ["third-party", "kyc", "outage", "concentration"], 1),
    (_VEN, _HIGH, "Vendor Monitor",
     "Core banking vendor announces sub-processor change — DPA review required",
     "The core banking platform vendor has notified a new sub-processor for analytics processing, effective in 30 days. This triggers a contractual data-processing-agreement and GDPR Article 28 review obligation.",
     "Have Legal and the DPO review the updated sub-processor list against the DPA. Assess data-residency and onward-transfer implications before the effective date; object in writing if controls are insufficient.",
     ["third-party", "gdpr", "dpa", "outsourcing"], 5),
    (_VEN, _HIGH, "Vendor Monitor",
     "Cloud region outage impacting payment-processing availability",
     "The primary cloud region hosting payment-processing workloads experienced a multi-hour availability incident. RTO for the payment gateway approached the DORA tolerable-disruption threshold.",
     "Run a post-incident review against the operational-resilience impact-tolerance statement. Validate multi-region failover and update the DORA important-business-service mapping.",
     ["third-party", "resilience", "dora", "outage"], 8),
    (_VEN, _MED, "Vendor Monitor",
     "Critical SaaS vendor SOC 2 report lapsed — assurance gap",
     "The annual SOC 2 Type II report for a critical SaaS vendor has lapsed and the bridge letter has not been provided. There is currently no independent assurance over that vendor's control environment.",
     "Request the bridge letter and renewal timeline from the vendor. Escalate to the third-party risk committee if assurance is not restored within the contractual window.",
     ["third-party", "assurance", "soc2"], 12),

    # ── Macro / geopolitical / sector ──────────────────────────────────────
    (_MAC, _HIGH, "Macro Watch",
     "Central bank signals further rate tightening — IRRBB exposure",
     "Forward guidance points to continued policy-rate tightening. Interest-rate risk in the banking book and ALM repricing assumptions should be re-tested against a steeper-for-longer scenario.",
     "Re-run IRRBB stress scenarios with the updated rate path. Brief ALCO on EVE/NII sensitivity and review hedge effectiveness and deposit-beta assumptions.",
     ["macro", "interest-rate", "alm", "irrbb"], 3),
    (_MAC, _HIGH, "Macro Watch",
     "Expanded sanctions package against additional financial entities",
     "A new sanctions package adds financial entities and changes ownership-aggregation rules. Screening lists and 50%-rule logic must be updated to avoid false-negative exposure.",
     "Confirm the screening provider has ingested the updated lists. Re-run a retrospective screen over recent high-value payments and document results for the sanctions control file.",
     ["macro", "sanctions", "screening"], 7),
    (_MAC, _MED, "Macro Watch",
     "Sector-wide deposit-outflow trend observed in regional banking",
     "Industry data shows an accelerating deposit-outflow trend in the regional banking segment, with funding mix shifting toward higher-cost wholesale sources. Liquidity-coverage assumptions warrant review.",
     "Stress liquidity (LCR/NSFR) under an adverse deposit-runoff scenario and review the contingency funding plan with treasury.",
     ["macro", "liquidity", "funding"], 11),
    (_MAC, _MED, "Macro Watch",
     "FX volatility spike — treasury and hedging review",
     "EUR/USD realised volatility has spiked on macro uncertainty. Open FX positions and the effectiveness of existing hedges should be reviewed against revised value-at-risk limits.",
     "Review FX VaR utilisation and hedge coverage with treasury; confirm limit framework remains appropriate under the elevated volatility regime.",
     ["macro", "fx", "market-risk"], 14),

    # ── Regulatory (curated headline set) ──────────────────────────────────
    (_REG, _CRIT, "Regulatory Monitor",
     "DORA in force — ICT resilience obligations now enforceable",
     "The Digital Operational Resilience Act is now enforceable. ICT risk-management, incident-classification, third-party-register and threat-led-penetration-testing obligations are subject to supervisory examination.",
     "Confirm the DORA gap-assessment remediation roadmap is on track. Prioritise the ICT third-party register and incident-classification procedures for the next supervisory cycle.",
     ["regulatory", "dora", "resilience"], 2),
    (_REG, _HIGH, "Regulatory Monitor",
     "EBA publishes final guidelines on outsourcing arrangements",
     "Updated guidelines tighten expectations on critical-or-important function identification, exit strategies and sub-outsourcing oversight, with documentation expected at the next examination.",
     "Map current outsourcing register to the updated criteria. Verify exit strategies and sub-outsourcing clauses exist for all critical-or-important arrangements.",
     ["regulatory", "outsourcing", "eba"], 6),
    (_REG, _HIGH, "Regulatory Monitor",
     "AMLD6 — expanded predicate offences and individual liability",
     "The sixth Anti-Money-Laundering Directive expands predicate offences and introduces individual liability for senior management, raising the bar for transaction-monitoring coverage and governance evidence.",
     "Reassess transaction-monitoring scenario coverage against the expanded predicate-offence list and confirm senior-management governance and training evidence is current.",
     ["regulatory", "aml", "amld6"], 10),
    (_REG, _MED, "Regulatory Monitor",
     "EU AI Act — high-risk obligations for credit-scoring models",
     "Credit-scoring and creditworthiness models are classified high-risk under the EU AI Act, triggering data-governance, transparency, human-oversight and conformity-assessment obligations.",
     "Inventory ML models used in credit decisioning. Begin a conformity-assessment gap analysis covering data governance, bias testing and human-oversight controls.",
     ["regulatory", "ai-act", "model-risk"], 15),
]


async def _generate_context_aware_signals(org_id: UUID, db: AsyncSession) -> bool:
    """
    Generate org-specific radar signals via Claude using the Company Profile.
    Returns True if signals were generated, False if the profile is too sparse
    (falls back to the hardcoded catalogue).
    """
    org_context = await build_org_profile_context(org_id, db)
    if org_context is None or (
        not org_context.lines_of_business
        and not org_context.geographies
        and not org_context.industries
    ):
        return False

    context_block = format_context_for_prompt(org_context)
    now = datetime.now(timezone.utc)

    prompt = f"""You are a senior GRC analyst. Generate 8-10 relevant risk radar signals for the company below.
Signals must be specific to this company's profile — industries, geographies, products, and customer segments.
Do NOT produce generic financial-sector signals unless the company actually operates in financial services.

{context_block}

Return a JSON array of signal objects. Each object must have:
{{
  "category": "regulatory|threat|vendor|macro",
  "severity": "critical|high|medium|info",
  "source": "<issuing body, e.g. 'ICO', 'NIST', 'Threat Intelligence'>",
  "title": "<concise title, max 120 chars>",
  "body": "<2-3 sentence description of the signal and why it matters to this company>",
  "ai_recommendation": "<1-2 sentence specific action recommendation>",
  "tags": ["<tag1>", "<tag2>"],
  "days_ago": <integer 1-14>
}}

Prioritise signals relating to:
- Regulations applicable to their geographies (e.g. GDPR if EU, CCPA if US, MAS TRM if SG)
- Risks matching their sector and lines of business
- Threats relevant to their technology stack and data types
- Third-party and supply chain risks given their vendor tier profile

Return ONLY a valid JSON array, no other text."""

    try:
        response = await _claude.messages.create(
            model=settings.claude_model,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        signals_data = json.loads(raw)
    except Exception as e:
        logger.warning("Context-aware signal generation failed: %s", e)
        return False

    cat_map = {
        "regulatory": SignalCategory.regulatory,
        "threat": SignalCategory.threat,
        "vendor": SignalCategory.vendor,
        "macro": SignalCategory.macro,
    }
    sev_map = {
        "critical": SignalSeverity.critical,
        "high": SignalSeverity.high,
        "medium": SignalSeverity.medium,
        "info": SignalSeverity.info,
    }

    for i, s in enumerate(signals_data[:12]):
        db.add(Signal(
            org_id=org_id,
            source=s.get("source", "Aegis Radar"),
            category=cat_map.get(s.get("category", "regulatory"), SignalCategory.regulatory),
            severity=sev_map.get(s.get("severity", "medium"), SignalSeverity.medium),
            title=s.get("title", "")[:500],
            body=s.get("body", ""),
            ai_recommendation=s.get("ai_recommendation"),
            tags=s.get("tags", []),
            relevance_score=0.90,
            is_surfaced=True,
            is_new=True,
            published_at=now - timedelta(days=s.get("days_ago", i + 1)),
            external_id=f"radar-ctx-{i}",
        ))
    await db.commit()
    return True


async def _seed_radar_signals(org_id: UUID, db: AsyncSession) -> None:
    """Idempotently seed the curated multi-category signal catalogue."""
    now = datetime.now(timezone.utc)
    for i, (cat, sev, source, title, body, rec, tags, days_ago) in enumerate(_RADAR_CATALOG):
        db.add(Signal(
            org_id=org_id,
            source=source,
            category=cat,
            severity=sev,
            title=title,
            body=body,
            ai_recommendation=rec,
            tags=tags,
            relevance_score=0.92 if sev in (_CRIT, _HIGH) else 0.78,
            is_surfaced=True,
            is_new=True,
            published_at=now - timedelta(days=days_ago),
            external_id=f"radar-cat-{i}",
        ))
    await db.commit()


@router.get("/signals", response_model=SignalListResponse)
async def list_signals(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
    category: str | None = Query(None),
    severity: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    # Auto-seed once per org: prefer context-aware signals, fall back to catalogue.
    has_seeded = (await db.execute(
        select(Signal.id).where(
            Signal.org_id == org_id,
            Signal.external_id.like("radar-%"),
        ).limit(1)
    )).scalar_one_or_none()
    if has_seeded is None:
        context_generated = await _generate_context_aware_signals(org_id, db)
        if not context_generated:
            await _seed_radar_signals(org_id, db)

    q = (
        select(Signal)
        .where(Signal.org_id == org_id, Signal.is_surfaced == True, Signal.dismissed_at.is_(None))
        .order_by(Signal.created_at.desc())
    )
    if category:
        q = q.where(Signal.category == category)
    if severity:
        q = q.where(Signal.severity == severity)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset((page - 1) * page_size).limit(page_size))).scalars().all()

    all_signals = (await db.execute(
        select(Signal).where(Signal.org_id == org_id, Signal.is_surfaced == True, Signal.dismissed_at.is_(None))
    )).scalars().all()

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    counts = {
        "critical": sum(1 for s in all_signals if s.severity == SignalSeverity.critical),
        "high": sum(1 for s in all_signals if s.severity == SignalSeverity.high),
        "medium": sum(1 for s in all_signals if s.severity == SignalSeverity.medium),
        "info": sum(1 for s in all_signals if s.severity == SignalSeverity.info),
        "new_today": sum(1 for s in all_signals if s.created_at and s.created_at >= today_start),
        # Per-category counts power the Radar category navigation
        "all": len(all_signals),
        "cat_regulatory": sum(1 for s in all_signals if s.category == SignalCategory.regulatory),
        "cat_threat": sum(1 for s in all_signals if s.category == SignalCategory.threat),
        "cat_vendor": sum(1 for s in all_signals if s.category == SignalCategory.vendor),
        "cat_macro": sum(1 for s in all_signals if s.category == SignalCategory.macro),
    }

    new_ids = [s.id for s in items if s.is_new]
    if new_ids:
        await db.execute(update(Signal).where(Signal.id.in_(new_ids)).values(is_new=False))

    return SignalListResponse(items=items, total=total, counts=counts)


@router.post("/signals/{signal_id}/dismiss", status_code=204)
async def dismiss_signal(
    signal_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(Signal)
        .where(Signal.id == signal_id, Signal.org_id == org_id)
        .values(dismissed_at=datetime.now(timezone.utc))
    )
