"""app/api/routes/validation_route.py — verification state, verify-this, proposals."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_active_user, get_org_id
from app.database import get_db
from app.models import User, SeedingProposal, FieldValidation, OrgProfile
from app.assistant.permissions import require_resolve_flagged, require_approve_proposal

router = APIRouter(prefix="/validation", tags=["validation"])


@router.get("/state/{entity_type}/{entity_id}")
async def get_verification_state(
    entity_type: str,
    entity_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_active_user)],
):
    """Return the latest validation state for all fields of an entity."""
    rows = (await db.execute(
        select(FieldValidation)
        .where(
            FieldValidation.org_id == org_id,
            FieldValidation.entity_type == entity_type,
            FieldValidation.entity_id == entity_id,
        )
        .order_by(FieldValidation.validated_at.desc())
    )).scalars().all()

    # Group by field, keep latest A and B per field
    state: dict[str, dict] = {}
    for row in rows:
        if row.field_name not in state:
            state[row.field_name] = {"a": None, "b": None}
        key = row.validator.lower() if row.validator in ("A", "B") else None
        if key and state[row.field_name][key] is None:
            state[row.field_name][key] = {
                "status": row.status,
                "confidence": row.confidence,
                "sources": row.sources,
                "proposed_alternative": row.proposed_alternative,
                "validated_at": row.validated_at.isoformat() if row.validated_at else None,
            }

    return {"entity_type": entity_type, "entity_id": str(entity_id), "fields": state}


@router.post("/verify/{entity_type}/{entity_id}/{field_name}")
async def verify_field(
    entity_type: str,
    entity_id: UUID,
    field_name: str,
    org_id: Annotated[UUID, Depends(get_org_id)],
    _user: Annotated[User, Depends(get_current_active_user)],
):
    """Queue Validator A for a specific field (per-field 'Verify this' action)."""
    from app.workers.tasks import celery_app
    celery_app.send_task(
        "app.workers.tasks.run_validation_for_field",
        kwargs={
            "org_id": str(org_id),
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "field_name": field_name,
        },
    )
    return {"status": "queued", "field": field_name}


@router.post("/resolve/{validation_id}")
async def resolve_flagged_field(
    validation_id: UUID,
    body: dict,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_active_user)],
):
    """Resolve a flagged_for_review field (three-option resolution UI)."""
    require_resolve_flagged(user)

    fv = (await db.execute(
        select(FieldValidation).where(
            FieldValidation.id == validation_id,
            FieldValidation.org_id == org_id,
        )
    )).scalar_one_or_none()
    if not fv:
        raise HTTPException(404, "Validation record not found")

    chosen_value = body.get("chosen_value")
    resolution_source = body.get("resolution_source", "user")   # "seeded"|"alternative"|"user_input"

    # Write user resolution record
    user_fv = FieldValidation(
        org_id=org_id,
        entity_type=fv.entity_type,
        entity_id=fv.entity_id,
        field_name=fv.field_name,
        validator="user",
        status="user_resolved",
        seeded_value=fv.seeded_value,
        proposed_alternative=fv.proposed_alternative,
        sources=[body.get("source_note", "")],
        notes=f"User selected: {resolution_source}",
        confidence=1.0,
        resolution_source=resolution_source,
        duration_ms=0,
    )
    db.add(user_fv)

    # Apply chosen value to the entity
    await _apply_to_entity(db, org_id, fv.entity_type, fv.entity_id, fv.field_name, chosen_value)
    await db.commit()
    return {"status": "resolved", "field": fv.field_name, "resolution_source": resolution_source}


# ── Proposals ─────────────────────────────────────────────────────────────────

@router.get("/proposals")
async def list_proposals(
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_active_user)],
):
    rows = (await db.execute(
        select(SeedingProposal)
        .where(SeedingProposal.org_id == org_id, SeedingProposal.status == "pending")
        .order_by(SeedingProposal.created_at.desc())
    )).scalars().all()

    return {
        "proposals": [
            {
                "id": str(p.id),
                "entity_type": p.entity_type,
                "entity_id": str(p.entity_id),
                "field_name": p.field_name,
                "proposed_value": p.proposed_value,
                "confidence": p.confidence,
                "sources": p.sources,
                "created_at": p.created_at.isoformat(),
            }
            for p in rows
        ]
    }


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_active_user)],
):
    require_approve_proposal(user)
    from datetime import datetime, timezone

    proposal = (await db.execute(
        select(SeedingProposal).where(
            SeedingProposal.id == proposal_id, SeedingProposal.org_id == org_id
        )
    )).scalar_one_or_none()
    if not proposal or proposal.status != "pending":
        raise HTTPException(404, "Proposal not found or already resolved")

    proposed_val = (proposal.proposed_value or {}).get("value")
    await _apply_to_entity(db, org_id, proposal.entity_type, proposal.entity_id, proposal.field_name, proposed_val)

    proposal.status = "approved"
    proposal.resolved_at = datetime.now(timezone.utc)
    proposal.resolved_by = user.id

    # Queue validation for the newly applied value
    from app.workers.tasks import celery_app
    celery_app.send_task(
        "app.workers.tasks.run_validation_for_field",
        kwargs={
            "org_id": str(org_id),
            "entity_type": proposal.entity_type,
            "entity_id": str(proposal.entity_id),
            "field_name": proposal.field_name,
        },
    )
    await db.commit()
    return {"status": "approved", "proposal_id": str(proposal_id)}


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: UUID,
    org_id: Annotated[UUID, Depends(get_org_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_active_user)],
):
    require_approve_proposal(user)
    from datetime import datetime, timezone

    proposal = (await db.execute(
        select(SeedingProposal).where(
            SeedingProposal.id == proposal_id, SeedingProposal.org_id == org_id
        )
    )).scalar_one_or_none()
    if not proposal or proposal.status != "pending":
        raise HTTPException(404, "Proposal not found or already resolved")

    proposal.status = "rejected"
    proposal.resolved_at = datetime.now(timezone.utc)
    proposal.resolved_by = user.id
    await db.commit()
    return {"status": "rejected", "proposal_id": str(proposal_id)}


# ── Helper ────────────────────────────────────────────────────────────────────

async def _apply_to_entity(db, org_id: UUID, entity_type: str, entity_id: UUID, field_name: str, value):
    from app.models import OrgProfile, LineOfBusiness, OrgGeography, OrgIndustry, OrgProduct, CustomerSegment, ThirdPartyDependency, DataTechProfile

    model_map = {
        "org_profiles": OrgProfile, "lines_of_business": LineOfBusiness,
        "org_geographies": OrgGeography, "org_industries": OrgIndustry,
        "org_products": OrgProduct, "org_customer_segments": CustomerSegment,
        "org_third_parties": ThirdPartyDependency, "org_data_tech_profiles": DataTechProfile,
    }
    model_cls = model_map.get(entity_type)
    if not model_cls:
        return
    entity = (await db.execute(
        select(model_cls).where(model_cls.id == entity_id, model_cls.org_id == org_id)
    )).scalar_one_or_none()
    if entity and hasattr(entity, field_name):
        setattr(entity, field_name, value)
        status_map = dict(entity.field_status_map or {})
        status_map[field_name] = "user_edited"
        entity.field_status_map = status_map
