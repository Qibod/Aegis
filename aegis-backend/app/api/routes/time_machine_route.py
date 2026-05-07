"""
app/api/routes/time_machine_route.py
────────────────────────────────────
GRC Time Machine — history scrubber + scenario simulation engine.

Endpoints:
  GET  /time-machine/snapshots           → list of monthly snapshots (for scrubber)
  GET  /time-machine/events              → timeline events (coloured dots)
  POST /time-machine/simulate            → run a scenario simulation
  GET  /time-machine/simulations         → recent simulation runs
  POST /time-machine/seed-history        → seed 18 months of demo history
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_active_user, get_org_id
from app.database import get_db
from app.models import (
    Control, Framework, Risk, User,
    GRCEvent, GRCEventSentiment, GRCEventType,
    TimeMachineSnapshot, SimulationRun,
    ControlStatus, RiskSeverity,
)

router = APIRouter(prefix="/time-machine", tags=["time-machine"])


# ── Pydantic I/O schemas ───────────────────────────────────────────────────────

class SnapshotOut(BaseModel):
    snapshot_month: str
    total_risks: int
    critical_risks: int
    high_risks: int
    total_controls: int
    effective_controls: int
    coverage_pct: float
    frameworks_active: int
    open_audit_plans: int
    delta_risks: int
    delta_coverage_pct: float
    delta_controls: int
    notable_events: list[dict[str, Any]]
    risk_diff: dict[str, Any]
    control_diff: dict[str, Any]

    class Config:
        from_attributes = True


class TimelineEventOut(BaseModel):
    id: str
    event_type: str
    sentiment: str
    title: str
    description: str | None
    entity_type: str | None
    entity_name: str | None
    occurred_at: str


class SimulateRequest(BaseModel):
    scenario_key: str = Field(..., description="e.g. 'data_breach'")
    scenario_label: str
    parameters: dict[str, Any]    # {affected_records, control_effectiveness_pct, detection_lag_days, response_readiness_pct}


class FindingOut(BaseModel):
    severity: str
    title: str
    description: str


class SimulationResult(BaseModel):
    id: str
    scenario_key: str
    scenario_label: str
    parameters: dict[str, Any]
    residual_risk_score: float
    controls_failing_count: int
    regulatory_exposure_usd: float
    domain_exposure: list[dict[str, Any]]
    ai_recommendation: str
    findings: list[FindingOut]
    run_at: str


# ── GET /time-machine/snapshots ───────────────────────────────────────────────

@router.get("/snapshots", response_model=list[SnapshotOut])
async def list_snapshots(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    """Return all monthly snapshots sorted oldest → newest."""
    rows = (await db.execute(
        select(TimeMachineSnapshot)
        .where(TimeMachineSnapshot.org_id == org_id)
        .order_by(TimeMachineSnapshot.snapshot_month)
    )).scalars().all()

    # If no snapshots yet, auto-generate demo history
    if not rows:
        await _seed_demo_history(org_id, db)
        rows = (await db.execute(
            select(TimeMachineSnapshot)
            .where(TimeMachineSnapshot.org_id == org_id)
            .order_by(TimeMachineSnapshot.snapshot_month)
        )).scalars().all()

    return rows


# ── GET /time-machine/events ──────────────────────────────────────────────────

@router.get("/events", response_model=list[TimelineEventOut])
async def list_events(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    """Return all timeline events for the org, newest first."""
    rows = (await db.execute(
        select(GRCEvent)
        .where(GRCEvent.org_id == org_id)
        .order_by(desc(GRCEvent.occurred_at))
        .limit(200)
    )).scalars().all()

    return [
        TimelineEventOut(
            id=str(r.id),
            event_type=r.event_type.value,
            sentiment=r.sentiment.value,
            title=r.title,
            description=r.description,
            entity_type=r.entity_type,
            entity_name=r.entity_name,
            occurred_at=r.occurred_at.isoformat(),
        )
        for r in rows
    ]


# ── POST /time-machine/simulate ───────────────────────────────────────────────

@router.post("/simulate", response_model=SimulationResult)
async def run_simulation(
    payload: SimulateRequest,
    org_id: Annotated[UUID, Depends(get_org_id)],
    _: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    """Run a scenario simulation against the org's current control inventory."""
    # Load current controls + risks for context
    controls = (await db.execute(
        select(Control).where(Control.org_id == org_id)
    )).scalars().all()

    risks = (await db.execute(
        select(Risk).where(Risk.org_id == org_id)
    )).scalars().all()

    result = _compute_simulation(payload, controls, risks)

    # Persist
    run = SimulationRun(
        org_id=org_id,
        scenario_key=payload.scenario_key,
        scenario_label=payload.scenario_label,
        parameters=payload.parameters,
        residual_risk_score=result["residual_risk_score"],
        controls_failing_count=result["controls_failing_count"],
        regulatory_exposure_usd=result["regulatory_exposure_usd"],
        domain_exposure=result["domain_exposure"],
        ai_recommendation=result["ai_recommendation"],
        findings=[f.model_dump() for f in result["findings"]],
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    return SimulationResult(
        id=str(run.id),
        scenario_key=run.scenario_key,
        scenario_label=run.scenario_label,
        parameters=run.parameters,
        residual_risk_score=run.residual_risk_score,
        controls_failing_count=run.controls_failing_count,
        regulatory_exposure_usd=run.regulatory_exposure_usd,
        domain_exposure=run.domain_exposure,
        ai_recommendation=run.ai_recommendation,
        findings=[FindingOut(**f) for f in run.findings],
        run_at=run.run_at.isoformat(),
    )


# ── GET /time-machine/simulations ─────────────────────────────────────────────

@router.get("/simulations", response_model=list[SimulationResult])
async def list_simulations(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(SimulationRun)
        .where(SimulationRun.org_id == org_id)
        .order_by(desc(SimulationRun.run_at))
        .limit(20)
    )).scalars().all()

    return [
        SimulationResult(
            id=str(r.id),
            scenario_key=r.scenario_key,
            scenario_label=r.scenario_label,
            parameters=r.parameters,
            residual_risk_score=r.residual_risk_score or 0,
            controls_failing_count=r.controls_failing_count or 0,
            regulatory_exposure_usd=r.regulatory_exposure_usd or 0,
            domain_exposure=r.domain_exposure or [],
            ai_recommendation=r.ai_recommendation or "",
            findings=[FindingOut(**f) for f in (r.findings or [])],
            run_at=r.run_at.isoformat(),
        )
        for r in rows
    ]


