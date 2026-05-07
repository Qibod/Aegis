"""
app/api/routes/audit_copilot_route.py
────────────────────────────────────────
AI Co-Auditor — three-panel audit workspace.

Capabilities:
  Anomaly review   — AI discusses GL/JE anomalies in structured mode
  Work paper draft — AI populates section content in real-time
  Interview prep   — AI generates risk-mapped questions per finding
  Free query       — Open-ended engagement data analysis

Auto-seeds one demo engagement (Meridian FY2024 Revenue Audit) on first request.
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
    {"code": "WP-REV-01", "title": "Revenue Recognition — Planning Memo",         "area": "Revenue",  "status": WorkPaperStatus.approved,  "sort_order": 0},
    {"code": "WP-REV-02", "title": "Revenue by Product Line — Analytical Review",  "area": "Revenue",  "status": WorkPaperStatus.approved,  "sort_order": 1},
    {"code": "WP-REV-03", "title": "Journal Entry Testing — Q3-Q4 FY2024",        "area": "Revenue",  "status": WorkPaperStatus.in_review, "sort_order": 2},
    {"code": "WP-REV-04", "title": "Revenue Recognition — Substantive Testing",   "area": "Revenue",  "status": WorkPaperStatus.draft,     "sort_order": 3, "is_active": True},
    {"code": "WP-AML-01", "title": "AML Controls Effectiveness Testing",          "area": "AML",      "status": WorkPaperStatus.approved,  "sort_order": 4},
    {"code": "WP-CTRL-01", "title": "IT General Controls — Access & Change Mgmt", "area": "IT",       "status": WorkPaperStatus.in_review, "sort_order": 5},
    {"code": "WP-MGMT-01", "title": "Management Representation Letter",            "area": "Reporting","status": WorkPaperStatus.draft,     "sort_order": 6},
]

_SECTIONS = [
    {"title": "Objective & scope",  "status": WPSectionStatus.approved,
     "content": "To obtain sufficient appropriate evidence that revenue is recognised in accordance with IFRS 15 for the period January – December 2024. Scope includes all revenue streams exceeding EUR 500k individually, covering the retail deposits, institutional FX, and trade finance lines."},
    {"title": "Risk assessment",    "status": WPSectionStatus.approved,
     "content": "Inherent risk is assessed as high. Key risks identified: cut-off manipulation at period end, fictitious transactions through related-party channels, and revenue inflation via early recognition of multi-period contracts. Control risk is moderate — TM controls are in place but model validation is overdue."},
    {"title": "Anomaly findings",   "status": WPSectionStatus.empty,    "content": None},
    {"title": "Evidence & testing", "status": WPSectionStatus.empty,    "content": None},
    {"title": "Conclusions",        "status": WPSectionStatus.empty,    "content": None},
    {"title": "Sign-off & review",  "status": WPSectionStatus.empty,    "content": None},
]

_ANOMALIES = [
    {
        "title": "$2.1M revenue spike in November",
        "description": "Statistical outlier: November 2024 retail revenue is 34% above the trailing 6-month average. Three large transactions totalling €2.1M were booked on Nov 28-29 — the final two business days of the month. Journal entries were posted by a single operator (ID: FIN-0047) and reversed in the first week of December.",
        "severity": AnomalySeverity.high,
        "amount_label": "$2.1M",
        "account_ref": "GL-7000 · Retail Revenue",
        "period": "Q3-Q4 FY2024",
        "assertion": "cutoff",
    },
    {
        "title": "Unauthorised journal entry reversal — Dec 29",
        "description": "A journal entry reversal of €840k was posted on December 29 at 23:47 local time, outside normal business hours. The approver field contains the same user ID as the preparer (FIN-0047), indicating a segregation of duties breach. No supporting documentation found in the evidence vault.",
        "severity": AnomalySeverity.high,
        "amount_label": "€840k",
        "account_ref": "GL-7000 · GL-4510",
        "period": "Q4 FY2024",
        "assertion": "authorization",
    },
    {
        "title": "180-day payment terms — non-standard contracts",
        "description": "Eight contracts with payment terms of 180+ days represent €3.4M of revenue recognised in H2 FY2024. Standard terms are 30-60 days. Contracts lack approval signatures from the Head of Credit. Revenue recognition at contract inception may not be appropriate where collectability is uncertain.",
        "severity": AnomalySeverity.medium,
        "amount_label": "€3.4M",
        "account_ref": "GL-7200 · Contract Revenue",
        "period": "H2 FY2024",
        "assertion": "occurrence",
    },
    {
        "title": "Q4 accrual spike — top-side entries",
        "description": "Management top-side accruals in Q4 total €1.2M, representing 180% of the Q3 accrual balance. Accruals were posted on December 31 without underlying contracts or delivery evidence. The pattern is inconsistent with Q1-Q3 accrual behaviour and warrants substantive testing.",
        "severity": AnomalySeverity.medium,
        "amount_label": "€1.2M",
        "account_ref": "GL-2300 · Accrued Revenue",
        "period": "Q4 FY2024",
        "assertion": "completeness",
    },
]

_INTERVIEW_QUESTIONS = [
    # Controller questions (WP-REV-04)
    {"question": "Can you walk me through the revenue recognition process for orders booked in November?", "risk_level": "high",   "assertion": "cutoff",         "target_role": "Controller"},
    {"question": "What triggered the journal entry reversal on December 29 — who approved it?",          "risk_level": "high",   "assertion": "authorization",  "target_role": "Controller"},
    {"question": "Are 180-day payment terms standard policy, or individually negotiated?",               "risk_level": "medium", "assertion": "occurrence",     "target_role": "Controller"},
    {"question": "Who has access to post top-side journal entries after the system cut-off?",            "risk_level": "high",   "assertion": "authorization",  "target_role": "Controller"},
    {"question": "How does the finance team determine when multi-period contracts are fully earned?",     "risk_level": "high",   "assertion": "cutoff",         "target_role": "Controller"},
    {"question": "What controls exist to prevent revenue being recognised before goods are delivered?",   "risk_level": "medium", "assertion": "occurrence",     "target_role": "Controller"},
    # CFO questions
    {"question": "Can you explain the rationale for the November revenue uplift compared to prior months?", "risk_level": "high",   "assertion": "cutoff",       "target_role": "CFO"},
    {"question": "Were the board or audit committee informed of the December reversal at the time?",        "risk_level": "high",   "assertion": "authorization", "target_role": "CFO"},
    # IT Manager questions
    {"question": "What system controls prevent a single user from both preparing and approving a JE?",   "risk_level": "high",   "assertion": "authorization",  "target_role": "IT Manager"},
    {"question": "Are after-hours journal entry postings flagged automatically for management review?",   "risk_level": "medium", "assertion": "authorization",  "target_role": "IT Manager"},
    {"question": "What is the audit trail retention period for GL posting activity?",                    "risk_level": "medium", "assertion": "completeness",   "target_role": "IT Manager"},
    {"question": "Can the system restrict posting to authorised users only during period-end close?",    "risk_level": "medium", "assertion": "authorization",  "target_role": "IT Manager"},
]


async def _seed_engagement(org_id: UUID, db: AsyncSession) -> AuditEngagement:
    """Create the demo Meridian FY2024 Revenue Audit engagement."""
    eng = AuditEngagement(
        org_id=org_id,
        name="FY2024 Revenue Audit",
        phase="Phase 2",
        client_name="Meridian Group",
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
