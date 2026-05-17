"""
app/tasks/reseed_unknowns.py
─────────────────────────────
Daily Celery Beat task: re-attempt seeding for every field marked "unknown".
Never applies values silently — creates SeedingProposal rows and notifies admins.
"""
import asyncio
import logging
from uuid import UUID

from app.workers.tasks import celery_app, _run_async

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.reseed_unknowns.reseed_unknown_fields_for_org", bind=True, max_retries=2)
def reseed_unknown_fields_for_org(self, org_id: str):
    try:
        _run_async(_reseed_async(UUID(org_id)))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)


@celery_app.task(name="app.tasks.reseed_unknowns.reseed_all_orgs")
def reseed_all_orgs():
    """Triggered by Celery Beat at 02:00 UTC. Fans out per-org tasks."""
    _run_async(_dispatch_all_orgs())


async def _dispatch_all_orgs():
    from app.database import get_db_context
    from app.models import Organization
    from sqlalchemy import select

    async with get_db_context() as db:
        orgs = (await db.execute(
            select(Organization.id).where(Organization.onboarding_complete == True)
        )).scalars().all()

    for org_id in orgs:
        reseed_unknown_fields_for_org.delay(str(org_id))
    logger.info("reseed_all_orgs: queued %d orgs", len(orgs))


async def _reseed_async(org_id: UUID):
    from app.database import get_db_context
    from app.models import Organization, OrgProfile
    from app.seeding.completeness_loop import seed_field
    from app.seeding.field_specs import FIELD_SPECS
    from app.seeding.proposals import create_proposal
    from sqlalchemy import select

    async with get_db_context() as db:
        org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
        if not org:
            return

        profile = (await db.execute(
            select(OrgProfile).where(OrgProfile.org_id == org_id)
        )).scalar_one_or_none()
        if not profile:
            return

        company_name = profile.legal_name or org.name
        context = {
            "legal_name": profile.legal_name,
            "website": profile.website,
            "hq_country": profile.hq_country,
            "stock_ticker": profile.stock_ticker,
            "is_public_company": bool(profile.stock_ticker),
        }

        proposals_created = 0

        for spec in FIELD_SPECS.get("org_profiles", []):
            status_map = profile.field_status_map or {}
            if status_map.get(spec.name) != "unknown":
                continue

            result = await seed_field(spec, company_name, context, db, org_id, "org_profiles", profile.id)
            if result.status == "seeded":
                await create_proposal(
                    db=db,
                    org_id=org_id,
                    entity_type="org_profiles",
                    entity_id=profile.id,
                    field_name=spec.name,
                    proposed_value=result.value,
                    confidence=result.confidence,
                    sources=result.source_urls,
                )
                proposals_created += 1

        await db.commit()

    if proposals_created:
        logger.info("reseed org %s: %d proposals created", org_id, proposals_created)
    else:
        logger.debug("reseed org %s: no new proposals", org_id)