# ── Simulation engine ─────────────────────────────────────────────────────────

# Scenario definitions — base multipliers for regulatory exposure
_SCENARIO_CONFIG: dict[str, dict] = {
    "data_breach": {
        "label": "Major Data Breach",
        "domains": ["Data Privacy & Protection", "Cybersecurity & Information Security", "Third-Party & Vendor Risk"],
        "base_fine_usd": 20_000_000,       # GDPR Art.83 max 4% global turnover, or 20M€
        "fine_multiplier_per_record": 150,  # per-record exposure estimate
        "control_keywords": ["gdpr", "dsar", "data", "endpoint", "access", "cloud", "vulnerability"],
    },
    "regulatory_action": {
        "label": "Regulatory Enforcement Action",
        "domains": ["Financial Crime & Fraud", "Legal & Regulatory Compliance", "Conduct & Culture Risk"],
        "base_fine_usd": 15_000_000,
        "fine_multiplier_per_record": 0,
        "control_keywords": ["aml", "kyc", "sanctions", "monitoring", "regulatory", "whistleblower"],
    },
    "ransomware": {
        "label": "Ransomware Attack",
        "domains": ["Cybersecurity & Information Security", "Business Continuity & Resilience", "Technology & IT Risk"],
        "base_fine_usd": 8_000_000,
        "fine_multiplier_per_record": 50,
        "control_keywords": ["endpoint", "edr", "backup", "resilience", "patch", "cloud", "access"],
    },
    "third_party_failure": {
        "label": "Critical Vendor Failure",
        "domains": ["Third-Party & Vendor Risk", "Business Continuity & Resilience", "Operational Risk"],
        "base_fine_usd": 5_000_000,
        "fine_multiplier_per_record": 0,
        "control_keywords": ["vendor", "third-party", "continuity", "resilience", "supplier"],
    },
    "ai_bias": {
        "label": "Algorithmic Bias Finding",
        "domains": ["Model & Algorithmic Risk", "Legal & Regulatory Compliance", "Conduct & Culture Risk"],
        "base_fine_usd": 10_000_000,
        "fine_multiplier_per_record": 80,
        "control_keywords": ["model", "ai", "algorithm", "bias", "credit", "conduct"],
    },
    "pre_audit": {
        "label": "Pre-Audit Stress Test",
        "domains": ["Financial Crime & Fraud", "Data Privacy & Protection", "Cybersecurity & Information Security",
                    "Business Continuity & Resilience", "Third-Party & Vendor Risk"],
        "base_fine_usd": 25_000_000,
        "fine_multiplier_per_record": 100,
        "control_keywords": ["*"],  # all controls
    },
}

