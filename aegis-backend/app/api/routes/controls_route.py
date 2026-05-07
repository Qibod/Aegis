"""app/api/routes/controls_route.py — Control library CRUD"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_active_user, get_org_id
from app.database import get_db
from app.models import Control, Evidence, User
from app.schemas import ControlCreate, ControlResponse, ControlUpdate, EvidenceResponse

router = APIRouter(prefix="/controls", tags=["controls"])


@router.get("", response_model=list[ControlResponse])
async def list_controls(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(None),
    domain: str | None = Query(None),
):
    q = (
        select(Control).where(Control.org_id == org_id)
        .options(selectinload(Control.owner))
        .order_by(Control.name)
    )
    if status:
        q = q.where(Control.status == status)
    if domain:
        q = q.where(Control.domain == domain)
    return (await db.execute(q)).scalars().all()


@router.post("", response_model=ControlResponse, status_code=201)
async def create_control(
    payload: ControlCreate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    control = Control(org_id=org_id, **payload.model_dump())
    db.add(control)
    await db.flush()
    await db.refresh(control, ["owner"])
    return control


@router.get("/{control_id}", response_model=ControlResponse)
async def get_control(
    control_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Control).where(Control.id == control_id, Control.org_id == org_id)
        .options(selectinload(Control.owner))
    )
    control = result.scalar_one_or_none()
    if not control:
        raise HTTPException(404, "Control not found")
    return control


@router.patch("/{control_id}", response_model=ControlResponse)
async def update_control(
    control_id: UUID,
    payload: ControlUpdate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Control).where(Control.id == control_id, Control.org_id == org_id)
        .options(selectinload(Control.owner))
    )
    control = result.scalar_one_or_none()
    if not control:
        raise HTTPException(404, "Control not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(control, field, value)
    return control


@router.post("/{control_id}/evidence", response_model=EvidenceResponse, status_code=201)
async def upload_evidence(
    control_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Control).where(Control.id == control_id, Control.org_id == org_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Control not found")
    content = await file.read()
    file_key = f"{org_id}/{control_id}/{file.filename}"
    evidence = Evidence(
        org_id=org_id, control_id=control_id, uploaded_by=current_user.id,
        name=file.filename, file_key=file_key,
        file_size_bytes=len(content), mime_type=file.content_type,
    )
    db.add(evidence)
    await db.flush()
    return evidence


@router.get("/{control_id}/evidence", response_model=list[EvidenceResponse])
async def list_evidence(
    control_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    q = select(Evidence).where(
        Evidence.control_id == control_id, Evidence.org_id == org_id
    ).order_by(Evidence.created_at.desc())
    return (await db.execute(q)).scalars().all()
