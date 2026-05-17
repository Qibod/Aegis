"""
app/api/routes/regulatory_route.py
────────────────────────────────────
Regulatory Change Agent — five-stage AI pipeline.

Endpoints:
  GET  /regulatory/changes              → paginated change feed
  GET  /regulatory/changes/{id}         → single change + tasks
  POST /regulatory/changes/{id}/assess  → (re)generate AI impact assessment
  PATCH /regulatory/tasks/{id}          → update task status
  POST /regulatory/dismiss/{id}         → dismiss a change
  GET  /regulatory/deadlines            → upcoming deadlines strip
  POST /regulatory/simulate-update      → inject a simulated live update
  POST /regulatory/seed                 → seed initial changes for demo
"""
from __future__ import annotations

import json
import random
import string
from datetime import datetime, timezone, timedelta
from typing import Annotated, Any
from uuid import UUID

from anthropic import AsyncAnthropic
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import OrgProfileContext, build_org_profile_context, format_context_for_prompt
from app.api.auth import get_current_active_user, get_org_id
from app.config import get_settings
from app.database import get_db
from app.models import (
    Control, Framework, Organization, User,
    RegulatoryChange, RegChangeTask,
    RegChangeSeverity, RegChangePipelineStage, RegChangeTaskStatus,
)

router  = APIRouter(prefix="/regulatory", tags=["regulatory"])
settings = get_settings()
claude  = AsyncAnthropic(api_key=settings.anthropic_api_key)

# ── Pydantic schemas ───────────────────────────────────────────────────────────

class TaskOut(BaseModel):
    id: str
    phase: int
    phase_label: str | None
    label: str
    role: str | None
    status: str
    is_priority: bool
    sort_order: int
    due_week: int | None

    class Config:
        from_attributes = True


class ChangeOut(BaseModel):
    id: str
    source: str
    source_url: str | None
    regulation_family: str | None
    jurisdiction: str | None
    title: str
    summary: str | None
    severity: str
    relevance_score: float
    pipeline_stage: str
    deadline_at: str | None
    deadline_label: str | None
    impact_assessment: str | None
    matched_controls: list[dict[str, Any]]
    tags: list[str]
    is_new: bool
    is_dismissed: bool
    published_at: str
    tasks: list[TaskOut]


class ChangeListItem(BaseModel):
    id: str
    source: str
    regulation_family: str | None
    title: str
    summary: str | None
    severity: str
    pipeline_stage: str
    deadline_label: str | None
    tags: list[str]
    is_new: bool
    published_at: str
    task_total: int
    task_done: int


class ChangeListResponse(BaseModel):
    items: list[ChangeListItem]
    total: int
    counts: dict[str, int]


class DeadlineOut(BaseModel):
    change_id: str
    title: str
    regulation_family: str | None
    severity: str
    deadline_at: str
    deadline_label: str | None
    days_remaining: int


class TaskPatchRequest(BaseModel):
    status: str


# ── GET /regulatory/changes ────────────────────────────────────────────────────

