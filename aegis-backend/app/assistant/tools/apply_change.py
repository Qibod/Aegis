"""apply_proposed_change — persist a previously proposed change after UI approval."""
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

TOOL_DEF = {
    "name": "apply_proposed_change",
    "description": "Apply a previously proposed change. Requires prior UI confirmation from the user.",
    "input_schema": {
        "type": "object",
        "properties": {
            "change_id": {"type": "string", "description": "UUID returned by propose_profile_change"},
        },
        "required": ["change_id"],
    },
}


async def handle(args: dict, org_id: UUID, db: AsyncSession, user_id: UUID | None = None) -> dict:
    from app.models import ProfileChangeLog, OrgProfile, LineOfBusiness, OrgGeography, OrgIndustry, OrgProduct, CustomerSegment, ThirdPartyDependency, DataTechProfile

    model_map = {
        "org_profiles": OrgProfile, "lines_of_business": LineOfBusiness,
        "org_geographies": OrgGeography, "org_industries": OrgIndustry,
        "org_products": OrgProduct, "org_customer_segments": CustomerSegment,
        "org_third_parties": ThirdPartyDependency, "org_data_tech_profiles": DataTechProfile,
    }

    change = (await db.execute(
        select(ProfileChangeLog).where(
            ProfileChangeLog.id == UUID(args["change_id"]),
            ProfileChangeLog.org_id == org_id,
        )
    )).scalar_one_or_none()

    if not change:
        return {"error": "Change not found"}
    if change.propagation_status != "proposed":
        return {"error": f"Change already in status: {change.propagation_status}"}

    model_cls = model_map.get(change.entity_type)
    if model_cls and change.entity_id and change.field_changed:
        entity = (await db.execute(
            select(model_cls).where(model_cls.id == change.entity_id)
        )).scalar_one_or_none()
        if entity:
            new_val = (change.new_value or {}).get("value")
            setattr(entity, change.field_changed, new_val)
            status_map = dict(entity.field_status_map or {})
            status_map[change.field_changed] = "user_edited"
            entity.field_status_map = status_map

    change.propagation_status = "applied"
    change.change_summary = change.change_summary.replace("[assistant_proposal]", "[grc_assistant]")
    await db.flush()

    return {"change_id": args["change_id"], "status": "applied", "field": change.field_changed}
