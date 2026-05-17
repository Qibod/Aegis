"""
app/tasks/cleanup_synthetic_tenants.py
────────────────────────────────────────
Celery Beat task: hard-delete synthetic tenants older than 90 days.
Runs daily at 03:00 UTC (one hour after re-seed to avoid overlap).
"""
import logging
from datetime import datetime, timedelta, timezone

from app.workers.tasks import celery_app, _run_async

logger = logging.getLogger(__name__)
RETENTION_DAYS = 90


@celery_app.task(name="app.tasks.cleanup_synthetic_tenants.cleanup_old_synthetic_tenants")
def cleanup_old_synthetic_tenants():
    _run_async(_cleanup_async())


async def _cleanup_async():
    from app.database import get_db_context
    from app.models import Organization
    from sqlalchemy import select, delete

    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)

    async with get_db_context() as db:
        orgs = (await db.execute(
            select(Organization).where(
                Organization.is_synthetic == True,
                Organization.created_at < cutoff,
            )
        )).scalars().all()

        for org in orgs:
            age_days = (datetime.now(timezone.utc) - org.created_at).days
            await db.delete(org)   # CASCADE deletes all child rows
            logger.info("synthetic_tenant_deleted org_id=%s age_days=%d", org.id, age_days)

        await db.commit()
        logger.info("cleanup_synthetic_tenants: deleted %d tenants", len(orgs))
