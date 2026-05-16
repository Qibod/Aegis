"""
app/api/routes/audit_copilot_route.py
────────────────────────────────────────
AI Co-Auditor — three-panel audit workspace.

Capabilities:
  Anomaly review   — AI discusses GL/JE anomalies in structured mode
  Work paper draft — AI populates section content in real-time
  Interview prep   — AI generates risk-mapped questions per finding
  Free query       — Open-ended engagement data analysis

Auto-seeds one demo engagement (Uber Technologies FY2024 Revenue Audit) on first request.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_org_id
from app.config import get_settings
from app.database import get_db
from app.models import (
    AuditEngagement, EngagementStatus,
    CopilotWorkPaper, WorkPaperStatus,
    WPSection, WPSectionStatus,
    EngagementAnomaly, AnomalySeverity,
    InterviewQuestion,
    Organization,
)

settings = get_settings()
claude = AsyncAnthropic(api_key=settings.anthropic_api_key)
router = APIRouter(prefix="/audit-copilot", tags=["audit-copilot"])


# ─────────────────────────────────────────────────────────────────────────────
# Demo seed — executed once per org on first GET /engagements
# ─────────────────────────────────────────────────────────────────────────────

_WORK_PAPERS = [
    {"code": "WP-REV-01", "title": "Revenue Recognition — Planning Memo",              "area": "Revenue",   "status": WorkPaperStatus.approved,  "sort_order": 0},
    {"code": "WP-REV-02", "title": "Mobility & Delivery Take Rate — Analytical Review","area": "Revenue",   "status": WorkPaperStatus.approved,  "sort_order": 1},
    {"code": "WP-REV-03", "title": "Journal Entry Testing — Q3-Q4 FY2024",             "area": "Revenue",   "status": WorkPaperStatus.in_review, "sort_order": 2},
    {"code": "WP-REV-04", "title": "Revenue Recognition — Substantive Testing",        "area": "Revenue",   "status": WorkPaperStatus.draft,     "sort_order": 3, "is_active": True},
    {"code": "WP-FRD-01", "title": "Payment Fraud & Promo Abuse Controls Testing",     "area": "Fraud",     "status": WorkPaperStatus.approved,  "sort_order": 4},
    {"code": "WP-CTRL-01", "title": "IT General Controls — Access & Change Mgmt",      "area": "IT",        "status": WorkPaperStatus.in_review, "sort_order": 5},
    {"code": "WP-MGMT-01", "title": "Management Representation Letter",                 "area": "Reporting", "status": WorkPaperStatus.draft,     "sort_order": 6},
]

_SECTIONS = [
    {"title": "Objective & scope",  "status": WPSectionStatus.approved,
     "content": "To obtain sufficient appropriate evidence that Uber Technologies recognises revenue in accordance with ASC 606 for the period January – December 2024. Scope includes all revenue streams exceeding $50M individually: Mobility (ride-hailing commission / service fee), Delivery (Eats take rate and delivery fee), and Freight (brokerage margin). Excludes driver incentive contra-revenue, which is covered in WP-REV-02."},
    {"title": "Risk assessment",    "status": WPSectionStatus.approved,
     "content": "Inherent risk is assessed as high. Key risks: (1) Cut-off manipulation — Mobility trips initiated near period end may span two reporting periods; (2) Take-rate accuracy — changes to commission algorithms in Q3 created risk of misstatement in Eats revenue; (3) Freight revenue netting — gross vs net presentation of carrier payments requires assessment under ASC 606 principal/agent guidance. Control risk is moderate — automated billing reconciliation is in place but the Q3 algorithm change was not subject to financial close review."},
    {"title": "Anomaly findings",   "status": WPSectionStatus.empty,    "content": None},
    {"title": "Evidence & testing", "status": WPSectionStatus.empty,    "content": None},
    {"title": "Conclusions",        "status": WPSectionStatus.empty,    "content": None},
    {"title": "Sign-off & review",  "status": WPSectionStatus.empty,    "content": None},
]

_ANOMALIES = [
    {
        "title": "$47M Eats take-rate spike — Q3 algorithm change",
        "description": "Uber Eats gross take rate increased from 22.4% to 26.1% in Q3 2024 following an undocumented pricing algorithm update deployed on July 14. The change was not reviewed by Finance before deployment. Revenue for Q3 is $47M higher than the extrapolated run-rate from H1. Three markets (CA, NY, TX) account for 71% of the variance. Journal entries reflect the higher take rate but no supporting change-control documentation was found in the evidence vault.",
        "severity": AnomalySeverity.high,
        "amount_label": "$47M",
        "account_ref": "GL-4200 · Delivery Revenue",
        "period": "Q3 FY2024",
        "assertion": "accuracy",
    },
    {
        "title": "Unauthorised journal entry — Freight revenue reclassification, Dec 28",
        "description": "A manual journal entry reclassifying $18.4M of Freight gross bookings from net (brokerage fee) to gross (carrier payment + margin) presentation was posted on December 28 at 22:13 local time, outside normal business hours. The preparer and approver field contain the same user ID (FIN-1134), indicating a segregation of duties breach. Reclassification inflates reported revenue by $14.2M net of carrier costs. No ASC 606 principal/agent memo was found to support gross presentation.",
        "severity": AnomalySeverity.high,
        "amount_label": "$14.2M",
        "account_ref": "GL-4400 · Freight Revenue",
        "period": "Q4 FY2024",
        "assertion": "authorization",
    },
    {
        "title": "Driver incentive contra-revenue under-accrual — Q4",
        "description": "Driver earnings guarantees and surge bonuses paid in Q4 total $312M per payroll records, versus $267M accrued as contra-revenue in the general ledger — a $45M shortfall. Under ASC 606, payments to platform participants (drivers) that create a material right should reduce transaction price. The under-accrual overstates net revenue. Finance management attributes the gap to a forecasting model error identified post-close.",
        "severity": AnomalySeverity.medium,
        "amount_label": "$45M",
        "account_ref": "GL-4010 · Driver Incentives (contra-revenue)",
        "period": "Q4 FY2024",
        "assertion": "completeness",
    },
    {
        "title": "Promo code abuse — $8.3M in fraudulent new-user credits",
        "description": "Data analytics identified 214,000 new-user promo redemptions in FY2024 that share device fingerprints with existing accounts, indicating synthetic-identity abuse. Associated promotional credits of $8.3M were recorded as sales and marketing expense rather than contra-revenue. Misclassification has no P&L impact but overstates gross revenue and marketing spend, affecting segment KPIs presented to the Board.",
        "severity": AnomalySeverity.medium,
        "amount_label": "$8.3M",
        "account_ref": "GL-6100 · Sales & Marketing / GL-4000 · Gross Revenue",
        "period": "H1-H2 FY2024",
        "assertion": "classification",
    },
]

_INTERVIEW_QUESTIONS = [
    # Controller questions (WP-REV-04)
    {"question": "Can you walk us through the July 14 algorithm change — what approval process was followed before deployment?", "risk_level": "high",   "assertion": "accuracy",       "target_role": "Controller"},
    {"question": "Who authorised the December 28 Freight revenue reclassification, and where is the ASC 606 principal/agent memo?", "risk_level": "high", "assertion": "authorization", "target_role": "Controller"},
    {"question": "How does Finance verify that driver incentive accruals match payroll actuals at each quarter-end?",            "risk_level": "high",   "assertion": "completeness",   "target_role": "Controller"},
    {"question": "What controls exist to prevent a single user from both preparing and approving a manual journal entry?",        "risk_level": "high",   "assertion": "authorization",  "target_role": "Controller"},
    {"question": "How are after-hours journal entries flagged for management review before the books are closed?",                "risk_level": "high",   "assertion": "authorization",  "target_role": "Controller"},
    {"question": "What is the threshold for Finance sign-off on product or pricing algorithm changes that affect revenue?",       "risk_level": "medium", "assertion": "accuracy",       "target_role": "Controller"},
    # CFO questions
    {"question": "Were the Audit Committee or Board informed of the Q3 take-rate variance when it was first identified?",        "risk_level": "high",   "assertion": "accuracy",       "target_role": "CFO"},
    {"question": "What is management's position on the Freight gross vs net presentation, and has outside counsel reviewed it?", "risk_level": "high",   "assertion": "authorization",  "target_role": "CFO"},
    # VP Engineering / IT
    {"question": "Does the pricing algorithm deployment pipeline include a mandatory Finance review gate before production release?", "risk_level": "high",   "assertion": "accuracy",      "target_role": "VP Engineering"},
    {"question": "What audit trail is retained for algorithm parameter changes — version history, approval records, rollback logs?",  "risk_level": "medium", "assertion": "completeness",  "target_role": "VP Engineering"},
    {"question": "How does the system enforce segregation of duties for ERP journal entry posting and approval?",                     "risk_level": "high",   "assertion": "authorization", "target_role": "VP Engineering"},
    {"question": "Can the ERP restrict manual journal entries to authorised users only during the period-end close window?",          "risk_level": "medium", "assertion": "authorization", "target_role": "VP Engineering"},
]


async def _seed_engagement(org_id: UUID, db: AsyncSession) -> AuditEngagement:
    """Create the demo Uber Technologies FY2024 Revenue Audit engagement."""
    eng = AuditEngagement(
        org_id=org_id,
        name="FY2024 Revenue Audit",
        phase="Phase 2",
        client_name="Uber Technologies, Inc.",
        period="FY2024",
        status=EngagementStatus.active,
    )
    db.add(eng)
    await db.flush()

    # Work papers
    wp_active: CopilotWorkPaper | None = None
    for i, wpd in enumerate(_WORK_PAPERS):
        is_active = wpd.pop("is_active", False)
        wp = CopilotWorkPaper(engagement_id=eng.id, **wpd)
        wp.is_active = is_active
        db.add(wp)
        await db.flush()
        if is_active:
            wp_active = wp
            for j, sd in enumerate(_SECTIONS):
                sec = WPSection(work_paper_id=wp.id, sort_order=j, **sd)
                db.add(sec)
            await db.flush()
            for k, qd in enumerate(_INTERVIEW_QUESTIONS):
                q = InterviewQuestion(engagement_id=eng.id, work_paper_id=wp.id, sort_order=k, **qd)
                db.add(q)
        wpd["is_active"] = is_active  # restore for any re-use

    # Anomalies
    for ad in _ANOMALIES:
        a = EngagementAnomaly(engagement_id=eng.id, **ad)
        db.add(a)

    await db.commit()
    return eng


# ─────────────────────────────────────────────────────────────────────────────
# Serialisation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _section_dict(s: WPSection) -> dict:
    return {
        "id": str(s.id), "title": s.title,
        "content": s.content, "status": s.status.value, "sort_order": s.sort_order,
    }

def _wp_dict(wp: CopilotWorkPaper) -> dict:
    return {
        "id": str(wp.id), "code": wp.code, "title": wp.title,
        "area": wp.area, "status": wp.status.value,
        "is_active": wp.is_active, "sort_order": wp.sort_order,
        "sections": [_section_dict(s) for s in (wp.sections or [])],
        "question_count": len(wp.questions or []),
    }

def _anomaly_dict(a: EngagementAnomaly) -> dict:
    return {
        "id": str(a.id), "title": a.title, "description": a.description,
        "severity": a.severity.value, "amount_label": a.amount_label,
        "account_ref": a.account_ref, "period": a.period,
        "assertion": a.assertion, "is_addressed": a.is_addressed,
    }

def _question_dict(q: InterviewQuestion) -> dict:
    return {
        "id": str(q.id), "question": q.question,
        "risk_level": q.risk_level, "assertion": q.assertion,
        "target_role": q.target_role, "sort_order": q.sort_order,
    }

def _engagement_dict(eng: AuditEngagement) -> dict:
    anomalies = [_anomaly_dict(a) for a in (eng.anomalies or [])]
    return {
        "id": str(eng.id),
        "name": eng.name,
        "phase": eng.phase,
        "client_name": eng.client_name,
        "period": eng.period,
        "status": eng.status.value,
        "work_paper_count": len(eng.work_papers or []),
        "anomaly_count": len(anomalies),
        "open_anomaly_count": sum(1 for a in anomalies if not a["is_addressed"]),
        "work_papers": [_wp_dict(wp) for wp in (eng.work_papers or [])],
        "anomalies": anomalies,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Mode-aware system prompts
# ─────────────────────────────────────────────────────────────────────────────

_BASE_SYSTEM = """You are an AI co-auditor embedded in the Aegis GRC platform. You assist \
qualified auditors on live engagements — you are not a generic chatbot. You have access to the \
engagement's work papers, GL anomaly data, and evidence.

