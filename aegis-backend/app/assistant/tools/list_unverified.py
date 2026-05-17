"""list_unverified_fields — list fields without a verification tick."""
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

TOOL_DEF = {
    "name": "list_unverified_fields",
    "description": "List all profile fields that don't have a verification tick (not verified or verified_after_dispute).",
    "input_schema": {
        "type": "object",
        "properties": {
            "scope": {"type": "string", "description": "Entity type to filter, or 'all'", "default": "all"},
        },
    },
}

VERIFIED = {"verified", "verified_after_dispute"}


async def handle(args: dict, org_id: UUID, db: AsyncSession, **_) -> dict:
    from app.models import OrgProfile
    from app.seeding.field_specs import FIELD_SPECS

    profile = (await db.execute(
        select(OrgProfile).where(OrgProfile.org_id == org_id)
    )).scalar_one_or_none()
    if not profile:
        return {"unverified": []}

    status_map = profile.field_status_map or {}
    scope = args.get("scope", "all")

    unverified = []
    for entity_type, specs in FIELD_SPECS.items():
        if scope != "all" and scope != entity_type:
            continue
        for spec in specs:
            s = status_map.get(spec.name, "unknown")
            if s not in VERIFIED:
                unverified.append({"entity_type": entity_type, "field": spec.name, "status": s})

    return {"unverified": unverified, "count": len(unverified)}
