"""app/api/routes/risks_route.py — Risk register CRUD + Risk Universe"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_org_id
from app.database import get_db
from app.models import LineOfBusiness, Risk
from app.schemas import (
    DomainCoverage, HeatCell, RiskCreate, RiskListResponse,
    RiskResponse, RiskUpdate, UniverseSummary,
)

router = APIRouter(prefix="/risks", tags=["risks"])

_SEV_RANK = case(
    (Risk.inherent_severity == "critical", 4),
    (Risk.inherent_severity == "high", 3),
    (Risk.inherent_severity == "medium", 2),
    else_=1,
)

_SEV_FROM_RANK = {4: "critical", 3: "high", 2: "medium", 1: "low"}


def _risk_to_response(risk: Risk) -> RiskResponse:
    data = RiskResponse.model_validate(risk)
    if risk.lob is not None:
        data.lob_name = risk.lob.name
    return data


# ── Universe summary ──────────────────────────────────────────────────────────
# IMPORTANT: must be registered before /{risk_id} to avoid UUID parsing clash.

@router.get("/universe-summary", response_model=UniverseSummary)
async def get_universe_summary(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    base_where = Risk.org_id == org_id

    # ── Totals ──────────────────────────────────────────────────────────────
    total_row = (await db.execute(
        select(
            func.count(Risk.id).label("total"),
            func.count(Risk.id).filter(
                Risk.inherent_severity.in_(["high", "critical"])
            ).label("high_crit"),
            func.count(Risk.id).filter(Risk.owner_id.is_(None)).label("unowned"),
            func.avg(Risk.control_coverage_pct).label("avg_cov"),
        ).where(base_where)
    )).one()

    total_risks = total_row.total or 0
    high_critical_count = total_row.high_crit or 0
    unowned_count = total_row.unowned or 0
    avg_coverage_pct = round(float(total_row.avg_cov or 0), 1)

    # ── Domain coverage ──────────────────────────────────────────────────────
    domain_rows = (await db.execute(
        select(
            Risk.domain,
            func.count(Risk.id).label("risk_count"),
            func.avg(Risk.control_coverage_pct).label("avg_cov"),
            func.max(_SEV_RANK).label("worst_rank"),
        )
        .where(base_where, Risk.domain.isnot(None))
        .group_by(Risk.domain)
        .order_by(func.count(Risk.id).desc())
    )).all()

    domain_coverage = [
        DomainCoverage(
            domain=r.domain,
            risk_count=r.risk_count,
            avg_coverage_pct=round(float(r.avg_cov or 0), 1),
            worst_severity=_SEV_FROM_RANK.get(r.worst_rank, "low"),
        )
        for r in domain_rows
    ]

    # ── Heat cells ───────────────────────────────────────────────────────────
    heat_rows = (await db.execute(
        select(
            Risk.lob_id,
            LineOfBusiness.name.label("lob_name"),
            Risk.domain,
            func.count(Risk.id).label("risk_count"),
            func.max(_SEV_RANK).label("worst_rank"),
        )
        .join(LineOfBusiness, Risk.lob_id == LineOfBusiness.id, isouter=False)
        .where(base_where, Risk.lob_id.isnot(None), Risk.domain.isnot(None))
        .group_by(Risk.lob_id, LineOfBusiness.name, Risk.domain)
    )).all()

    heat_cells = [
        HeatCell(
            lob_id=str(r.lob_id),
            lob_name=r.lob_name,
            domain=r.domain,
            risk_count=r.risk_count,
            worst_severity=_SEV_FROM_RANK.get(r.worst_rank, "low"),
        )
        for r in heat_rows
    ]

    # ── Needs attention ──────────────────────────────────────────────────────
    attention_q = (
        select(Risk)
        .where(
            base_where,
            (Risk.owner_id.is_(None)) | (Risk.control_coverage_pct < 20),
        )
        .options(selectinload(Risk.owner), selectinload(Risk.lob))
        .order_by(_SEV_RANK.desc())
        .limit(3)
    )
    attention_risks = (await db.execute(attention_q)).scalars().all()
    needs_attention = [_risk_to_response(r) for r in attention_risks]

    return UniverseSummary(
        total_risks=total_risks,
        high_critical_count=high_critical_count,
        unowned_count=unowned_count,
        avg_coverage_pct=avg_coverage_pct,
        domain_coverage=domain_coverage,
        heat_cells=heat_cells,
        needs_attention=needs_attention,
    )


# ── List risks ────────────────────────────────────────────────────────────────

@router.get("", response_model=RiskListResponse)
async def list_risks(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
    domain: str | None = Query(None),
    severity: str | None = Query(None),
    lob_id: UUID | None = Query(None),
    geo_id: UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    q = (
        select(Risk)
        .where(Risk.org_id == org_id)
        .options(selectinload(Risk.owner), selectinload(Risk.lob))
        .order_by(Risk.updated_at.desc())
    )
    if domain:
        q = q.where(Risk.domain == domain)
    if severity:
        q = q.where(Risk.inherent_severity == severity)
    if lob_id:
        q = q.where(Risk.lob_id == lob_id)
    if geo_id:
        q = q.where(Risk.geography_ids.any(geo_id))

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    risks = (await db.execute(q.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return RiskListResponse(
        items=[_risk_to_response(r) for r in risks],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── Create risk ───────────────────────────────────────────────────────────────

@router.post("", response_model=RiskResponse, status_code=201)
async def create_risk(
    payload: RiskCreate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    risk = Risk(org_id=org_id, **payload.model_dump())
    db.add(risk)
    await db.flush()
    await db.refresh(risk, ["owner", "lob"])
    return _risk_to_response(risk)


# ── Get single risk ───────────────────────────────────────────────────────────

@router.get("/{risk_id}", response_model=RiskResponse)
async def get_risk(
    risk_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Risk).where(Risk.id == risk_id, Risk.org_id == org_id)
        .options(selectinload(Risk.owner), selectinload(Risk.lob))
    )
    risk = result.scalar_one_or_none()
    if not risk:
        raise HTTPException(404, "Risk not found")
    return _risk_to_response(risk)


# ── Update risk ───────────────────────────────────────────────────────────────

@router.patch("/{risk_id}", response_model=RiskResponse)
async def update_risk(
    risk_id: UUID,
    payload: RiskUpdate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Risk).where(Risk.id == risk_id, Risk.org_id == org_id)
        .options(selectinload(Risk.owner), selectinload(Risk.lob))
    )
    risk = result.scalar_one_or_none()
    if not risk:
        raise HTTPException(404, "Risk not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(risk, field, value)
    await db.flush()
    await db.refresh(risk, ["lob"])
    return _risk_to_response(risk)


# ── Delete risk ───────────────────────────────────────────────────────────────

@router.delete("/{risk_id}", status_code=204)
async def delete_risk(
    risk_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Risk).where(Risk.id == risk_id, Risk.org_id == org_id))
    risk = result.scalar_one_or_none()
    if not risk:
        raise HTTPException(404, "Risk not found")
    await db.delete(risk)
