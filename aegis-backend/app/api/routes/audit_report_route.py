"""
app/api/routes/audit_report_route.py
─────────────────────────────────────
One-tap AI Audit Report Generator.

Assembly pipeline (4 sequential Claude calls):
  Stage 1 · Executive Summary    — headline, period, overall rating, key metrics
  Stage 2 · Finding Narratives   — IIA-format findings derived from org risk/control data
  Stage 3 · Recommendations      — actionable items + management response placeholders
  Stage 4 · Document Structure   — scope, methodology, appendices
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID

from anthropic import AsyncAnthropic
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_org_id
from app.config import get_settings
from app.database import get_db, AsyncSessionLocal
from app.models import (
    AuditReport, AuditReportStatus, FindingResponse, ReportComment,
    Risk, Control, Framework, AuditPlan, Organization,
    ControlStatus, RiskSeverity,
)

settings = get_settings()
claude = AsyncAnthropic(api_key=settings.anthropic_api_key)

router = APIRouter(prefix="/audit", tags=["audit-reports"])


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _severity_label(s: str) -> str:
    return {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}.get(s, s.title())


def _rating_from_score(score: float) -> str:
    if score >= 75:
        return "Satisfactory"
    elif score >= 50:
        return "Needs Improvement"
    else:
        return "Unsatisfactory"


async def _call_claude(system: str, user: str) -> str:
    """Single Claude call — returns message text."""
    msg = await claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    if not msg.content:
        raise ValueError("Claude returned empty content")
    return msg.content[0].text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# 4-Stage Assembly Pipeline
# ─────────────────────────────────────────────────────────────────────────────

REPORT_SYSTEM = """You are an expert internal audit report writer following IIA (Institute of Internal Auditors) \
standards. You write for a Big-4-quality GRC platform called Aegis.

Style rules:
- Professional, authoritative, McKinsey-quality prose. No filler phrases.
- Finding titles: concise (≤ 8 words), action-oriented.
- Severity language: Critical / High / Medium / Low only.
- Always output ONLY valid JSON — no markdown, no code blocks, no extra text.
- Dates are in ISO format. Amounts in EUR where applicable.
- Write as if addressing an Audit Committee, not the management team."""


async def _stage1_exec_summary(
    org_name: str, industry: str, period: str,
    risks: list[dict], controls: list[dict], frameworks: list[str],
    coverage_pct: float, critical_count: int, effective_pct: float,
) -> dict[str, Any]:
    prompt = f"""Generate an executive summary for an internal audit report.

Organisation: {org_name}
Industry: {industry}
Audit period: {period}
Active frameworks: {', '.join(frameworks) or 'None'}

Risk posture:
- Total risks: {len(risks)}
- Critical risks: {critical_count}
- Coverage: {coverage_pct:.0f}%

Control effectiveness:
- Total controls: {len(controls)}
- Effective: {effective_pct:.0f}%
- Sample controls tested: {', '.join(c['name'] for c in controls[:5])}

Top risk domains: {', '.join(set(r.get('domain','') for r in risks[:6] if r.get('domain')))}

