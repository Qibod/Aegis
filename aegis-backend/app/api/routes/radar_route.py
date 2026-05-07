"""app/api/routes/radar_route.py"""
from typing import Annotated
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_org_id
from app.database import get_db
from app.models import Signal, SignalSeverity
from app.schemas import SignalListResponse, SignalResponse

router = APIRouter(prefix="/radar", tags=["radar"])


@router.get("/signals", response_model=SignalListResponse)
async def list_signals(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
    category: str | None = Query(None),
    severity: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
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
