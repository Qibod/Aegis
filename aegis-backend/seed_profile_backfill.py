"""
seed_profile_backfill.py
─────────────────────────
One-shot Railway function that fixes two gaps left by PR #6 deployment:

  1. Backfills field_status_map on all profile entity rows so Verification
     Ticks render a state (seeded / unknown) instead of being invisible.

  2. Runs fingerprint + full seed for any org stuck at onboarding_complete=false
     (except synthetic/smoke-test tenants) so those accounts get their data.

Run inside the api container or as a Railway one-shot function:
  railway run --service pure-enthusiasm python seed_profile_backfill.py
"""
import asyncio
import logging
import sys

sys.path.insert(0, "/app")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

SKIP_NAMES = {"SmokeTest"}


async def backfill_field_status_maps():
    """Mark every non-null field as 'seeded' and every null field as 'unknown'."""
    from sqlalchemy import select

    from app.database import get_db_context
    from app.models import (
        CustomerSegment, DataTechProfile, LineOfBusiness,
        OrgGeography, OrgIndustry, OrgProduct, OrgProfile,
        Organization, ThirdPartyDependency,
    )
    from app.seeding.field_specs import FIELD_SPECS

    entity_model_map = {
        "org_profiles":           OrgProfile,
        "lines_of_business":      LineOfBusiness,
        "org_geographies":        OrgGeography,
        "org_industries":         OrgIndustry,
        "org_products":           OrgProduct,
        "org_customer_segments":  CustomerSegment,
        "org_third_parties":      ThirdPartyDependency,
        "org_data_tech_profiles": DataTechProfile,
    }

    async with get_db_context() as db:
        orgs = (await db.execute(
            select(Organization).where(Organization.onboarding_complete == True)
        )).scalars().all()

        for org in orgs:
            if org.name in SKIP_NAMES:
                continue

            updated_entities = 0
            for entity_type, model_cls in entity_model_map.items():
                entities = (await db.execute(
                    select(model_cls).where(model_cls.org_id == org.id)
                )).scalars().all()

                for entity in entities:
                    status_map = dict(entity.field_status_map or {})
                    changed = False
                    for spec in FIELD_SPECS.get(entity_type, []):
                        if spec.name in status_map:
                            continue  # don't overwrite existing status
                        val = getattr(entity, spec.name, None)
                        is_set = val is not None and val != "" and val != [] and val != {}
                        status_map[spec.name] = "seeded" if is_set else "unknown"
                        changed = True
                    if changed:
                        entity.field_status_map = status_map
                        updated_entities += 1

            log.info("backfill: org '%s' (%s) — %d entities updated", org.name, org.id, updated_entities)

    log.info("field_status_map backfill complete")


async def fix_incomplete_onboarding():
    """Fingerprint + seed orgs stuck at onboarding_complete=False."""
    from sqlalchemy import select

    from app.ai.fingerprint import fingerprint_company, seed_org_from_fingerprint
    from app.database import get_db_context
    from app.models import Organization, OrgProfile

    async with get_db_context() as db:
        stuck = (await db.execute(
            select(Organization).where(Organization.onboarding_complete == False)
        )).scalars().all()

        for org in stuck:
            if org.name in SKIP_NAMES:
                log.info("skipping synthetic tenant '%s'", org.name)
                continue

            existing_profile = (await db.execute(
                select(OrgProfile).where(OrgProfile.org_id == org.id)
            )).scalar_one_or_none()
            if existing_profile:
                log.info("org '%s' already has profile — marking onboarding complete", org.name)
                org.onboarding_complete = True
                continue

            log.info("fixing incomplete onboarding for '%s' (%s)...", org.name, org.id)
            try:
                fingerprint = await fingerprint_company(org.name)

                from datetime import datetime, timezone
                org.fingerprint_data = fingerprint
                org.onboarding_complete = True
                org.industry_code = fingerprint.get("industry_code")
                org.industry_label = fingerprint.get("industry_label")
                org.jurisdiction = fingerprint.get("jurisdiction")
                org.regulator = fingerprint.get("regulator")
                org.fingerprinted_at = datetime.now(timezone.utc)
                await db.flush()

                await seed_org_from_fingerprint(str(org.id), fingerprint, db)
                log.info("fixed '%s' — %d risks, %d controls seeded",
                         org.name,
                         len(fingerprint.get("risks", [])),
                         len(fingerprint.get("controls", [])))
            except Exception as exc:
                log.error("failed to fix '%s': %s", org.name, exc)
                await db.rollback()


async def main():
    log.info("=== Aegis profile backfill starting ===")
    await backfill_field_status_maps()
    await fix_incomplete_onboarding()
    log.info("=== Backfill complete ===")


asyncio.run(main())
