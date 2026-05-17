"""request_revalidation — trigger Validator A for a specific field."""
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

TOOL_DEF = {
    "name": "request_revalidation",
    "description": "Trigger Validator A to re-verify a specific field.",
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_type": {"type": "string"},
            "entity_id":   {"type": "string"},
            "field_name":  {"type": "string"},
        },
        "required": ["entity_type", "entity_id", "field_name"],
    },
}


async def handle(args: dict, org_id: UUID, db: AsyncSession, **_) -> dict:
    from app.workers.tasks import celery_app
    celery_app.send_task(
        "app.workers.tasks.run_validation_for_field",
        kwargs={
            "org_id": str(org_id),
            "entity_type": args["entity_type"],
            "entity_id": args["entity_id"],
            "field_name": args["field_name"],
        },
    )
    return {"status": "queued", "field": args["field_name"]}
