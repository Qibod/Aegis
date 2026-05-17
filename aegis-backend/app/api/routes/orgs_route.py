"""app/api/routes/orgs_route.py — Organization management"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import build_org_profile_context
from app.api.auth import get_current_active_user, get_org_id
from app.database import get_db
from app.models import Organization, User
from app.schemas import (
    OrgCompleteOnboarding, OrgFingerprintRequest,
    OrgFingerprintResponse, OrgResponse, OrgProfileResponse,
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


@router.get("/profile", response_model=OrgProfileResponse)
async def get_org_profile(
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
    org_id: Annotated[UUID, Depends(get_org_id)],
    _: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
):
    from app.ai.fingerprint import fingerprint_company
    # Use verified Company Profile as primary context if it already exists
    org_context = await build_org_profile_context(org_id, db)
    result = await fingerprint_company(payload.company_name, org_context)
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
