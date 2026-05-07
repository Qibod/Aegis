"""Dashboard — aggregated view for the Head of Internal Audit."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_org_id
from app.database import get_db
from app.models import Framework, Organization, Risk, Signal
from app.schemas import DashboardResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    # Org
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one()

    # Risk counts
    all_risks = (await db.execute(
        select(Risk).where(Risk.org_id == org_id).options(selectinload(Risk.owner))
    )).scalars().all()

    # Framework coverage
    frameworks = (await db.execute(
        select(Framework).where(Framework.org_id == org_id, Framework.is_active == True)
    )).scalars().all()

    # Recent signals
    signals = (await db.execute(
        select(Signal)
        .where(Signal.org_id == org_id, Signal.is_surfaced == True, Signal.dismissed_at.is_(None))
        .order_by(desc(Signal.created_at))
        .limit(5)
    )).scalars().all()

    high_risks = [r for r in all_risks if r.inherent_severity in ("high", "critical")]
    gap_risks = [r for r in all_risks if r.control_coverage_pct < 50]

    # AI insights (simple rule-based; upgrade to Claude call for richer output)
    insights = _generate_insights(all_risks, frameworks, signals)

    return DashboardResponse(
        org=org,
        metrics={
            "total_risks": len(all_risks),
            "high_risks": len(high_risks),
            "medium_risks": sum(1 for r in all_risks if r.inherent_severity == "medium"),
            "low_risks": sum(1 for r in all_risks if r.inherent_severity == "low"),
            "controls_mapped": 42,    # TODO: query controls table
            "control_gaps": len(gap_risks),
            "audit_areas": 12,
            "frameworks_active": len(frameworks),
        },
        ai_insights=insights,
        top_risks=sorted(all_risks, key=lambda r: (r.inherent_severity, -r.control_coverage_pct))[:7],
        framework_coverage=[
            {"code": f.code, "label": f.label, "coverage_pct": f.coverage_pct}
            for f in frameworks
        ],
        recent_signals=signals,
    )


def _generate_insights(risks, frameworks, signals) -> list[dict]:
    insights = []
    gap_risks = [r for r in risks if r.control_coverage_pct < 30 and r.inherent_severity in ("high", "critical")]
    if gap_risks:
        r = gap_risks[0]
        insights.append({
            "text": f"Your {r.domain or 'top'} controls have no documented testing evidence. Given your regulatory obligations, this is your highest-priority gap.",
            "source": "Risk register · control gap analysis",
            "action": "Build testing plan",
        })
    low_fw = [f for f in frameworks if f.coverage_pct < 25]
    if low_fw:
        f = low_fw[0]
        insights.append({
            "text": f"{f.label} coverage is at {f.coverage_pct:.0f}%. Based on your profile, key controls need to be created from scratch.",
            "source": f"Framework gap analysis · {f.label}",
            "action": "View DORA roadmap",
        })
    if signals:
        s = signals[0]
        insights.append({
            "text": f"New {s.severity} signal from {s.source}: {s.title[:100]}",
            "source": f"Risk radar · {s.source}",
            "action": "Review signal",
        })
    return insights
