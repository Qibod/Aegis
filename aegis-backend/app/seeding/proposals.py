"""
app/seeding/proposals.py
─────────────────────────
Helpers for creating and resolving daily re-seed proposals.
"""
import logging
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SeedingProposal, Organization

logger = logging.getLogger(__name__)


async def create_proposal(
    db: AsyncSession,
    org_id: UUID,
    entity_type: str,
    entity_id: UUID,
    field_name: str,
    proposed_value,
    confidence: float,
    sources: list[str],
) -> SeedingProposal:
    proposal = SeedingProposal(
        org_id=org_id,
        entity_type=entity_type,
        entity_id=entity_id,
        field_name=field_name,
        proposed_value={"value": proposed_value},
        confidence=confidence,
        sources=sources,
        status="pending",
    )
    db.add(proposal)
    await db.flush()

    # Update badge count on the org
    pending = (await db.execute(
        select(func.count()).select_from(SeedingProposal).where(
            SeedingProposal.org_id == org_id,
            SeedingProposal.status == "pending",
        )
    )).scalar_one()
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if org:
        org.synthetic_proposals_pending = pending
    await db.flush()
    return proposal


async def get_pending(db: AsyncSession, org_id: UUID) -> list[SeedingProposal]:
    result = await db.execute(
        select(SeedingProposal)
        .where(SeedingProposal.org_id == org_id, SeedingProposal.status == "pending")
        .order_by(SeedingProposal.created_at.desc())
    )
    return result.scalars().all()
