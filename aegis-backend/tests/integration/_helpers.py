"""tests/integration/_helpers.py — shared test helpers."""
from __future__ import annotations

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Organization, User, SeedingAttempt, FieldValidation, UserRole


async def onboard_test_org(db: AsyncSession, company_slug: str, test_companies: dict) -> Organization:
    """Synchronously runs the full onboarding flow against a fixture company.

    Uses the real seed/validate code paths but with mock_claude in effect.
    Returns the Organization row.
    """
    from app.api.routes.orgs_route import _seed_org_background

    company = test_companies[company_slug]

    org = Organization(
        name=company["company_name"],
        slug=company_slug.replace("_", "-"),
        onboarding_complete=True,
        fingerprint_data={"company_name": company["company_name"], "domain": company["domain"]},
    )
    db.add(org)
    await db.flush()

    user = User(
        email=f"admin@{company['domain']}",
        full_name="Test Admin",
        org_id=org.id,
        role=UserRole.org_admin,
        hashed_password="not-a-real-hash",
        is_active=True,
    )
    db.add(user)
    await db.commit()

    await _seed_org_background(
        org_id=str(org.id),
        fingerprint=org.fingerprint_data,
        frameworks=[],
        company_name=company["company_name"],
    )

    await db.refresh(org)
    return org


async def get_seeding_attempts(db: AsyncSession, org_id: UUID, field_name: str) -> list[SeedingAttempt]:
    rows = (await db.execute(
        select(SeedingAttempt).where(
            SeedingAttempt.org_id == org_id,
            SeedingAttempt.field_name == field_name,
        )
    )).scalars().all()
    return list(rows)


async def get_validations(db: AsyncSession, org_id: UUID, field_name: str) -> list[FieldValidation]:
    rows = (await db.execute(
        select(FieldValidation).where(
            FieldValidation.org_id == org_id,
            FieldValidation.field_name == field_name,
        )
    )).scalars().all()
    return list(rows)
