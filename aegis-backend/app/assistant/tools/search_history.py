"""search_change_history — search the profile change log."""
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

TOOL_DEF = {
    "name": "search_change_history",
    "description": "Search the profile change history for this org.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search term (field name, entity type, or keyword)"},
            "limit": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    },
}


async def handle(args: dict, org_id: UUID, db: AsyncSession, **_) -> dict:
    from app.models import ProfileChangeLog

    q = args.get("query", "").lower()
    limit = min(int(args.get("limit", 10)), 50)

    rows = (await db.execute(
        select(ProfileChangeLog)
        .where(
            ProfileChangeLog.org_id == org_id,
            or_(
                ProfileChangeLog.entity_type.ilike(f"%{q}%"),
                ProfileChangeLog.field_changed.ilike(f"%{q}%"),
                ProfileChangeLog.change_summary.ilike(f"%{q}%"),
            ),
        )
        .order_by(ProfileChangeLog.changed_at.desc())
        .limit(limit)
    )).scalars().all()

    return {
        "results": [
            {
                "id": str(r.id),
                "entity_type": r.entity_type,
                "field": r.field_changed,
                "summary": r.change_summary,
                "changed_at": r.changed_at.isoformat() if r.changed_at else None,
            }
            for r in rows
        ]
    }
