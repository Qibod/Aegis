"""propose_profile_change — stage a change for user approval. Does NOT apply it."""
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

TOOL_DEF = {
    "name": "propose_profile_change",
    "description": "Propose a change to a profile field. Returns a diff for user approval. Does NOT apply the change.",
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_type": {"type": "string"},
            "entity_id":   {"type": "string"},
            "field_name":  {"type": "string"},
            "new_value":   {"description": "The proposed new value"},
            "rationale":   {"type": "string"},
        },
        "required": ["entity_type", "entity_id", "field_name", "new_value", "rationale"],
    },
}


async def handle(args: dict, org_id: UUID, db: AsyncSession, user_id: UUID | None = None) -> dict:
    from app.models import ProfileChangeLog
    import json

    # Read current value via read_field
    from app.assistant.tools.read_field import handle as read_field
    current = await read_field(
        {"entity_type": args["entity_type"], "entity_id": args["entity_id"], "field_name": args["field_name"]},
        org_id, db,
    )

    change = ProfileChangeLog(
        org_id=org_id,
        changed_by=user_id,
        entity_type=args["entity_type"],
        entity_id=UUID(args["entity_id"]) if args.get("entity_id") not in (None, "primary") else None,
        field_changed=args["field_name"],
        old_value={"value": current.get("value")},
        new_value={"value": args["new_value"]},
        change_summary=f"[assistant_proposal] {args['rationale']}",
        propagation_status="proposed",
    )
    db.add(change)
    await db.flush()

    return {
        "change_id": str(change.id),
        "entity_type": args["entity_type"],
        "field_name": args["field_name"],
        "current_value": current.get("value"),
        "proposed_value": args["new_value"],
        "rationale": args["rationale"],
        "status": "pending_approval",
    }