_SCENARIO_FINDINGS: dict[str, list[dict]] = {
    "data_breach": [
        {"severity": "critical", "title": "Unencrypted PII in backup storage",
         "description": "Backup systems contain unencrypted customer PII that would be exposed in a breach. GDPR Article 32 requires appropriate technical measures including encryption of personal data."},
        {"severity": "high", "title": "Access review backlog — 127 overdue users",
         "description": "Quarterly access recertification is 34% complete with 127 overdue accounts. In a breach scenario, investigators would find excessive access as a contributing factor."},
        {"severity": "high", "title": "DSAR fulfilment SLA at risk",
         "description": "With fragmented data stores, identifying and extracting all affected records within the 72-hour breach notification window would be operationally impossible."},
        {"severity": "medium", "title": "Cloud misconfiguration — S3 buckets exposed",
         "description": "2 critical CSPM findings indicate publicly accessible S3 buckets. These would be the entry point in a credential-based breach scenario."},
    ],
    "regulatory_action": [
        {"severity": "critical", "title": "Transaction monitoring coverage gap",
         "description": "Current rule engine covers 47 AML typologies. DNB examination typically expects 60+ typologies for a firm with this transaction volume. Gap would trigger enhanced supervision."},
        {"severity": "critical", "title": "Sanctions screening false negative risk",
         "description": "Name-matching algorithm has documented gaps with transliteration variants. A single confirmed false negative during examination triggers mandatory reporting to OFAC/EU."},
        {"severity": "high", "title": "EDD workflow not consistently applied",
         "description": "Enhanced due diligence triggers are applied inconsistently for PEP categories. Examiners would sample 30-50 high-risk customer files and expect uniform EDD documentation."},
        {"severity": "medium", "title": "KYC periodic review overdue for 18% of customers",
         "description": "Periodic review cycle has not been completed for 18% of the medium-risk customer population. This is a standard examination finding."},
    ],
    "ransomware": [
        {"severity": "critical", "title": "Recovery time objective breach under DORA",
         "description": "Payment gateway RTO is 6 hours against DORA's tolerable disruption threshold of 2 hours for important business services. Failure to restore within threshold triggers regulatory notification."},
        {"severity": "high", "title": "EDR coverage gap — 2% of endpoints unprotected",
         "description": "98% EDR coverage leaves approximately 15 endpoints unprotected. In a ransomware scenario, unprotected endpoints are the typical initial access vector."},
        {"severity": "high", "title": "Privileged credential vaulting incomplete",
         "description": "12 overdue quarterly reviews include credentials that may belong to former contractors. Stale privileged credentials are a primary ransomware propagation mechanism."},
        {"severity": "medium", "title": "Patch backlog — 7 high-severity vulnerabilities",
         "description": "7 high-severity CVEs exceed the 7-day patch SLA. Public PoC code is available for 3 of these, narrowing the exploitation window significantly."},
    ],
    "third_party_failure": [
        {"severity": "critical", "title": "KYC vendor single-point-of-failure",
         "description": "100% of customer onboarding flows through a single KYC API provider. Zero documented fallback procedure. A 4-hour outage halts all new account opening."},
        {"severity": "high", "title": "Payment processor concentration risk",
         "description": "Transaction processing is split 80/20 across two providers. The primary processor handling 80% of volume has no contractually guaranteed RTO under the current agreement."},
        {"severity": "medium", "title": "Vendor security assessment overdue for 3 critical suppliers",
         "description": "Annual security questionnaire cycle has not been completed for 3 suppliers classified as critical. DORA requires documented third-party risk assessments for all critical ICT providers."},
    ],
    "ai_bias": [
        {"severity": "critical", "title": "Credit model demographic disparity detected",
         "description": "Back-testing reveals a 12% disparity in approval rates for protected groups when income is held constant. EU AI Act Art.10 requires bias monitoring and documentation for high-risk AI systems."},
        {"severity": "high", "title": "Model inventory incomplete",
         "description": "AI model governance framework does not cover 4 ML models identified in production. EU AI Act requires a comprehensive inventory with risk classification for all AI systems in financial services."},
        {"severity": "high", "title": "Explainability documentation absent for credit decisions",
         "description": "Consumer Credit Directive requires that applicants receive an explanation of automated decisions. Current system cannot produce individual explanations — class action exposure."},
        {"severity": "medium", "title": "Model drift monitoring not configured",
         "description": "Transaction fraud model shows 8% performance degradation vs training baseline. No automated drift alert is configured to notify model risk when degradation exceeds threshold."},
    ],
    "pre_audit": [
        {"severity": "critical", "title": "AML transaction monitoring coverage below examination standard",
         "description": "Rule set covers 78% of expected typologies. DNB examinations in 2024-2025 have resulted in remediation orders for firms below 90% coverage."},
        {"severity": "critical", "title": "DORA ICT risk management framework incomplete",
         "description": "DORA became applicable January 2025. Current ICT risk management documentation does not meet the required 6-component framework. Immediate remediation required before examination."},
        {"severity": "high", "title": "Access review completion 34% — quarterly deadline in 14 days",
         "description": "Examiner sampling of access controls will find the incomplete recertification cycle. This is a recurring finding that elevates the probability of a remediation order."},
        {"severity": "high", "title": "Business continuity plan not tested at full scale",
         "description": "Last full-scale DR test covered payment gateway only. Core banking and KYC systems have not been tested against DORA's business continuity requirements."},
        {"severity": "medium", "title": "ESG disclosure framework below SFDR requirements",
         "description": "SFDR entity-level disclosure is in place but product-level PAI disclosures are incomplete. Institutional investors are increasingly using SFDR compliance as a due diligence criterion."},
    ],
}


