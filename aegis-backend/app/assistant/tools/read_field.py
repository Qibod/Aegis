"""get_profile_field — read any profile field for the current org."""
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

TOOL_DEF = {
    "name": "get_profile_field",
    "description": "Read the current value of any Company Profile field for this org.",
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_type": {"type": "string", "description": "e.g. org_profiles, lines_of_business"},
            "entity_id":   {"type": "string", "description": "UUID of the entity, or 'primary' for org_profiles"},
            "field_name":  {"type": "string", "description": "The field name to read"},
        },
        "required": ["entity_type", "field_name"],
    },
}


async def handle(args: dict, org_id: UUID, db: AsyncSession) -> dict:
    from app.models import OrgProfile, LineOfBusiness, OrgGeography, OrgIndustry, OrgProduct, CustomerSegment, ThirdPartyDependency, DataTechProfile
    from sqlalchemy import select

    model_map = {
        "org_profiles": OrgProfile, "lines_of_business": LineOfBusiness,
        "org_geographies": OrgGeography, "org_industries": OrgIndustry,
        "org_products": OrgProduct, "org_customer_segments": CustomerSegment,
        "org_third_parties": ThirdPartyDependency, "org_data_tech_profiles": DataTechProfile,
    }
    entity_type = args["entity_type"]
    field_name = args["field_name"]
    model_cls = model_map.get(entity_type)
    if not model_cls:
        return {"error": f"Unknown entity_type: {entity_type}"}

    entity_id_raw = args.get("entity_id")
    if entity_id_raw and entity_id_raw != "primary":
        entity = (await db.execute(
            select(model_cls).where(model_cls.id == UUID(entity_id_raw), model_cls.org_id == org_id)
        )).scalar_one_or_none()
    else:
        entity = (await db.execute(
            select(model_cls).where(model_cls.org_id == org_id)
        )).scalar_one_or_none()

    if not entity:
        return {"error": "Entity not found"}

    value = getattr(entity, field_name, None)
    status = (entity.field_status_map or {}).get(field_name, "unknown")
    sources = (entity.field_source_map or {}).get(field_name, [])
    return {"field": field_name, "value": value, "status": status, "sources": sources}
