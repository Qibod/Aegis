"""
app/assistant/chat_handler.py
───────────────────────────────
WebSocket handler for the GRC Assistant.
Runs a Claude tool-use loop, emits streamed responses, and logs interactions.
"""
import json
import logging
from uuid import UUID

from anthropic import AsyncAnthropic
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant import session as session_store
from app.assistant.safety_rails import SYSTEM_PROMPT, classify_intent
from app.assistant.tools import ALL_TOOL_DEFS, TOOL_HANDLERS
from app.config import get_settings
from app.models import AssistantInteraction

logger = logging.getLogger(__name__)
settings = get_settings()
claude = AsyncAnthropic(api_key=settings.anthropic_api_key)


async def handle_ws(
    websocket: WebSocket,
    org_id: UUID,
    user_id: UUID,
    user_role: str,
    db: AsyncSession,
):
    """Main WS handler. Maintains one Claude session per connection."""
    session_id = session_store.create_session(user_id)
    await websocket.send_json({
        "type": "session_start",
        "session_id": str(session_id),
        "message": "Conversations reset between sessions. I won't remember our previous chats.",
    })

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type", "message")

            if msg_type == "new_session":
                session_store.clear_session(user_id, session_id)
                session_id = session_store.create_session(user_id)
                await websocket.send_json({"type": "session_reset", "session_id": str(session_id)})
                continue

            if msg_type == "apply_change":
                # UI confirmed a proposed change — apply it
                change_id = data.get("change_id")
                result = await TOOL_HANDLERS["apply_proposed_change"](
                    {"change_id": change_id}, org_id, db, user_id,
                )
                await db.commit()
                await websocket.send_json({"type": "change_applied", "result": result})
                continue

            user_text = data.get("content", "")
            if not user_text:
                continue

            session_store.append_message(user_id, session_id, "user", user_text)
            _log_interaction(db, org_id, user_id, session_id, "user", user_text)

            history = session_store.get_history(user_id, session_id)
            response_text = await _run_tool_loop(
                messages=history,
                org_id=org_id,
                user_id=user_id,
                user_role=user_role,
                db=db,
                websocket=websocket,
                session_id=session_id,
            )

            session_store.append_message(user_id, session_id, "assistant", response_text)
            _log_interaction(db, org_id, user_id, session_id, "assistant", response_text)
            await db.commit()

    except WebSocketDisconnect:
        logger.debug("assistant WS disconnected user=%s", user_id)
    except Exception as exc:
        logger.error("assistant WS error: %s", exc, exc_info=True)
        try:
            await websocket.send_json({"type": "error", "detail": "Internal error. Please try again."})
        except Exception:
            pass


async def _run_tool_loop(
    messages: list[dict],
    org_id: UUID,
    user_id: UUID,
    user_role: str,
    db: AsyncSession,
    websocket: WebSocket,
    session_id: UUID,
) -> str:
    """Run Claude with tool use until no more tool calls, streaming responses."""
    context_messages = [{"role": m["role"], "content": m["content"]} for m in messages]

    while True:
        response = await claude.messages.create(
            model="claude-opus-4-7",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOL_DEFS,
            messages=context_messages,
        )

        text_parts = [b.text for b in response.content if hasattr(b, "text") and b.text]
        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if text_parts:
            text = "\n".join(text_parts)
            await websocket.send_json({"type": "assistant_message", "content": text})

        if not tool_uses:
            return "\n".join(text_parts)

        # Execute each tool call
        tool_results = []
        for tool_use in tool_uses:
            handler = TOOL_HANDLERS.get(tool_use.name)
            if not handler:
                result = {"error": f"Unknown tool: {tool_use.name}"}
            else:
                try:
                    result = await handler(tool_use.input, org_id, db, user_id=user_id)
                except Exception as exc:
                    result = {"error": str(exc)}

            # Emit tool result event for change proposals
            if tool_use.name == "propose_profile_change" and "change_id" in result:
                await websocket.send_json({"type": "change_proposal", **result})

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": json.dumps(result),
            })

        # Add assistant turn + tool results to context for next loop
        context_messages.append({"role": "assistant", "content": response.content})
        context_messages.append({"role": "user", "content": tool_results})


def _log_interaction(db: AsyncSession, org_id: UUID, user_id: UUID, session_id: UUID, role: str, content) -> None:
    db.add(AssistantInteraction(
        org_id=org_id,
        user_id=user_id,
        session_id=session_id,
        role=role,
        content={"text": content} if isinstance(content, str) else content,
    ))