def _compute_simulation(
    payload: SimulateRequest,
    controls: list,
    risks: list,
) -> dict:
    cfg = _SCENARIO_CONFIG.get(payload.scenario_key, _SCENARIO_CONFIG["pre_audit"])
    params = payload.parameters
    p = params

    affected_records      = float(p.get("affected_records", 500_000))
    ctrl_effectiveness    = float(p.get("control_effectiveness_pct", 50)) / 100.0
    detection_lag         = float(p.get("detection_lag_days", 14))
    response_readiness    = float(p.get("response_readiness_pct", 60)) / 100.0

    # ── Controls that would fail under this scenario ───────────────────────
    scenario_keywords = cfg["control_keywords"]
    if scenario_keywords == ["*"]:
        relevant_controls = controls
    else:
        relevant_controls = [
            c for c in controls
            if any(
                kw in (c.name or "").lower() or kw in (c.description or "").lower()
                for kw in scenario_keywords
            )
        ]

    # A control "fails" when its current status is weak AND scenario reduces effectiveness
    failing = []
    for c in relevant_controls:
        base_effectiveness = {
            ControlStatus.effective:  0.85,
            ControlStatus.partial:    0.50,
            ControlStatus.ineffective: 0.20,
            ControlStatus.not_tested: 0.30,
        }.get(c.status, 0.50)

        scenario_adjusted = base_effectiveness * ctrl_effectiveness
        if scenario_adjusted < 0.45:
            failing.append(c)

    controls_failing_count = max(len(failing), len(_SCENARIO_FINDINGS.get(payload.scenario_key, [])))

    # ── Regulatory exposure ────────────────────────────────────────────────
    record_exposure   = affected_records * cfg["fine_multiplier_per_record"]
    base_fine         = cfg["base_fine_usd"]
    lag_multiplier    = 1.0 + (detection_lag / 30.0) * 0.4   # more lag = worse
    readiness_reducer = 0.4 + response_readiness * 0.6         # better readiness = lower fine
    regulatory_exposure = (base_fine + record_exposure) * lag_multiplier * (2.0 - readiness_reducer)
    regulatory_exposure = min(regulatory_exposure, base_fine * 8)  # cap at 8x base fine

    # ── Residual risk score 0-100 ──────────────────────────────────────────
    risk_base       = 50.0
    ctrl_penalty    = (1 - ctrl_effectiveness) * 25
    lag_penalty     = min(detection_lag / 90.0 * 15, 15)
    readiness_bonus = response_readiness * 15
    residual_risk_score = min(100.0, max(0.0, risk_base + ctrl_penalty + lag_penalty - readiness_bonus))

    # ── Domain exposure breakdown ──────────────────────────────────────────
    scenario_domains = cfg["domains"]
    total_domain_weight = sum(range(1, len(scenario_domains) + 1))
    domain_exposure = []
    for i, domain in enumerate(scenario_domains):
        weight = (len(scenario_domains) - i) / total_domain_weight
        exposure_pct = weight * 100 * (1 - ctrl_effectiveness * 0.6)
        domain_exposure.append({
            "domain": domain,
            "exposure_pct": round(min(100.0, exposure_pct), 1),
        })

    # ── AI recommendation ──────────────────────────────────────────────────
    ai_recommendation = _generate_ai_recommendation(
        payload.scenario_key, payload.scenario_label,
        controls_failing_count, regulatory_exposure, residual_risk_score,
        ctrl_effectiveness, detection_lag, response_readiness,
    )

    # ── Findings ───────────────────────────────────────────────────────────
    raw_findings = _SCENARIO_FINDINGS.get(payload.scenario_key, [])
    # Adjust findings based on control effectiveness — fewer findings if controls are strong
    if ctrl_effectiveness > 0.75:
        raw_findings = [f for f in raw_findings if f["severity"] != "medium"]
    findings = [FindingOut(**f) for f in raw_findings]

    return {
        "residual_risk_score": round(residual_risk_score, 1),
        "controls_failing_count": controls_failing_count,
        "regulatory_exposure_usd": round(regulatory_exposure, 0),
        "domain_exposure": domain_exposure,
        "ai_recommendation": ai_recommendation,
        "findings": findings,
    }


