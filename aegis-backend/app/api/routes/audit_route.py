"""app/api/routes/audit_route.py — Audit plan and task management"""
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_org_id
from app.database import get_db
from app.models import AuditPlan, AuditTask, TaskStatus
from app.schemas import (
    AuditPlanCreate, AuditPlanResponse,
    AuditTaskCreate, AuditTaskResponse, AuditTaskUpdate,
)

router = APIRouter(prefix="/audit", tags=["audit"])


async def _update_progress(plan_id, db):
    done = (await db.execute(
        select(func.count()).select_from(AuditTask)
        .where(AuditTask.plan_id == plan_id, AuditTask.status == TaskStatus.done)
    )).scalar_one()
    total = (await db.execute(
        select(func.count()).select_from(AuditTask).where(AuditTask.plan_id == plan_id)
    )).scalar_one()
    plan = (await db.execute(
        select(AuditPlan).where(AuditPlan.id == plan_id)
    )).scalar_one_or_none()
    if plan:
        plan.done_count = done
        plan.task_count = total
        plan.progress_pct = (done / total * 100) if total > 0 else 0.0


@router.get("/plans", response_model=list[AuditPlanResponse])
async def list_plans(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(AuditPlan).where(AuditPlan.org_id == org_id)
        .options(selectinload(AuditPlan.tasks).selectinload(AuditTask.assignee))
        .order_by(AuditPlan.created_at.desc())
    )
    return (await db.execute(q)).scalars().all()


@router.post("/plans", response_model=AuditPlanResponse, status_code=201)
async def create_plan(
    payload: AuditPlanCreate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    plan = AuditPlan(org_id=org_id, **payload.model_dump())
    db.add(plan)
    await db.flush()
    await db.refresh(plan, ["tasks"])
    return plan


@router.get("/plans/{plan_id}", response_model=AuditPlanResponse)
async def get_plan(
    plan_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AuditPlan).where(AuditPlan.id == plan_id, AuditPlan.org_id == org_id)
        .options(selectinload(AuditPlan.tasks).selectinload(AuditTask.assignee))
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan


@router.post("/plans/{plan_id}/tasks", response_model=AuditTaskResponse, status_code=201)
async def create_task(
    plan_id: UUID,
    payload: AuditTaskCreate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    plan = (await db.execute(
        select(AuditPlan).where(AuditPlan.id == plan_id, AuditPlan.org_id == org_id)
    )).scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    task = AuditTask(**payload.model_dump())
    db.add(task)
    await db.flush()
    await _update_progress(plan_id, db)
    await db.refresh(task, ["assignee"])
    return task


@router.patch("/tasks/{task_id}", response_model=AuditTaskResponse)
async def update_task(
    task_id: UUID,
    payload: AuditTaskUpdate,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AuditTask)
        .join(AuditPlan, AuditTask.plan_id == AuditPlan.id)
        .where(AuditTask.id == task_id, AuditPlan.org_id == org_id)
        .options(selectinload(AuditTask.assignee))
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    if payload.status == "done" and not task.completed_at:
        task.completed_at = datetime.now(timezone.utc)
    await _update_progress(task.plan_id, db)
    return task
