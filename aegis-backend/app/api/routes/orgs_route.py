"""app/api/routes/orgs_route.py — Organization management"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_active_user, get_org_id
from app.database import get_db
from app.models import Organization, User
from app.schemas import (
    OrgCompleteOnboarding, OrgFingerprintRequest,
    OrgFingerprintResponse, OrgResponse,
)

router = APIRouter(prefix="/orgs", tags=["organizations"])


@router.get("/me", response_model=OrgResponse)
async def get_my_org(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: AsyncSession = Depends(get_db),
):
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if not org:
        raise HTTPException(404, "Organization not found")
    return org


@router.post("/fingerprint", response_model=OrgFingerprintResponse)
async def fingerprint(
    payload: OrgFingerprintRequest,
    _: Annotated[User, Depends(get_current_active_user)],
):
    from app.ai.fingerprint import fingerprint_company
    result = await fingerprint_company(payload.company_name)
    return OrgFingerprintResponse(**result)


@router.post("/complete-onboarding", response_model=OrgResponse)
async def complete_onboarding(
    payload: OrgCompleteOnboarding,
    org_id: Annotated[UUID, Depends(get_org_id)],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if not org:
        raise HTTPException(404, "Organization not found")
    if org.onboarding_complete:
        raise HTTPException(409, "Onboarding already completed")
    org.fingerprint_data = payload.fingerprint_data
    org.onboarding_complete = True
    await db.flush()
    background_tasks.add_task(
        _seed_org_background,
        org_id=str(org_id),
        fingerprint=payload.fingerprint_data,
        frameworks=payload.selected_frameworks,
    )
    return org


async def _seed_org_background(org_id: str, fingerprint: dict, frameworks: list):
    from app.ai.fingerprint import seed_org_from_fingerprint
    from app.database import get_db_context
    async with get_db_context() as db:
        await seed_org_from_fingerprint(org_id, fingerprint, db)