def _generate_ai_recommendation(
    scenario_key: str,
    scenario_label: str,
    failing_controls: int,
    exposure_usd: float,
    risk_score: float,
    ctrl_effectiveness: float,
    detection_lag: float,
    response_readiness: float,
) -> str:
    exposure_m = exposure_usd / 1_000_000

    templates: dict[str, str] = {
        "data_breach": (
            f"Under this breach scenario, {failing_controls} controls would fail examination. "
            f"The estimated regulatory exposure of €{exposure_m:.1f}M is driven primarily by the detection lag of {detection_lag:.0f} days — "
            f"GDPR's 72-hour notification window means every additional day increases the Art.83 fine basis. "
            f"Highest-priority remediation: (1) complete the access recertification cycle this week — this directly reduces breach scope; "
            f"(2) implement automated DSAR data-mapping to meet the notification window; "
            f"(3) remediate the 2 critical CSPM findings before the next penetration test. "
            f"Estimated remediation cost: €180K–€250K. Expected fine reduction: 60–75%, saving €{exposure_m * 0.65:.1f}M in expected fines."
        ),
        "regulatory_action": (
            f"A regulatory examination under this scenario would identify {failing_controls} material findings. "
            f"The €{exposure_m:.1f}M exposure estimate is based on comparable DNB enforcement actions in 2023-2024 for firms in your sector. "
            f"The transaction monitoring gap is the single highest-priority item — expanding from 47 to 65+ typologies typically takes 3-4 months. "
            f"Recommend initiating an immediate internal gap assessment against the DNB's published AML examination framework. "
            f"With {response_readiness*100:.0f}% response readiness, you can reduce the fine basis materially by self-reporting the gap before examination."
        ),
        "ransomware": (
            f"This ransomware scenario scores {risk_score:.0f}/100 residual risk with {failing_controls} controls likely to fail. "
            f"The €{exposure_m:.1f}M exposure includes DORA notification requirements, operational recovery costs, and customer compensation. "
            f"The {detection_lag:.0f}-day detection lag is the critical driver — every additional day of dwell time increases the number of systems encrypted. "
            f"Immediate priorities: (1) close the 12 overdue privileged account reviews; "
            f"(2) remediate the 7 high-severity CVEs within 48 hours; "
            f"(3) validate backup integrity and test restoration procedure for payment gateway. "
            f"These three actions reduce residual risk score to approximately {max(20, risk_score - 25):.0f}/100."
        ),
        "third_party_failure": (
            f"Your vendor concentration creates a single-threaded failure mode. {failing_controls} controls fail under this scenario. "
            f"The €{exposure_m:.1f}M exposure is primarily operational loss from revenue disruption, not regulatory fines. "
            f"Highest-value action: negotiate a secondary KYC provider contract — this alone reduces the exposure by ~60%. "
            f"DORA requires documented exit plans for all critical ICT third-party providers. Building these plans also satisfies the regulatory requirement."
        ),
        "ai_bias": (
            f"EU AI Act compliance is the dominant risk driver here. {failing_controls} findings would be material in an examination. "
            f"The €{exposure_m:.1f}M exposure combines Art.83 GDPR fines for discriminatory credit decisions and potential class action liability. "
            f"The credit model bias finding is the most urgent — regulators will require immediate suspension of the model pending remediation. "
            f"Recommend commissioning an independent algorithmic audit within 30 days, and implementing a human-in-the-loop review for all declined applications while the model is remediated."
        ),
        "pre_audit": (
            f"Pre-examination analysis identifies {failing_controls} findings across your control environment. "
            f"Total regulatory exposure under this examination scenario is €{exposure_m:.1f}M — this is your worst-case estimate if findings are not remediated. "
            f"The examination team will prioritise AML controls, DORA compliance, and access management — these have the highest finding density. "
            f"Recommend a 30-60 day remediation sprint focusing on: (1) AML typology expansion, (2) access recertification completion, (3) DORA documentation. "
            f"Historical data shows that proactive self-disclosure of material gaps before examination reduces enforcement severity by 40-60%. "
            f"With {response_readiness*100:.0f}% current readiness, you have sufficient time to address the critical findings before the examination window."
        ),
    }

    return templates.get(scenario_key, (
        f"This scenario scores {risk_score:.0f}/100 residual risk. "
        f"{failing_controls} controls would fail under examination with €{exposure_m:.1f}M regulatory exposure. "
        f"Prioritise remediation of critical findings to reduce both the risk score and fine exposure."
    ))