Style:
- Authoritative, concise, IIA-standard language. No filler.
- Numbers always include units (EUR/USD, %, dates).
- When you identify a finding: state Condition, Criterion, Cause, Effect in that order.
- Always flag if a response requires auditor judgment vs. objective analysis.
"""

_MODE_CONTEXTS = {
    "anomaly_review": """You are in Anomaly Review mode. Your role is to discuss statistical anomalies \
detected in GL data, journal entries, and trial balances. Walk the auditor through findings, explain \
the significance of each, and suggest follow-up procedures. When presenting anomalies, be specific about \
amounts, account references, and the audit assertion at risk.""",

    "draft_workpaper": """You are in Work Paper Drafting mode. Draft structured work paper content using \
IIA standards. Fill sections with evidence-based language. Use objective, past-tense, third-person voice. \
When drafting findings, follow the criteria-condition-cause-effect-recommendation structure. \
Sections should be ready for audit committee review with no further editing needed.""",

    "interview_prep": """You are in Interview Preparation mode. Generate structured interview questions \
mapped to specific audit assertions (occurrence, completeness, cutoff, authorization, accuracy, classification). \
Rank questions by risk level. Include follow-up probes for high-risk areas. Questions should challenge \
management controls without being confrontational.""",

    "free_query": """You are in Free Query mode. Answer any question about the engagement data, \