Return JSON with this exact structure:
{{
  "headline": "<one compelling sentence — the audit committee's takeaway>",
  "period": "{period}",
  "overall_rating": "<Satisfactory|Needs Improvement|Unsatisfactory>",
  "rating_score": <0-100 integer>,
  "body": "<3-4 sentences of audit opinion — what was tested, what was found, overall conclusion>",
  "key_metrics": [
    {{"label": "Risks in Scope", "value": "<n>", "trend": "stable"}},
    {{"label": "Controls Tested", "value": "<n>", "trend": "<up|down|stable>"}},
    {{"label": "Control Effectiveness", "value": "<n>%", "trend": "<up|down|stable>"}},
    {{"label": "Open Findings", "value": "<n>", "trend": "down"}},
    {{"label": "Framework Coverage", "value": "<n>%", "trend": "up"}}
  ],
  "audit_scope": "<2 sentences describing what domains were in scope>",
  "limitations": "<any scope limitations or caveats — or null>"
}}"""

    raw = await _call_claude(REPORT_SYSTEM, prompt)
    return json.loads(raw)


async def _stage2_findings(
    org_name: str, industry: str,
    risks: list[dict], controls: list[dict],
) -> list[dict[str, Any]]:
    # Build finding candidates from highest-severity risks with weak controls
    finding_input = []
    for r in risks[:8]:
        domain = r.get("domain", "General")
        severity = r.get("severity", "medium")
        finding_input.append(f"- [{severity.upper()}] {r['name']} (domain: {domain})")

    weak_controls = [c for c in controls if c.get("status") in ("ineffective", "partial", "not_tested")][:6]
    ctrl_input = [f"  · {c['name']} ({c['status']})" for c in weak_controls]

    prompt = f"""Generate exactly 4 audit findings for {org_name} ({industry}).

Risks with highest exposure:
{chr(10).join(finding_input)}

Controls with gaps or weaknesses:
{chr(10).join(ctrl_input) if ctrl_input else "  · All controls tested effective"}

Each finding must follow IIA criteria-condition-cause-effect-observation format.
Assign findings F-1 through F-4, ordered by severity (most severe first).

Return a JSON array of exactly 4 objects:
[
  {{
    "id": "F-1",
    "title": "<≤8 word title>",
    "severity": "<Critical|High|Medium|Low>",
    "domain": "<risk domain>",
    "criteria": "<The standard, policy, or regulation that should be met>",
    "condition": "<What auditors found — the actual state>",
    "cause": "<Root cause of the gap>",
    "effect": "<Potential impact if not remediated, including regulatory exposure>",
    "observation": "<2-3 sentence professional narrative combining all of the above>"
  }},
  ...
]"""

    raw = await _call_claude(REPORT_SYSTEM, prompt)
    return json.loads(raw)


async def _stage3_recommendations(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings_text = "\n".join(
        f"- {f['id']} [{f['severity']}]: {f['title']} — {f['observation'][:200]}"
        for f in findings
    )

    prompt = f"""Generate audit recommendations for these findings:

{findings_text}

For each finding, provide one actionable recommendation. Write management-facing language.

Return a JSON array (same order as findings):
[
  {{
    "finding_id": "F-1",
    "recommendation": "<Specific, time-bound management action — 2-3 sentences>",
    "priority": "<Immediate|High|Medium|Low>",
    "target_date_label": "<e.g. Q3 2025 or Within 30 days>",
    "effort": "<Low|Medium|High>",
    "management_response_placeholder": "<Suggested management response template — 1-2 sentences starting with 'Management agrees...' or 'Management notes...'>"
  }},
  ...
]"""

    raw = await _call_claude(REPORT_SYSTEM, prompt)
    return json.loads(raw)


async def _stage4_doc_structure(
    org_name: str, period: str,
    exec_summary: dict, findings: list[dict], frameworks: list[str],
    controls: list[dict],
) -> dict[str, Any]:
    prompt = f"""Generate the document structure sections for an audit report.

Organisation: {org_name}
Period: {period}
Frameworks: {', '.join(frameworks)}
Findings count: {len(findings)}
Controls tested: {len(controls)}
Overall rating: {exec_summary.get('overall_rating', 'Needs Improvement')}