@router.get("/changes", response_model=ChangeListResponse)
async def list_changes(
    org_id: Annotated[UUID, Depends(get_org_id)],
    severity: str | None = None,
    regulation: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(RegulatoryChange).where(
        RegulatoryChange.org_id == org_id,
        RegulatoryChange.is_dismissed == False,
    )
    if severity:
        q = q.where(RegulatoryChange.severity == severity)
    if regulation:
        q = q.where(RegulatoryChange.regulation_family == regulation)

    rows = (await db.execute(
        q.options(selectinload(RegulatoryChange.tasks))
        .order_by(
            desc(RegulatoryChange.severity == RegChangeSeverity.critical),
            desc(RegulatoryChange.severity == RegChangeSeverity.high),
            desc(RegulatoryChange.published_at),
        )
    )).scalars().all()

    # Auto-seed if empty — use org profile context to filter relevant changes
    if not rows:
        org_context = await build_org_profile_context(org_id, db)
        await _seed_initial_changes(org_id, db, org_context)
        rows = (await db.execute(
            q.options(selectinload(RegulatoryChange.tasks))
            .order_by(desc(RegulatoryChange.published_at))
        )).scalars().all()

    counts = {
        "critical": sum(1 for r in rows if r.severity == RegChangeSeverity.critical),
        "high":     sum(1 for r in rows if r.severity == RegChangeSeverity.high),
        "new":      sum(1 for r in rows if r.is_new),
    }

    items = [
        ChangeListItem(
            id=str(r.id),
            source=r.source,
            regulation_family=r.regulation_family,
            title=r.title,
            summary=r.summary,
            severity=r.severity.value,
            pipeline_stage=r.pipeline_stage.value,
            deadline_label=r.deadline_label,
            tags=r.tags or [],
            is_new=r.is_new,
            published_at=r.published_at.isoformat(),
            task_total=len(r.tasks),
            task_done=sum(1 for t in r.tasks if t.status == RegChangeTaskStatus.done),
        )
        for r in rows
    ]

    return ChangeListResponse(items=items, total=len(items), counts=counts)


# ── GET /regulatory/changes/{id} ──────────────────────────────────────────────

@router.get("/changes/{change_id}", response_model=ChangeOut)
async def get_change(
    change_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(
        select(RegulatoryChange)
        .where(RegulatoryChange.id == change_id, RegulatoryChange.org_id == org_id)
        .options(selectinload(RegulatoryChange.tasks))
    )).scalar_one_or_none()

    if not row:
        raise HTTPException(404, "Change not found")

    # Mark as read
    if row.is_new:
        row.is_new = False
        await db.commit()

    return _to_change_out(row)


# ── POST /regulatory/changes/{id}/assess ──────────────────────────────────────

@router.post("/changes/{change_id}/assess", response_model=ChangeOut)
async def assess_change(
    change_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    _: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    """Run Claude impact assessment and action plan generation for a change."""
    row = (await db.execute(
        select(RegulatoryChange)
        .where(RegulatoryChange.id == change_id, RegulatoryChange.org_id == org_id)
        .options(selectinload(RegulatoryChange.tasks))
    )).scalar_one_or_none()

    if not row:
        raise HTTPException(404, "Change not found")

    # Load controls and company profile context
    controls = (await db.execute(
        select(Control).where(Control.org_id == org_id)
    )).scalars().all()

    org_context = await build_org_profile_context(org_id, db)

    # Run AI assessment
    assessment, matched, tasks_data = await _run_ai_assessment(row, controls, org_context)

    row.impact_assessment = assessment
    row.matched_controls  = matched
    row.pipeline_stage    = RegChangePipelineStage.assessed

    # Replace tasks
    for t in list(row.tasks):
        await db.delete(t)
    await db.flush()

    for i, td in enumerate(tasks_data):
        db.add(RegChangeTask(
            change_id=row.id,
            phase=td["phase"],
            phase_label=td["phase_label"],
            label=td["label"],
            role=td.get("role"),
            is_priority=td.get("is_priority", False),
            sort_order=i,
            due_week=td.get("due_week"),
        ))

    row.pipeline_stage = RegChangePipelineStage.actioned
    await db.commit()
    row = (await db.execute(
        select(RegulatoryChange)
        .where(RegulatoryChange.id == row.id)
        .options(selectinload(RegulatoryChange.tasks))
    )).scalar_one()
    return _to_change_out(row)


# ── PATCH /regulatory/tasks/{id} ──────────────────────────────────────────────

@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: UUID,
    payload: TaskPatchRequest,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    task = (await db.execute(
        select(RegChangeTask).where(RegChangeTask.id == task_id)
    )).scalar_one_or_none()

    if not task:
        raise HTTPException(404, "Task not found")

    # Verify org ownership via parent change
    change = (await db.execute(
        select(RegulatoryChange).where(
            RegulatoryChange.id == task.change_id,
            RegulatoryChange.org_id == org_id,
        )
    )).scalar_one_or_none()
    if not change:
        raise HTTPException(403, "Not authorised")

    task.status = payload.status
    await db.commit()
    await db.refresh(task)
    return TaskOut(
        id=str(task.id), phase=task.phase, phase_label=task.phase_label,
        label=task.label, role=task.role, status=task.status.value,
        is_priority=task.is_priority, sort_order=task.sort_order, due_week=task.due_week,
    )


# ── POST /regulatory/dismiss/{id} ─────────────────────────────────────────────

@router.post("/dismiss/{change_id}")
async def dismiss_change(
    change_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(
        select(RegulatoryChange)
        .where(RegulatoryChange.id == change_id, RegulatoryChange.org_id == org_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Change not found")
    row.is_dismissed = True
    await db.commit()
    return {"ok": True}


# ── GET /regulatory/deadlines ─────────────────────────────────────────────────

@router.get("/deadlines", response_model=list[DeadlineOut])
async def get_deadlines(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    rows = (await db.execute(
        select(RegulatoryChange)
        .where(
            RegulatoryChange.org_id == org_id,
            RegulatoryChange.deadline_at.isnot(None),
            RegulatoryChange.is_dismissed == False,
        )
        .order_by(RegulatoryChange.deadline_at)
    )).scalars().all()

    return [
        DeadlineOut(
            change_id=str(r.id),
            title=r.title,
            regulation_family=r.regulation_family,
            severity=r.severity.value,
            deadline_at=r.deadline_at.isoformat(),
            deadline_label=r.deadline_label,
            days_remaining=max(0, (r.deadline_at - now).days),
        )
        for r in rows
    ]


# ── POST /regulatory/simulate-update ─────────────────────────────────────────

# Pool of "live" simulated changes
_LIVE_CHANGES = [
    {
        "source": "SEC", "regulation_family": "SEC Enforcement",
        "jurisdiction": "US", "severity": "high",
        "title": "SEC charges fintech lender with misleading AI-based credit decisions",
        "summary": "SEC brings first enforcement action under the AI Credit Disclosure Rule against a fintech using unexplained automated decisions. Precedent alert for EU firms with US institutional exposure.",
        "deadline_label": "Immediate review",
        "deadline_days": 14,
        "tags": ["AI Act", "Credit", "Enforcement"],
        "external_id_prefix": "sec-ai-credit",
        "impact_assessment": "This SEC action establishes a precedent directly relevant to your credit scoring ML model under EU AI Act Article 10. While US jurisdiction limits direct exposure, EU regulators have cited SEC AI enforcement actions in shaping their own enforcement priorities. Your current model risk governance framework covers 4 of 8 required AI Act disclosures. Recommend commissioning an independent algorithmic audit within 30 days.",
        "matched_controls": [
            {"control_name": "AI Model Risk Governance Framework", "gap_type": "Partial gap", "severity": "high"},
            {"control_name": "KYC / Customer Due Diligence Engine", "gap_type": "Review required", "severity": "medium"},
        ],
        "tasks": [
            {"phase": 1, "phase_label": "Immediate review", "label": "Brief ExCo on SEC precedent and EU AI Act exposure", "role": "Compliance", "is_priority": True, "due_week": 1},
            {"phase": 1, "phase_label": "Immediate review", "label": "Map current credit model disclosures against EU AI Act Art.13 requirements", "role": "Legal", "is_priority": True, "due_week": 1},
            {"phase": 2, "phase_label": "Gap remediation", "label": "Commission independent algorithmic bias audit", "role": "Compliance", "due_week": 3},
            {"phase": 2, "phase_label": "Gap remediation", "label": "Draft model explainability documentation for declined applicants", "role": "IT", "due_week": 4},
            {"phase": 3, "phase_label": "Evidence packaging", "label": "Update model risk register with EU AI Act classification", "role": "Audit", "due_week": 6},
        ],
    },
    {
        "source": "ENISA", "regulation_family": "NIS2",
        "jurisdiction": "EU", "severity": "high",
        "title": "ENISA publishes NIS2 technical implementation guidance — incident reporting timelines clarified",
        "summary": "ENISA releases binding technical standards clarifying the 24-hour early warning and 72-hour incident report requirements under NIS2. Financial entities must align ICT incident response procedures immediately.",
        "deadline_label": "30 days",
        "deadline_days": 30,
        "tags": ["NIS2", "DORA", "Incident response"],
        "external_id_prefix": "enisa-nis2-incident",
        "impact_assessment": "The ENISA guidance aligns with DORA's ICT incident reporting requirements, creating overlapping obligations. Your current business continuity and DR testing control covers DORA but does not yet reflect NIS2's specific 24-hour early warning format. The 30-day implementation window requires immediate review of your incident response runbooks and communication templates.",
        "matched_controls": [
            {"control_name": "Business Continuity & DR Testing", "gap_type": "Update required", "severity": "high"},
            {"control_name": "Endpoint Detection & Response (EDR)", "gap_type": "Review required", "severity": "medium"},
        ],
        "tasks": [
            {"phase": 1, "phase_label": "Gap assessment", "label": "Map NIS2 Art.23 incident categories against current DORA incident classification", "role": "Compliance", "is_priority": True, "due_week": 1},
            {"phase": 1, "phase_label": "Gap assessment", "label": "Draft 24-hour early warning template per ENISA format", "role": "IT", "is_priority": True, "due_week": 2},
            {"phase": 2, "phase_label": "Implementation", "label": "Update incident response runbook with NIS2-compliant notification chain", "role": "IT", "due_week": 3},
            {"phase": 2, "phase_label": "Implementation", "label": "Tabletop exercise simulating NIS2 incident notification timeline", "role": "Audit", "due_week": 4},
            {"phase": 3, "phase_label": "Evidence packaging", "label": "Document NIS2 implementation evidence for supervisory file", "role": "Compliance", "due_week": 5},
        ],
    },
    {
        "source": "FATF", "regulation_family": "AML/AMLD6",
        "jurisdiction": "Global", "severity": "critical",
        "title": "FATF mutual evaluation of Netherlands — payment institution findings published",
        "summary": "FATF publishes Netherlands mutual evaluation follow-up. Dutch payment institutions cited for deficiencies in beneficial ownership verification and cross-border wire transfer monitoring. DNB expected to escalate supervisory intensity.",
        "deadline_label": "60 days",
        "deadline_days": 60,
        "tags": ["AML/AMLD6", "FATF", "DNB", "KYC"],
        "external_id_prefix": "fatf-nl-eval",
        "impact_assessment": "This FATF evaluation directly increases the probability of a DNB-initiated thematic review of payment institution AML controls within the next 6 months. Your transaction monitoring covers 47 of the expected 65+ typologies. Beneficial ownership verification through your KYC engine does not currently capture ultimate beneficial owners for complex structures — a specific FATF finding. This is a P1 remediation item.",
        "matched_controls": [
            {"control_name": "Transaction Monitoring Rule Engine", "gap_type": "Critical gap", "severity": "critical"},
            {"control_name": "KYC / Customer Due Diligence Engine", "gap_type": "Critical gap", "severity": "critical"},
            {"control_name": "Sanctions Screening — Real-Time API", "gap_type": "Review required", "severity": "high"},
        ],
        "tasks": [
            {"phase": 1, "phase_label": "Urgent response", "label": "MLRO to brief board on FATF findings and DNB escalation risk", "role": "MLRO", "is_priority": True, "due_week": 1},
            {"phase": 1, "phase_label": "Urgent response", "label": "Gap analysis: map beneficial ownership verification against FATF Rec 24/25", "role": "Compliance", "is_priority": True, "due_week": 1},
            {"phase": 2, "phase_label": "Remediation", "label": "Expand transaction monitoring to 20+ additional typologies — prioritise cross-border and wire transfer", "role": "IT", "due_week": 4},
            {"phase": 2, "phase_label": "Remediation", "label": "Implement UBO verification for legal entity customers — complex structures", "role": "IT", "due_week": 6},
            {"phase": 3, "phase_label": "Evidence packaging", "label": "Prepare DNB self-assessment response document", "role": "MLRO", "due_week": 8},
            {"phase": 3, "phase_label": "Evidence packaging", "label": "External review of updated AML programme by approved assessor", "role": "Audit", "due_week": 10},
        ],
    },
]

_live_change_index = 0

@router.post("/simulate-update", response_model=ChangeOut)
async def simulate_live_update(
    org_id: Annotated[UUID, Depends(get_org_id)],
    _: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    """Inject one new regulatory change from the live pool (rotates through 3)."""
    global _live_change_index
    template = _LIVE_CHANGES[_live_change_index % len(_LIVE_CHANGES)]
    _live_change_index += 1

    now = datetime.now(timezone.utc)
    # unique external_id to allow re-simulation
    uid = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    deadline = now + timedelta(days=template["deadline_days"])

    change = RegulatoryChange(
        org_id=org_id,
        source=template["source"],
        regulation_family=template["regulation_family"],
        jurisdiction=template["jurisdiction"],
        severity=_sev(template["severity"]),
        title=template["title"],
        summary=template["summary"],
        deadline_at=deadline,
        deadline_label=template["deadline_label"],
        impact_assessment=template["impact_assessment"],
        matched_controls=template["matched_controls"],
        tags=template["tags"],
        is_new=True,
        pipeline_stage=RegChangePipelineStage.actioned,
        relevance_score=0.92,
        external_id=f"{template['external_id_prefix']}-{uid}",
        published_at=now,
    )
    db.add(change)
    await db.flush()

    for i, td in enumerate(template["tasks"]):
        db.add(RegChangeTask(
            change_id=change.id,
            phase=td["phase"],
            phase_label=td["phase_label"],
            label=td["label"],
            role=td.get("role"),
            is_priority=td.get("is_priority", False),
            sort_order=i,
            due_week=td.get("due_week"),
        ))

    await db.commit()
    # Re-fetch with tasks eagerly loaded
    change = (await db.execute(
        select(RegulatoryChange)
        .where(RegulatoryChange.id == change.id)
        .options(selectinload(RegulatoryChange.tasks))
    )).scalar_one()
    return _to_change_out(change)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sev(s: str) -> RegChangeSeverity:
    return {
        "critical": RegChangeSeverity.critical, "high": RegChangeSeverity.high,
        "medium": RegChangeSeverity.medium, "low": RegChangeSeverity.low,
    }.get(s, RegChangeSeverity.medium)


def _to_change_out(r: RegulatoryChange) -> ChangeOut:
    return ChangeOut(
        id=str(r.id),
        source=r.source,
        source_url=r.source_url,
        regulation_family=r.regulation_family,
        jurisdiction=r.jurisdiction,
        title=r.title,
        summary=r.summary,
        severity=r.severity.value,
        relevance_score=r.relevance_score,
        pipeline_stage=r.pipeline_stage.value,
        deadline_at=r.deadline_at.isoformat() if r.deadline_at else None,
        deadline_label=r.deadline_label,
        impact_assessment=r.impact_assessment,
        matched_controls=r.matched_controls or [],
        tags=r.tags or [],
        is_new=r.is_new,
        is_dismissed=r.is_dismissed,
        published_at=r.published_at.isoformat(),
        tasks=[
            TaskOut(
                id=str(t.id), phase=t.phase, phase_label=t.phase_label,
                label=t.label, role=t.role,
                status=t.status.value, is_priority=t.is_priority,
                sort_order=t.sort_order, due_week=t.due_week,
            )
            for t in sorted(r.tasks, key=lambda x: x.sort_order)
        ],
    )


async def _run_ai_assessment(
    change: RegulatoryChange,
    controls: list[Control],
    org_context: OrgProfileContext | None = None,
) -> tuple[str, list[dict], list[dict]]:
    """Call Claude to generate impact assessment + action plan."""
    control_summary = "\n".join(
        f"- {c.name} ({c.domain}) — {c.status.value}" for c in controls[:20]
    )

    org_block = ""
    if org_context:
        org_block = f"\nFIRM PROFILE:\n{format_context_for_prompt(org_context)}\n"
    firm_descriptor = org_context.legal_name if org_context else "the firm"

    prompt = f"""You are a regulatory impact assessment specialist for {firm_descriptor}.
{org_block}
REGULATORY CHANGE:
Title: {change.title}
Source: {change.source} | Regulation: {change.regulation_family} | Severity: {change.severity.value}
Summary: {change.summary or 'Not provided'}
Deadline: {change.deadline_label or 'Not specified'}

FIRM'S CURRENT CONTROL INVENTORY:
{control_summary}

Generate a JSON response with exactly this structure:
{{
  "assessment": "<3-4 sentence plain-language impact assessment specific to this firm's controls>",
  "matched_controls": [
    {{"control_name": "<exact name from inventory>", "gap_type": "<Critical gap|Partial gap|Update required|Review required|Adequate>", "severity": "<critical|high|medium|low>"}}
  ],
  "tasks": [
    {{"phase": 1, "phase_label": "Urgent response", "label": "<specific task>", "role": "<MLRO|Legal|IT|Compliance|Audit>", "is_priority": true, "due_week": 1}},
    ...more tasks across phases 1, 2, 3...
  ]
}}

Phase 1 = Urgent response (week 1-2)
Phase 2 = Implementation (weeks 2-N based on deadline)
Phase 3 = Evidence packaging (final weeks before deadline)

Return ONLY valid JSON, no other text."""

    try:
        response = await claude.messages.create(
            model=settings.claude_model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        return data["assessment"], data.get("matched_controls", []), data.get("tasks", [])
    except Exception as e:
        # Fallback to static assessment
        assessment = (
            f"This {change.severity.value}-severity change from {change.source} requires "
            f"review of your {change.regulation_family} compliance posture. "
            f"Relevant controls should be assessed against the new requirements. "
            f"Engage your compliance team to evaluate impact within the deadline window."
        )
        return assessment, [], [
            {"phase": 1, "phase_label": "Urgent response", "label": f"Review {change.regulation_family} change with compliance team", "role": "Compliance", "is_priority": True, "due_week": 1},
            {"phase": 2, "phase_label": "Implementation", "label": "Identify and update affected controls", "role": "IT", "due_week": 4},
            {"phase": 3, "phase_label": "Evidence packaging", "label": "Document compliance evidence", "role": "Audit", "due_week": 8},
        ]


# ── Initial data seeder ────────────────────────────────────────────────────────

_INITIAL_CHANGES = [
    {
        "source": "EBA",
        "regulation_family": "DORA",
        "jurisdiction": "EU",
        "severity": "critical",
        "relevance_score": 0.97,
        "title": "DORA RTS finalised — ICT third-party register requirements clarified",
        "summary": "EBA published final regulatory technical standards for DORA Art. 28. Firms must maintain a register of ICT third-party service providers with contractual information, sub-outsourcing chains, and concentration risk indicators.",
        "deadline_label": "Jan 2027",
        "deadline_days": 245,
        "tags": ["DORA", "ICT", "Third-party"],
        "external_id": "eba-dora-rts-2025-01",
        "impact_assessment": "The finalised DORA RTS requires you to maintain a structured ICT third-party register covering all providers in your supply chain. Your current third-party risk assessment programme captures annual questionnaire results but does not yet include sub-outsourcing chains or concentration risk scoring as required by Art.28(3). The January 2027 deadline is achievable but requires a programme of work beginning immediately.",
        "matched_controls": [
            {"control_name": "Third-Party Risk Assessment Programme", "gap_type": "Critical gap", "severity": "critical"},
            {"control_name": "Business Continuity & DR Testing", "gap_type": "Update required", "severity": "high"},
        ],
        "pipeline_stage": "actioned",
        "tasks": [
            {"phase": 1, "phase_label": "Urgent response", "label": "Map all ICT third-party providers against DORA Art.28 register template", "role": "Compliance", "is_priority": True, "due_week": 2},
            {"phase": 1, "phase_label": "Urgent response", "label": "Identify critical ICT third-party providers and sub-outsourcing chains", "role": "IT", "is_priority": True, "due_week": 2},
            {"phase": 2, "phase_label": "Register build", "label": "Build ICT third-party register with contractual data, SLAs, and sub-processor mapping", "role": "IT", "due_week": 8},
            {"phase": 2, "phase_label": "Register build", "label": "Implement concentration risk scoring model for critical providers", "role": "Compliance", "due_week": 12},
            {"phase": 2, "phase_label": "Register build", "label": "Negotiate DORA-compliant contractual provisions with top 10 ICT providers", "role": "Legal", "due_week": 16},
            {"phase": 3, "phase_label": "Submission", "label": "Submit ICT register to DNB in prescribed DORA format", "role": "Compliance", "due_week": 32},
            {"phase": 3, "phase_label": "Submission", "label": "Internal audit of ICT register completeness and accuracy", "role": "Audit", "due_week": 28},
        ],
    },
    {
        "source": "AP (NL)",
        "regulation_family": "GDPR",
        "jurisdiction": "NL",
        "severity": "high",
        "relevance_score": 0.91,
        "title": "AP enforcement: €2.1M fine for unlawful SCCs in cloud transfers — sector alert",
        "summary": "The Dutch Data Protection Authority fined a Netherlands payment processor €2.1M for transferring customer data to US cloud providers under invalidated SCCs. The AP confirmed it is conducting sector-wide reviews of cloud transfer mechanisms for payment firms.",
        "deadline_label": "Immediate",
        "deadline_days": 14,
        "tags": ["GDPR", "SCCs", "Cloud", "AP"],
        "external_id": "ap-scc-enforcement-2025-03",
        "impact_assessment": "This AP enforcement action directly signals an imminent sector review of cloud data transfer mechanisms for Netherlands-registered payment institutions. Your cloud infrastructure uses AWS eu-west-1 as primary region, but CSPM findings indicate cross-region replication that may involve US data centres. Your DSAR intake process does not currently map which personal data flows through US cloud infrastructure. This is a P1 item requiring immediate legal review.",
        "matched_controls": [
            {"control_name": "Cloud Security Posture Management (CSPM)", "gap_type": "Update required", "severity": "high"},
            {"control_name": "DSAR Intake & Fulfilment Workflow", "gap_type": "Partial gap", "severity": "high"},
        ],
        "pipeline_stage": "actioned",
        "tasks": [
            {"phase": 1, "phase_label": "Immediate review", "label": "Legal review of all active SCCs with US cloud providers — validate post-Schrems II compliance", "role": "Legal", "is_priority": True, "due_week": 1},
            {"phase": 1, "phase_label": "Immediate review", "label": "Map personal data flows through AWS — identify any cross-region replication to US regions", "role": "IT", "is_priority": True, "due_week": 1},
            {"phase": 2, "phase_label": "Remediation", "label": "Implement data residency controls — restrict PII to EU regions only", "role": "IT", "due_week": 3},
            {"phase": 2, "phase_label": "Remediation", "label": "Update DSAR data mapping to include cloud transfer mechanisms", "role": "Compliance", "due_week": 3},
            {"phase": 3, "phase_label": "Evidence packaging", "label": "Document updated transfer impact assessment for supervisory file", "role": "Legal", "due_week": 5},
        ],
    },
    {
        "source": "EC",
        "regulation_family": "PSD3",
        "jurisdiction": "EU",
        "severity": "high",
        "relevance_score": 0.88,
        "title": "PSD3 draft published — fraud liability shifts to payment firms for APP fraud",
        "summary": "European Commission published the PSD3 draft. Key change: authorised push payment (APP) fraud liability shifts from the victim to the payment institution in most cases, requiring firms to implement mandatory transaction delay features and enhanced fraud detection.",
        "deadline_label": "Late 2027",
        "deadline_days": 620,
        "tags": ["PSD3", "APP fraud", "Liability"],
        "external_id": "ec-psd3-draft-2025-02",
        "impact_assessment": "PSD3's APP fraud liability shift is the most material commercial impact on your business model in this regulatory cycle. Your current transaction monitoring covers fraud detection but does not implement mandatory cooling-off periods or step-up authentication for high-value APP payments as required under the draft. The late 2027 timeline gives adequate runway, but the technical implementation — particularly mandatory payment delay infrastructure — requires design work starting in Q3 2025.",
        "matched_controls": [
            {"control_name": "Transaction Monitoring Rule Engine", "gap_type": "Partial gap", "severity": "high"},
            {"control_name": "KYC / Customer Due Diligence Engine", "gap_type": "Update required", "severity": "medium"},
        ],
        "pipeline_stage": "assessed",
        "tasks": [
            {"phase": 1, "phase_label": "Analysis", "label": "Legal analysis of PSD3 APP fraud liability provisions and gap to current T&Cs", "role": "Legal", "is_priority": True, "due_week": 4},
            {"phase": 1, "phase_label": "Analysis", "label": "Product review: map mandatory PSD3 features against current payment flows", "role": "Compliance", "due_week": 4},
            {"phase": 2, "phase_label": "Design & build", "label": "Design mandatory payment delay feature for high-value APP transactions", "role": "IT", "due_week": 20},
            {"phase": 2, "phase_label": "Design & build", "label": "Enhance fraud ML model with APP-specific behavioural indicators", "role": "IT", "due_week": 24},
            {"phase": 3, "phase_label": "Compliance", "label": "Update terms and conditions to reflect revised APP fraud liability", "role": "Legal", "due_week": 52},
        ],
    },
    {
        "source": "DNB",
        "regulation_family": "AML/AMLD6",
        "jurisdiction": "NL",
        "severity": "critical",
        "relevance_score": 0.99,
        "title": "DNB supervisory letter — AML transaction monitoring: 60-day remediation deadline",
        "summary": "DNB issued a supervisory letter to all supervised payment institutions citing systemic deficiencies in transaction monitoring typology coverage and suspicious transaction reporting rates. Firms are required to submit a remediation plan within 60 days.",
        "deadline_label": "60 days",
        "deadline_days": 60,
        "tags": ["AML/AMLD6", "DNB", "Transaction monitoring"],
        "external_id": "dnb-aml-supervisory-2025-04",
        "impact_assessment": "This DNB supervisory letter is the highest-priority compliance action in your current portfolio. Your transaction monitoring rule engine covers 47 typologies against an expected 65+ for a firm with your transaction volume and risk profile. The 60-day deadline for a remediation plan is non-negotiable — failure to respond adequately creates grounds for formal enforcement under Art.22 of the AML Directive. Engage your MLRO immediately and prioritise typology expansion.",
        "matched_controls": [
            {"control_name": "Transaction Monitoring Rule Engine", "gap_type": "Critical gap", "severity": "critical"},
            {"control_name": "KYC / Customer Due Diligence Engine", "gap_type": "Update required", "severity": "high"},
            {"control_name": "Sanctions Screening — Real-Time API", "gap_type": "Review required", "severity": "medium"},
        ],
        "pipeline_stage": "actioned",
        "tasks": [
            {"phase": 1, "phase_label": "Urgent response", "label": "MLRO to convene AML crisis response team — brief within 48 hours", "role": "MLRO", "is_priority": True, "due_week": 1},
            {"phase": 1, "phase_label": "Urgent response", "label": "Commission gap analysis: current 47 typologies vs DNB expected coverage", "role": "Compliance", "is_priority": True, "due_week": 1},
            {"phase": 1, "phase_label": "Urgent response", "label": "Appoint external AML specialist to validate remediation plan", "role": "MLRO", "is_priority": True, "due_week": 2},
            {"phase": 2, "phase_label": "Remediation implementation", "label": "Expand transaction monitoring to 20 additional typologies — priority: structuring, smurfing, layering", "role": "IT", "due_week": 4},
            {"phase": 2, "phase_label": "Remediation implementation", "label": "Tune alert thresholds to reduce false positive rate below 15%", "role": "IT", "due_week": 5},
            {"phase": 2, "phase_label": "Remediation implementation", "label": "Enhance STR reporting workflow — automate pre-screening and escalation", "role": "Compliance", "due_week": 5},
            {"phase": 3, "phase_label": "Evidence submission", "label": "Draft and submit remediation plan to DNB", "role": "MLRO", "due_week": 7},
            {"phase": 3, "phase_label": "Evidence submission", "label": "Prepare testing evidence for expanded typology coverage", "role": "Audit", "due_week": 8},
        ],
    },
    {
        "source": "ISO",
        "regulation_family": "ISO 27001",
        "jurisdiction": "Global",
        "severity": "medium",
        "relevance_score": 0.78,
        "title": "ISO 27001:2022 transition deadline — 12 months remaining",
        "summary": "ISO/IEC 27001:2022 mandatory transition deadline approaches. All organisations must complete transition from 2013 version to 2022 standard. Certification bodies will cease issuing 2013 certificates. Key changes include new Annex A controls covering threat intelligence, cloud security, and secure coding.",
        "deadline_label": "Oct 2026",
        "deadline_days": 150,
        "tags": ["ISO 27001", "Certification", "Cloud security"],
        "external_id": "iso-27001-2022-transition",
        "impact_assessment": "Your ISO 27001:2022 transition audit is due within 12 months. Your current programme is based on the 2013 standard. The 2022 version adds 11 new Annex A controls — most relevantly A.8.23 (web filtering), A.8.25 (secure development lifecycle), and A.5.7 (threat intelligence). Your EDR and CSPM controls partially satisfy A.5.7 but require documentation updates. Your cloud security controls satisfy A.8.9 but lack the formal cloud configuration management process required by the new standard.",
        "matched_controls": [
            {"control_name": "Endpoint Detection & Response (EDR)", "gap_type": "Update required", "severity": "medium"},
            {"control_name": "Cloud Security Posture Management (CSPM)", "gap_type": "Update required", "severity": "medium"},
            {"control_name": "Vulnerability Management & Patch SLAs", "gap_type": "Review required", "severity": "low"},
        ],
        "pipeline_stage": "actioned",
        "tasks": [
            {"phase": 1, "phase_label": "Gap analysis", "label": "Map current 2013 Annex A controls to 2022 equivalents — identify 11 new controls", "role": "Compliance", "is_priority": True, "due_week": 2},
            {"phase": 2, "phase_label": "Implementation", "label": "Document threat intelligence process to satisfy Annex A.5.7", "role": "IT", "due_week": 8},
            {"phase": 2, "phase_label": "Implementation", "label": "Implement formal cloud configuration management process (A.8.9)", "role": "IT", "due_week": 12},
            {"phase": 2, "phase_label": "Implementation", "label": "Update ISMS documentation to 2022 structure", "role": "Compliance", "due_week": 16},
            {"phase": 3, "phase_label": "Transition audit", "label": "Schedule transition audit with certification body", "role": "Audit", "due_week": 18},
        ],
    },
]


async def _seed_initial_changes(
    org_id: UUID,
    db: AsyncSession,
    org_context: OrgProfileContext | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    for ch in _INITIAL_CHANGES:
        deadline = now + timedelta(days=ch["deadline_days"])
        change = RegulatoryChange(
            org_id=org_id,
            source=ch["source"],
            regulation_family=ch["regulation_family"],
            jurisdiction=ch["jurisdiction"],
            severity=_sev(ch["severity"]),
            relevance_score=ch["relevance_score"],
            title=ch["title"],
            summary=ch["summary"],
            deadline_at=deadline,
            deadline_label=ch["deadline_label"],
            impact_assessment=ch["impact_assessment"],
            matched_controls=ch["matched_controls"],
            tags=ch["tags"],
            is_new=True,
            pipeline_stage=RegChangePipelineStage(ch["pipeline_stage"]),
            external_id=ch["external_id"],
            published_at=now - timedelta(days=random.randint(0, 7)),
        )
        db.add(change)
        await db.flush()

        for i, td in enumerate(ch["tasks"]):
            db.add(RegChangeTask(
                change_id=change.id,
                phase=td["phase"],
                phase_label=td["phase_label"],
                label=td["label"],
                role=td.get("role"),
                is_priority=td.get("is_priority", False),
                sort_order=i,
                due_week=td.get("due_week"),
            ))

    await db.commit()
