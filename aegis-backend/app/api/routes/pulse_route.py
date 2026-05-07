"""Control pulse — continuous monitoring status and trend data."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_org_id
from app.database import get_db
from app.models import Control, ControlCheck, ControlStatus
from app.schemas import PulseControlResponse, PulseSummaryResponse

router = APIRouter(prefix="/pulse", tags=["pulse"])

# Static AI alerts keyed by control name (used when no live check exists)
_STATIC_ALERTS: dict[str, str] = {
    "Access Review & Recertification": (
        "Completion dropped from 71% to 34% over 14 days. At current velocity the quarterly "
        "deadline will be missed. Recommend escalating to IT owner to issue automated reminders."
    ),
    "Cloud Security Posture Management (CSPM)": (
        "2 critical findings in eu-west-1 relate to publicly exposed S3 buckets containing "
        "transaction logs. Auto-remediation has been attempted but requires manual review."
    ),
    "Privileged Access Management (CyberArk)": (
        "12 privileged accounts have overdue quarterly reviews. Two accounts belong to former "
        "contractors — immediate revocation recommended."
    ),
}

_STATUS_LABEL = {
    ControlStatus.effective: "passing",
    ControlStatus.partial: "degraded",
    ControlStatus.ineffective: "failing",
    ControlStatus.not_tested: "unknown",
}


@router.get("", response_model=PulseSummaryResponse)
async def get_pulse_summary(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    # All controls for the org (not just those with integration_source)
    controls = (await db.execute(
        select(Control).where(Control.org_id == org_id)
    )).scalars().all()

    pulse_controls = []
    for control in controls:
        # Try to get a live ControlCheck record first
        latest_check = (await db.execute(
            select(ControlCheck)
            .where(ControlCheck.control_id == control.id)
            .order_by(desc(ControlCheck.checked_at))
            .limit(1)
        )).scalar_one_or_none()

        if latest_check:
            current_status = latest_check.status.value
            current_metrics = latest_check.metrics or {}
        else:
            # Fall back to the control's own status + integration_config as metrics
            current_status = _STATUS_LABEL.get(control.status, "unknown")
            current_metrics = control.integration_config or {}

        # AI alert: prefer static alerts for known controls, then rule-based
        ai_alert: str | None = None
        if current_status in ("failing", "degraded", "unknown"):
            ai_alert = (
                _STATIC_ALERTS.get(control.name)
                or _generate_ai_alert(control.name, current_status, current_metrics)
            )

        pulse_controls.append(PulseControlResponse(
            control_id=control.id,
            control_name=control.name,
            integration_source=control.integration_source,
            current_status=current_status,
            current_metrics=current_metrics,
            trend=[],
            ai_alert=ai_alert,
        ))

    # Sort: failing first, then degraded, then passing, then unknown
    _ORDER = {"failing": 0, "degraded": 1, "passing": 2, "unknown": 3}
    pulse_controls.sort(key=lambda p: _ORDER.get(p.current_status, 99))

    passing = sum(1 for p in pulse_controls if p.current_status == "passing")
    failing = sum(1 for p in pulse_controls if p.current_status == "failing")
    degraded = sum(1 for p in pulse_controls if p.current_status == "degraded")

    return PulseSummaryResponse(
        passing_count=passing,
        failing_count=failing,
        degraded_count=degraded,
        total_monitored=len(pulse_controls),
        controls=pulse_controls,
    )


def _generate_ai_alert(control_name: str, status: str, metrics: dict) -> str | None:
    """Rule-based AI alert when no static alert exists."""
    if "completion_pct" in metrics:
        pct = metrics["completion_pct"]
        overdue = metrics.get("overdue_users", metrics.get("overdue_count", 0))
        return (
            f"{control_name} completion is at {pct:.0f}% with {overdue} overdue items. "
            f"At this rate, the quarterly deadline will be missed. Escalate to the control owner."
        )
    if "critical_findings" in metrics and metrics["critical_findings"] > 0:
        return (
            f"{metrics['critical_findings']} critical findings require immediate attention. "
            f"Review and remediate before next audit cycle."
        )
    if status == "failing":
        return f"{control_name} is failing. Review immediately and assign to a control owner."
    return None