prior year comparisons, regulatory requirements, or audit methodology. You have access to all \
engagement context. Be direct and evidence-based.""",
}


async def _chat_with_claude(
    mode: str,
    message: str,
    engagement_ctx: dict,
    history: list[dict],
) -> dict[str, Any]:
    """Single Claude call with mode-aware context."""

    mode_ctx = _MODE_CONTEXTS.get(mode, _MODE_CONTEXTS["free_query"])
    system = _BASE_SYSTEM + "\n\n" + mode_ctx

    # Build context block
    anomalies_text = "\n".join(
        f"  [{a['severity'].upper()}] {a['title']} | {a['amount_label'] or ''} | {a['account_ref'] or ''} | Assertion: {a['assertion']}"
        for a in engagement_ctx.get("anomalies", [])
    )
    engagement_block = f"""
ENGAGEMENT: {engagement_ctx.get('client_name')} · {engagement_ctx.get('name')} · {engagement_ctx.get('phase')}
PERIOD: {engagement_ctx.get('period')}

ANOMALIES DETECTED ({engagement_ctx.get('open_anomaly_count', 0)} open):
{anomalies_text or 'None'}

ACTIVE WORK PAPER: {next((wp['code'] + ' — ' + wp['title'] for wp in engagement_ctx.get('work_papers', []) if wp['is_active']), 'None')}
SECTION STATUS: {', '.join(s['title'] + '=' + s['status'] for wp in engagement_ctx.get('work_papers', []) if wp['is_active'] for s in wp['sections'])}
"""

    messages = [
        *[{"role": m["role"], "content": m["content"]} for m in history[-12:]],
        {"role": "user", "content": f"[Engagement context]\n{engagement_block}\n\n[Auditor message]\n{message}"},
    ]

    resp = await claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=system,
        messages=messages,
    )
    text = resp.content[0].text.strip()

    # Detect if response references anomalies — return structured flag
    refs_anomaly = any(
        kw in text.lower() for kw in ("anomaly", "spike", "reversal", "journal entry", "outlier", "$2", "€", "840")
    )

    return {
        "response": text,
        "refs_anomaly": refs_anomaly,
        "mode": mode,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

async def _get_or_seed_engagement(org_id: UUID, db: AsyncSession) -> AuditEngagement:
    result = await db.execute(
        select(AuditEngagement)
        .where(AuditEngagement.org_id == org_id)
        .options(
            selectinload(AuditEngagement.work_papers)
                .selectinload(CopilotWorkPaper.sections),
            selectinload(AuditEngagement.work_papers)
                .selectinload(CopilotWorkPaper.questions),
            selectinload(AuditEngagement.anomalies),
        )
        .order_by(AuditEngagement.created_at.desc())
        .limit(1)
    )
    eng = result.scalar_one_or_none()
    if not eng:
        eng = await _seed_engagement(org_id, db)
        # Re-fetch with relationships
        result2 = await db.execute(
            select(AuditEngagement)
            .where(AuditEngagement.id == eng.id)
            .options(
                selectinload(AuditEngagement.work_papers)
                    .selectinload(CopilotWorkPaper.sections),
                selectinload(AuditEngagement.work_papers)
                    .selectinload(CopilotWorkPaper.questions),
                selectinload(AuditEngagement.anomalies),
            )
        )
        eng = result2.scalar_one()
    return eng


@router.get("/engagements")
async def list_engagements(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    eng = await _get_or_seed_engagement(org_id, db)
    return [_engagement_dict(eng)]


@router.get("/engagements/{engagement_id}")
async def get_engagement(
    engagement_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AuditEngagement)
        .where(AuditEngagement.id == engagement_id, AuditEngagement.org_id == org_id)
        .options(
            selectinload(AuditEngagement.work_papers)
                .selectinload(CopilotWorkPaper.sections),
            selectinload(AuditEngagement.work_papers)
                .selectinload(CopilotWorkPaper.questions),
            selectinload(AuditEngagement.anomalies),
        )
    )
    eng = result.scalar_one_or_none()
    if not eng:
        raise HTTPException(404, "Engagement not found")
    return _engagement_dict(eng)


@router.post("/engagements/{engagement_id}/chat")
async def co_auditor_chat(
    engagement_id: UUID,
    payload: dict,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    """Mode-aware co-auditor chat. Returns AI response + optional actions."""
    eng = await _get_or_seed_engagement(org_id, db)
    if str(eng.id) != str(engagement_id):
        raise HTTPException(404)

    mode    = payload.get("mode", "free_query")
    message = payload.get("message", "")
    history = payload.get("history", [])

    ctx = _engagement_dict(eng)
    result = await _chat_with_claude(mode, message, ctx, history)
    return result


@router.patch("/sections/{section_id}")
async def update_section(
    section_id: UUID,
    payload: dict,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    """Update a work paper section's content and/or status."""
    # Verify ownership via join
    result = await db.execute(
        select(WPSection)
        .join(CopilotWorkPaper, WPSection.work_paper_id == CopilotWorkPaper.id)
        .join(AuditEngagement, CopilotWorkPaper.engagement_id == AuditEngagement.id)
        .where(WPSection.id == section_id, AuditEngagement.org_id == org_id)
    )
    sec = result.scalar_one_or_none()
    if not sec:
        raise HTTPException(404)

    if "content" in payload:
        sec.content = payload["content"]
    if "status" in payload:
        sec.status = WPSectionStatus(payload["status"])

    await db.commit()
    await db.refresh(sec)
    return _section_dict(sec)


