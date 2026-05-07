"""app/api/routes/risks_route.py — Risk register CRUD"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_org_id
from app.database import get_db
from app.models import Risk
from app.schemas import RiskCreate, RiskListResponse, RiskResponse, RiskUpdate

router = APIRouter(prefix="/risks", tags=["risks"])


@router.get("", response_model=RiskListResponse)
async def list_risks(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
    domain: str | None = Query(None),
    severity: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    q = (
        select(Risk)
        .where(Risk.org_id == org_id)
        .options(selectinload(Risk.owner))
        .order_by(Risk.updated_at.desc())
    )
    if domain:
        q = q.where(Risk.domain == domain)
    if severity:
        q = q.where(Risk.inherent_severity == severity)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return RiskListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=RiskResponse, status_code=201)
async def create_risk(
    payload: RiskCreate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    risk = Risk(org_id=org_id, **payload.model_dump())
    db.add(risk)
    await db.flush()
    await db.refresh(risk, ["owner"])
    return risk


@router.get("/{risk_id}", response_model=RiskResponse)
async def get_risk(
    risk_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Risk).where(Risk.id == risk_id, Risk.org_id == org_id)
        .options(selectinload(Risk.owner))
    )
    risk = result.scalar_one_or_none()
    if not risk:
        raise HTTPException(404, "Risk not found")
    return risk


@router.patch("/{risk_id}", response_model=RiskResponse)
async def update_risk(
    risk_id: UUID,
    payload: RiskUpdate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Risk).where(Risk.id == risk_id, Risk.org_id == org_id)
        .options(selectinload(Risk.owner))
    )
    risk = result.scalar_one_or_none()
    if not risk:
        raise HTTPException(404, "Risk not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(risk, field, value)
    return risk


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
