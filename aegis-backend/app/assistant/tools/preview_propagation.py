"""preview_propagation — show downstream effects of a proposed change."""
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

TOOL_DEF = {
    "name": "preview_propagation",
    "description": "Preview downstream effects of a proposed change before applying it.",
    "input_schema": {
        "type": "object",
        "properties": {
            "change_id": {"type": "string"},
        },
        "required": ["change_id"],
    },
}


async def handle(args: dict, org_id: UUID, db: AsyncSession, **_) -> dict:
    from app.models import ProfileChangeLog
    from app.ai.propagation import preview_propagation as _preview

    change = (await db.execute(
        select(ProfileChangeLog).where(
            ProfileChangeLog.id == UUID(args["change_id"]),
            ProfileChangeLog.org_id == org_id,
        )
    )).scalar_one_or_none()

    if not change:
        return {"error": "Change not found"}

    try:
        preview = await _preview(change, org_id, db)
        return {"change_id": args["change_id"], "preview": preview}
    except Exception as exc:
        return {"change_id": args["change_id"], "preview": {"affected_modules": [], "note": str(exc)}}