@router.post("/anomalies/{anomaly_id}/to-workpaper")
async def push_anomaly_to_workpaper(
    anomaly_id: UUID,
    payload: dict,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    """
    AI-drafts the 'Anomaly findings' section using a selected anomaly.
    Updates the section status to ai_drafting → drafted.
    """
    eng = await _get_or_seed_engagement(org_id, db)

    # Get anomaly
    anomaly = next((a for a in eng.anomalies if str(a.id) == str(anomaly_id)), None)
    if not anomaly:
        raise HTTPException(404, "Anomaly not found")

    # Find the active work paper's "Anomaly findings" section
    target_sec: WPSection | None = None
    for wp in eng.work_papers:
        if wp.is_active:
            for s in wp.sections:
                if "anomaly" in s.title.lower() or "finding" in s.title.lower():
                    target_sec = s
                    break

    if not target_sec:
        raise HTTPException(400, "No anomaly findings section found in active work paper")

    # Mark as drafting immediately
    target_sec.status = WPSectionStatus.ai_drafting
    await db.commit()

    # Generate draft content via Claude
    prompt = f"""Draft the 'Anomaly Findings' section for a work paper based on this finding:

Finding: {anomaly.title}
Detail: {anomaly.description}
Amount: {anomaly.amount_label or 'N/A'}
Account: {anomaly.account_ref or 'N/A'}
Period: {anomaly.period or 'N/A'}
Audit assertion at risk: {anomaly.assertion or 'N/A'}
Severity: {anomaly.severity.value}

Write 3-4 concise paragraphs in IIA work paper style. Use Condition / Criterion / Cause / Effect structure.
Include recommended management action. Do not use headings — continuous prose only. Past tense, third person."""

    resp = await claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=600,
        system=_BASE_SYSTEM + "\n\n" + _MODE_CONTEXTS["draft_workpaper"],
        messages=[{"role": "user", "content": prompt}],
    )
    draft_content = resp.content[0].text.strip()

    # Re-fetch and update
    result2 = await db.execute(select(WPSection).where(WPSection.id == target_sec.id))
    sec = result2.scalar_one()
    sec.content = draft_content
    sec.status  = WPSectionStatus.drafted
    anomaly.is_addressed = True
    await db.commit()
    await db.refresh(sec)

    return {"section": _section_dict(sec), "anomaly_id": str(anomaly_id)}


@router.get("/engagements/{engagement_id}/questions")
async def get_interview_questions(
    engagement_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    target_role: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    eng = await _get_or_seed_engagement(org_id, db)
    questions = []
    for wp in eng.work_papers:
        if wp.is_active:
            for q in wp.questions:
                if target_role is None or q.target_role == target_role:
                    questions.append(_question_dict(q))
    return questions