Return JSON with:
{{
  "scope_statement": "<2-3 sentences defining what was audited, time period, and population>",
  "methodology": "<2-3 sentences: risk-based sampling, testing approach, evidence gathered>",
  "independence_statement": "<Standard IIA independence declaration — 1 sentence>",
  "appendix_a_risk_matrix": {{
    "description": "<1 sentence>",
    "matrix": [
      {{"domain": "<domain>", "inherent": "<H/M/L>", "residual": "<H/M/L>", "trend": "<↑|→|↓>"}},
      {{"domain": "<domain>", "inherent": "<H/M/L>", "residual": "<H/M/L>", "trend": "<↑|→|↓>"}},
      {{"domain": "<domain>", "inherent": "<H/M/L>", "residual": "<H/M/L>", "trend": "<↑|→|↓>"}},
      {{"domain": "<domain>", "inherent": "<H/M/L>", "residual": "<H/M/L>", "trend": "<↑|→|↓>"}}
    ]
  }},
  "appendix_b_controls_tested": {{
    "description": "<1 sentence>",
    "items": [
      {{"control": "<name>", "type": "<Automated|Manual>", "result": "<Effective|Partial|Ineffective>", "sample_size": <n>}},
      {{"control": "<name>", "type": "<Automated|Manual>", "result": "<Effective|Partial|Ineffective>", "sample_size": <n>}},
      {{"control": "<name>", "type": "<Automated|Manual>", "result": "<Effective|Partial|Ineffective>", "sample_size": <n>}},
      {{"control": "<name>", "type": "<Automated|Manual>", "result": "<Effective|Partial|Ineffective>", "sample_size": <n>}},
      {{"control": "<name>", "type": "<Automated|Manual>", "result": "<Effective|Partial|Ineffective>", "sample_size": <n>}}
    ]
  }},
  "distribution": {{
    "audit_committee": true,
    "board": false,
    "control_owners": true,
    "regulator": false
  }}
}}"""

    raw = await _call_claude(REPORT_SYSTEM, prompt)
    return json.loads(raw)


# ─────────────────────────────────────────────────────────────────────────────
# Background assembly task
# ─────────────────────────────────────────────────────────────────────────────

async def _run_assembly(report_id: UUID, org_id: UUID) -> None:
    """
    Runs the 4-stage Claude pipeline in a background task.
    Opens its own DB session (safe for FastAPI BackgroundTasks).
    """
    async with AsyncSessionLocal() as db:
        try:
            # Fetch org data
            org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
            risks_q = await db.execute(select(Risk).where(Risk.org_id == org_id).order_by(Risk.inherent_severity.desc()).limit(12))
            risks_orm = risks_q.scalars().all()
            controls_q = await db.execute(select(Control).where(Control.org_id == org_id).limit(15))
            controls_orm = controls_q.scalars().all()
            frameworks_q = await db.execute(select(Framework).where(Framework.org_id == org_id, Framework.is_active == True).limit(8))
            frameworks_orm = frameworks_q.scalars().all()

            risks = [{"name": r.name, "domain": r.domain, "severity": r.inherent_severity.value} for r in risks_orm]
            controls = [{"name": c.name, "status": c.status.value, "domain": c.domain, "type": c.control_type.value} for c in controls_orm]
            frameworks = [f.label for f in frameworks_orm]

            # Compute quick stats
            effective_count = sum(1 for c in controls_orm if c.status == ControlStatus.effective)
            effective_pct = (effective_count / len(controls_orm) * 100) if controls_orm else 0
            critical_count = sum(1 for r in risks_orm if r.inherent_severity == RiskSeverity.critical)

            # Rough coverage pct
            coverage_pct = min(100, (effective_count / max(len(risks_orm), 1)) * 100 * 1.2)

            org_name = org.name if org else "Organisation"
            industry = org.industry_label if org else "Financial Services"
            period = "January – December 2025"

            assembly_log: list[dict] = []

            # ── Stage 1: Executive Summary ──
            t0 = time.monotonic()
            exec_summary = await _stage1_exec_summary(
                org_name, industry, period,
                risks, controls, frameworks,
                coverage_pct, critical_count, effective_pct,
            )
            assembly_log.append({"stage": 1, "name": "Executive Summary", "status": "done", "duration_ms": int((time.monotonic() - t0) * 1000)})

            # ── Stage 2: Finding Narratives ──
            t0 = time.monotonic()
            findings = await _stage2_findings(org_name, industry, risks, controls)
            assembly_log.append({"stage": 2, "name": "Finding Narratives", "status": "done", "duration_ms": int((time.monotonic() - t0) * 1000)})

            # ── Stage 3: Recommendations ──
            t0 = time.monotonic()
            recommendations = await _stage3_recommendations(findings)
            assembly_log.append({"stage": 3, "name": "Recommendations", "status": "done", "duration_ms": int((time.monotonic() - t0) * 1000)})

            # ── Stage 4: Document Structure ──
            t0 = time.monotonic()
            doc_structure = await _stage4_doc_structure(
                org_name, period, exec_summary, findings, frameworks, controls
            )
            assembly_log.append({"stage": 4, "name": "Document Structure", "status": "done", "duration_ms": int((time.monotonic() - t0) * 1000)})

            # Persist results
            report = (await db.execute(
                select(AuditReport)
                .where(AuditReport.id == report_id)
                .options(selectinload(AuditReport.finding_responses))
            )).scalar_one_or_none()

            if report:
                report.status = AuditReportStatus.draft
                report.exec_summary = exec_summary
                report.findings = findings
                report.recommendations = recommendations
                report.doc_structure = doc_structure
                report.assembly_log = assembly_log
                report.overall_rating = exec_summary.get("overall_rating", "Needs Improvement")
                report.rating_score = float(exec_summary.get("rating_score", 60))
                report.distribution = doc_structure.get("distribution", {})
                report.assembled_at = datetime.now(timezone.utc)
                await db.commit()

        except Exception as exc:
            # Mark as failed draft so UI shows error state
            try:
                report = (await db.execute(select(AuditReport).where(AuditReport.id == report_id))).scalar_one_or_none()
                if report:
                    report.status = AuditReportStatus.draft
                    report.exec_summary = {
                        "headline": "Assembly failed — please regenerate",
                        "body": str(exc)[:500],
                        "overall_rating": "Needs Improvement",
                    }
                    await db.commit()
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

def _report_to_dict(r: AuditReport) -> dict:
    return {
        "id": str(r.id),
        "org_id": str(r.org_id),
        "plan_id": str(r.plan_id) if r.plan_id else None,
        "title": r.title,
        "status": r.status.value,
        "overall_rating": r.overall_rating,
        "rating_score": r.rating_score,
        "period_start": r.period_start,
        "period_end": r.period_end,
        "exec_summary": r.exec_summary or {},
        "findings": r.findings or [],
        "recommendations": r.recommendations or [],
        "doc_structure": r.doc_structure or {},
        "assembly_log": r.assembly_log or [],
        "distribution": r.distribution or {},
        "assembled_at": r.assembled_at.isoformat() if r.assembled_at else None,
        "published_at": r.published_at.isoformat() if r.published_at else None,
        "created_at": r.created_at.isoformat(),
        "finding_responses": [
            {
                "id": str(fr.id),
                "finding_index": fr.finding_index,
                "response_text": fr.response_text,
                "responder_name": fr.responder_name,
                "responder_role": fr.responder_role,
                "target_date": fr.target_date,
                "agreed": fr.agreed,
                "created_at": fr.created_at.isoformat(),
            }
            for fr in (r.finding_responses or [])
        ],
    }


@router.post("/reports/generate", status_code=202)
async def generate_report(
    org_id: Annotated[UUID, Depends(get_org_id)],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Kick off a new AI audit report assembly.
    Returns 202 with the report ID immediately; assembly runs in background.
    """
    # Create stub record
    report = AuditReport(
        org_id=org_id,
        title=f"Internal Audit Report — {datetime.now(timezone.utc).strftime('%B %Y')}",
        status=AuditReportStatus.assembling,
        period_start="Q1 2025",
        period_end="Q4 2025",
        assembly_log=[],
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    # Launch background assembly
    background_tasks.add_task(_run_assembly, report.id, org_id)

    return {"report_id": str(report.id), "status": "assembling"}


@router.get("/reports", response_model=list[dict])
async def list_reports(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(AuditReport)
        .where(AuditReport.org_id == org_id)
        .options(selectinload(AuditReport.finding_responses))
        .order_by(AuditReport.created_at.desc())
    )
    reports = (await db.execute(q)).scalars().all()
    return [_report_to_dict(r) for r in reports]


@router.get("/reports/{report_id}")
async def get_report(
    report_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    report = (await db.execute(
        select(AuditReport)
        .where(AuditReport.id == report_id, AuditReport.org_id == org_id)
        .options(selectinload(AuditReport.finding_responses))
    )).scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")
    return _report_to_dict(report)


@router.patch("/reports/{report_id}/status")
async def update_report_status(
    report_id: UUID,
    payload: dict,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    """Advance report status: draft → review → published."""
    report = (await db.execute(
        select(AuditReport)
        .where(AuditReport.id == report_id, AuditReport.org_id == org_id)
        .options(selectinload(AuditReport.finding_responses))
    )).scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")

    new_status = payload.get("status")
    allowed = [s.value for s in AuditReportStatus]
    if new_status not in allowed:
        raise HTTPException(400, f"Status must be one of: {allowed}")

    report.status = AuditReportStatus(new_status)
    if new_status == "published":
        report.published_at = datetime.now(timezone.utc)

    await db.commit()
    return _report_to_dict(report)


@router.post("/reports/{report_id}/findings/{finding_index}/response")
async def upsert_finding_response(
    report_id: UUID,
    finding_index: int,
    payload: dict,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    """Add or update management response for a specific finding."""
    report = (await db.execute(
        select(AuditReport)
        .where(AuditReport.id == report_id, AuditReport.org_id == org_id)
    )).scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")

    # Upsert
    existing = (await db.execute(
        select(FindingResponse)
        .where(FindingResponse.report_id == report_id,
               FindingResponse.finding_index == finding_index)
    )).scalar_one_or_none()

    if existing:
        existing.response_text = payload.get("response_text", existing.response_text)
        existing.responder_name = payload.get("responder_name", existing.responder_name)
        existing.responder_role = payload.get("responder_role", existing.responder_role)
        existing.target_date = payload.get("target_date", existing.target_date)
        existing.agreed = payload.get("agreed", existing.agreed)
        fr = existing
    else:
        fr = FindingResponse(
            report_id=report_id,
            finding_index=finding_index,
            response_text=payload.get("response_text", ""),
            responder_name=payload.get("responder_name"),
            responder_role=payload.get("responder_role"),
            target_date=payload.get("target_date"),
            agreed=payload.get("agreed", True),
        )
        db.add(fr)

    await db.commit()
    await db.refresh(fr)
    return {
        "id": str(fr.id),
        "finding_index": fr.finding_index,
        "response_text": fr.response_text,
        "responder_name": fr.responder_name,
        "responder_role": fr.responder_role,
        "target_date": fr.target_date,
        "agreed": fr.agreed,
    }


@router.delete("/reports/{report_id}/findings/{finding_index}/response", status_code=204)
async def delete_finding_response(
    report_id: UUID,
    finding_index: int,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    report = (await db.execute(
        select(AuditReport).where(AuditReport.id == report_id, AuditReport.org_id == org_id)
    )).scalar_one_or_none()
    if not report:
        raise HTTPException(404)
    fr = (await db.execute(
        select(FindingResponse)
        .where(FindingResponse.report_id == report_id, FindingResponse.finding_index == finding_index)
    )).scalar_one_or_none()
    if fr:
        await db.delete(fr)
        await db.commit()


@router.post("/reports/{report_id}/comments")
async def add_comment(
    report_id: UUID,
    payload: dict,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    report = (await db.execute(
        select(AuditReport).where(AuditReport.id == report_id, AuditReport.org_id == org_id)
    )).scalar_one_or_none()
    if not report:
        raise HTTPException(404)

    comment = ReportComment(
        report_id=report_id,
        section=payload.get("section", "general"),
        comment_text=payload.get("comment_text", ""),
        author_name=payload.get("author_name"),
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return {"id": str(comment.id), "section": comment.section, "comment_text": comment.comment_text}
