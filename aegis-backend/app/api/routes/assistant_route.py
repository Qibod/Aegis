"""app/api/routes/assistant_route.py — GRC Assistant WebSocket endpoint."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_active_user, get_org_id
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/assistant", tags=["grc-assistant"])


@router.websocket("/ws")
async def assistant_ws(
    websocket: WebSocket,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    WebSocket endpoint for the GRC Assistant.
    Auth is passed in the first message: {"type": "auth", "token": "<jwt>"}
    """
    from app.api.auth import decode_access_token
    from app.models import User
    from sqlalchemy import select

    await websocket.accept()
    try:
        auth_msg = await websocket.receive_json()
        if auth_msg.get("type") != "auth":
            await websocket.close(code=4001)
            return

        token = auth_msg.get("token", "")
        payload = decode_access_token(token)
        if not payload:
            await websocket.close(code=4001)
            return

        user = (await db.execute(
            select(User).where(User.id == UUID(payload["sub"]))
        )).scalar_one_or_none()
        if not user or not user.is_active:
            await websocket.close(code=4001)
            return

        from app.assistant.chat_handler import handle_ws
        await handle_ws(
            websocket=websocket,
            org_id=user.org_id,
            user_id=user.id,
            user_role=user.role,
            db=db,
        )
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close(code=4000)
        except Exception:
            pass