# ── Demo history seeder ───────────────────────────────────────────────────────

async def _seed_demo_history(org_id: UUID, db: AsyncSession) -> None:
    """
    Seed 18 months of realistic GRC history for the time machine demo.
    Creates TimeMachineSnapshot rows + GRCEvent rows.
    """
    from datetime import date
    from dateutil.relativedelta import relativedelta  # type: ignore

    today = date.today()
    start = today - relativedelta(months=17)

    # ── Month-by-month trajectory ──────────────────────────────────────────────
    # Each tuple: (risks, critical, high, controls, effective, coverage_pct, frameworks, notable_events)
    MONTHS_DATA = [
        # Month 0 — 17 months ago: early-stage, sparse coverage
        (4,  2, 2, 3,  1, 18.0, 2, []),
        # Month 1 — onboarding complete, AI seeded initial risks
        (12, 4, 7, 8,  3, 24.0, 4, [
            {"type": "milestone", "title": "AI fingerprinting completed — 12 risks seeded", "sentiment": "positive"},
        ]),
        # Month 2 — first controls tested
        (12, 4, 7, 10, 4, 31.0, 4, [
            {"type": "control_tested", "title": "KYC engine tested — result: Effective", "sentiment": "positive"},
        ]),
        # Month 3 — regulatory inquiry arrives
        (14, 4, 8, 11, 4, 33.0, 5, [
            {"type": "regulatory_inquiry", "title": "DNB supervisory letter received — AML review requested", "sentiment": "negative"},
            {"type": "risk_created", "title": "New risk added: AMLD6 transaction monitoring gap", "sentiment": "negative"},
        ]),
        # Month 4 — response to inquiry, new controls
        (14, 4, 8, 13, 5, 38.0, 5, [
            {"type": "control_created", "title": "Transaction monitoring rule engine enhanced — 12 new typologies", "sentiment": "positive"},
            {"type": "audit_opened", "title": "Internal AML audit opened in response to DNB letter", "sentiment": "neutral"},
        ]),
        # Month 5 — audit in progress
        (14, 4, 8, 13, 6, 42.0, 5, [
            {"type": "control_tested", "title": "Sanctions screening API tested — 1 gap found", "sentiment": "negative"},
        ]),
        # Month 6 — audit closes, coverage improves
        (14, 3, 8, 14, 7, 48.0, 6, [
            {"type": "audit_closed", "title": "Internal AML audit closed — 3 findings remediated", "sentiment": "positive"},
            {"type": "framework_added", "title": "DORA added to active framework portfolio", "sentiment": "positive"},
        ]),
        # Month 7 — SOC 2 / ISO work begins
        (15, 3, 9, 14, 7, 49.0, 6, [
            {"type": "risk_created", "title": "New risk identified: Cloud misconfiguration (post-pentest)", "sentiment": "negative"},
        ]),
        # Month 8 — big improvement month
        (15, 3, 9, 15, 9, 56.0, 7, [
            {"type": "control_tested", "title": "CSPM deployed — 23 cloud misconfigurations auto-remediated", "sentiment": "positive"},
            {"type": "certification", "title": "ISO 27001:2022 certification audit commenced", "sentiment": "positive"},
        ]),
        # Month 9 — setback: ransomware incident (contained)
        (16, 4, 9, 15, 8, 53.0, 7, [
            {"type": "signal_critical", "title": "Ransomware incident detected and contained — 4h disruption", "sentiment": "negative"},
            {"type": "risk_updated", "title": "Ransomware risk upgraded to critical — post-incident review", "sentiment": "negative"},
        ]),
        # Month 10 — post-incident hardening
        (16, 4, 9, 15, 9, 57.0, 7, [
            {"type": "control_tested", "title": "EDR coverage expanded to 98% post-incident", "sentiment": "positive"},
            {"type": "control_created", "title": "Privileged Access Management (CyberArk) deployed", "sentiment": "positive"},
        ]),
        # Month 11 — ISO achieved
        (15, 3, 9, 15, 10, 62.0, 7, [
            {"type": "certification", "title": "ISO 27001:2022 certificate achieved", "sentiment": "positive"},
            {"type": "risk_updated", "title": "5 cybersecurity risks downgraded following ISO certification", "sentiment": "positive"},
        ]),
        # Month 12 — DORA preparations
        (15, 3, 9, 15, 10, 64.0, 7, [
            {"type": "audit_opened", "title": "DORA readiness assessment commenced", "sentiment": "neutral"},
            {"type": "milestone", "title": "12-month GRC programme review — overall maturity: Developing", "sentiment": "neutral"},
        ]),
        # Month 13 — steady state
        (15, 3, 9, 15, 10, 66.0, 7, [
            {"type": "control_tested", "title": "Business continuity DR test — payment gateway RTO: 5.2h (target: 2h)", "sentiment": "negative"},
        ]),
        # Month 14 — access review issues surface
        (15, 3, 9, 15, 9, 65.0, 7, [
            {"type": "control_updated", "title": "Access review completion dropped to 34% — escalation raised", "sentiment": "negative"},
            {"type": "signal_critical", "title": "Okta zero-day CVE published — immediate patch applied", "sentiment": "negative"},
        ]),
        # Month 15 — remediation underway
        (15, 3, 9, 15, 10, 67.0, 7, [
            {"type": "control_tested", "title": "Vulnerability management — all P1/P2 CVEs patched within SLA", "sentiment": "positive"},
        ]),
        # Month 16 — last month
        (15, 3, 9, 15, 10, 68.0, 7, [
            {"type": "milestone", "title": "DORA readiness: 72% — on track for January deadline", "sentiment": "positive"},
        ]),
        # Month 17 — current month
        (12, 4, 8, 15, 7, 65.0, 7, [
            {"type": "signal_critical", "title": "DNB sector-wide AML review announced for Q2 2026", "sentiment": "negative"},
            {"type": "control_updated", "title": "Access review recertification: 34% complete (127 overdue)", "sentiment": "negative"},
        ]),
    ]

    prev_snapshot: TimeMachineSnapshot | None = None

    for i, (total_risks, critical, high, total_controls, effective, coverage_pct, frameworks, events) in enumerate(MONTHS_DATA):
        month_date = start + relativedelta(months=i)
        month_str = month_date.strftime("%Y-%m")

        delta_risks    = total_risks    - (prev_snapshot.total_risks if prev_snapshot else 0)
        delta_controls = total_controls - (prev_snapshot.total_controls if prev_snapshot else 0)
        delta_coverage = coverage_pct   - (prev_snapshot.coverage_pct if prev_snapshot else 0.0)

        snapshot = TimeMachineSnapshot(
            org_id=org_id,
            snapshot_month=month_str,
            total_risks=total_risks,
            critical_risks=critical,
            high_risks=high,
            total_controls=total_controls,
            effective_controls=effective,
            coverage_pct=coverage_pct,
            frameworks_active=frameworks,
            open_audit_plans=1 if any(e["type"] == "audit_opened" for e in events) else 0,
            delta_risks=delta_risks,
            delta_coverage_pct=round(delta_coverage, 1),
            delta_controls=delta_controls,
            notable_events=events,
            risk_diff={
                "added": [f"Risk {j}" for j in range(max(0, delta_risks))],
                "changed": [],
                "removed": [],
            },
            control_diff={
                "added": [f"Control {j}" for j in range(max(0, delta_controls))],
                "changed": [],
                "removed": [],
            },
        )
        db.add(snapshot)
        prev_snapshot = snapshot

        # Write GRC events for significant months
        occurred = datetime(month_date.year, month_date.month, 15, 12, 0, 0, tzinfo=timezone.utc)
        for ev in events:
            sentiment_map = {
                "positive": GRCEventSentiment.positive,
                "negative": GRCEventSentiment.negative,
                "neutral":  GRCEventSentiment.neutral,
            }
            event_type_map = {
                "milestone":          GRCEventType.milestone,
                "control_tested":     GRCEventType.control_tested,
                "control_created":    GRCEventType.control_created,
                "control_updated":    GRCEventType.control_updated,
                "risk_created":       GRCEventType.risk_created,
                "risk_updated":       GRCEventType.risk_updated,
                "regulatory_inquiry": GRCEventType.regulatory_inquiry,
                "audit_opened":       GRCEventType.audit_opened,
                "audit_closed":       GRCEventType.audit_closed,
                "signal_critical":    GRCEventType.signal_critical,
                "certification":      GRCEventType.certification,
                "framework_added":    GRCEventType.framework_added,
                "coverage_changed":   GRCEventType.coverage_changed,
            }
            db.add(GRCEvent(
                org_id=org_id,
                event_type=event_type_map.get(ev["type"], GRCEventType.milestone),
                sentiment=sentiment_map.get(ev["sentiment"], GRCEventSentiment.neutral),
                title=ev["title"],
                entity_type=ev["type"].split("_")[0] if "_" in ev["type"] else "org",
                occurred_at=occurred,
            ))

    await db.commit()
