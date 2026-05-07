"""
app/realtime/websocket.py
─────────────────────────
WebSocket connection manager for:
  1. Canvas collaboration — live cursors, node updates, edge creation
  2. Signal delivery — push new radar signals to connected clients
  3. Pulse alerts — push control failures in real time

Each org gets its own "room". Messages are JSON with a `type` field.
"""
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect


# ── Message types ─────────────────────────────────────────────────────────────
# Client → Server
MSG_CURSOR_MOVE   = "cursor_move"     # {x, y}
MSG_NODE_MOVE     = "node_move"       # {node_id, x, y}
MSG_NODE_CREATE   = "node_create"     # {node_type, pos_x, pos_y, ...}
MSG_EDGE_CREATE   = "edge_create"     # {from_node_id, to_node_id, edge_type}
MSG_TASK_UPDATE   = "task_update"     # {task_id, status}
MSG_PING          = "ping"

# Server → Client
MSG_CURSOR_UPDATE = "cursor_update"   # {user_id, name, initials, x, y}
MSG_NODE_UPDATED  = "node_updated"    # full node payload
MSG_EDGE_CREATED  = "edge_created"    # full edge payload
MSG_SIGNAL_NEW    = "signal_new"      # new radar signal
MSG_PULSE_ALERT   = "pulse_alert"     # control pulse failure
MSG_TASK_UPDATED  = "task_updated"    # task status change
MSG_PONG          = "pong"


@dataclass
class ConnectedClient:
    websocket: WebSocket
    user_id: str
    org_id: str
    full_name: str
    initials: str
    avatar_color: str
    cursor_x: float = 0.0
    cursor_y: float = 0.0


class ConnectionManager:
    """
    Manages WebSocket connections grouped by org_id.
    Thread-safe for async use — one event loop assumed.
    """

    def __init__(self):
        # org_id -> list of connected clients
        self._rooms: dict[str, list[ConnectedClient]] = {}

    async def connect(self, websocket: WebSocket, client: ConnectedClient) -> None:
        await websocket.accept()
        org_id = client.org_id
        if org_id not in self._rooms:
            self._rooms[org_id] = []
        self._rooms[org_id].append(client)

        # Notify others in the room
        await self._broadcast_to_room(
            org_id=org_id,
            message={
                "type": MSG_CURSOR_UPDATE,
                "user_id": client.user_id,
                "name": client.full_name,
                "initials": client.initials,
                "color": client.avatar_color,
                "x": 0,
                "y": 0,
                "online": True,
            },
            exclude_user=None,  # tell everyone, including the new user
        )

    async def disconnect(self, client: ConnectedClient) -> None:
        org_id = client.org_id
        room = self._rooms.get(org_id, [])
        if client in room:
            room.remove(client)
        if not room:
            self._rooms.pop(org_id, None)

        # Notify others the user went offline
        await self._broadcast_to_room(
            org_id=org_id,
            message={
                "type": MSG_CURSOR_UPDATE,
                "user_id": client.user_id,
                "online": False,
            },
        )

    async def handle_message(self, client: ConnectedClient, raw: str) -> None:
        """Route incoming client messages."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type")

        if msg_type == MSG_PING:
            await self._send(client.websocket, {"type": MSG_PONG})

        elif msg_type == MSG_CURSOR_MOVE:
            client.cursor_x = msg.get("x", 0)
            client.cursor_y = msg.get("y", 0)
            await self._broadcast_to_room(
                org_id=client.org_id,
                message={
                    "type": MSG_CURSOR_UPDATE,
                    "user_id": client.user_id,
                    "name": client.full_name,
                    "initials": client.initials,
                    "color": client.avatar_color,
                    "x": client.cursor_x,
                    "y": client.cursor_y,
                    "online": True,
                },
                exclude_user=client.user_id,
            )

        elif msg_type == MSG_NODE_MOVE:
            # Broadcast node position update to all other clients
            await self._broadcast_to_room(
                org_id=client.org_id,
                message={
                    "type": MSG_NODE_UPDATED,
                    "node_id": msg.get("node_id"),
                    "pos_x": msg.get("x"),
                    "pos_y": msg.get("y"),
                    "moved_by": client.user_id,
                },
                exclude_user=client.user_id,
            )

    async def push_signal(self, org_id: str, signal: dict[str, Any]) -> None:
        """Push a new radar signal to all clients in an org room."""
        await self._broadcast_to_room(
            org_id=org_id,
            message={
                "type": MSG_SIGNAL_NEW,
                "signal": signal,
            },
        )

    async def push_pulse_alert(self, org_id: str, control_name: str, status: str, metrics: dict) -> None:
        """Push a control failure notification."""
        await self._broadcast_to_room(
            org_id=org_id,
            message={
                "type": MSG_PULSE_ALERT,
                "control_name": control_name,
                "status": status,
                "metrics": metrics,
            },
        )

    def get_online_users(self, org_id: str) -> list[dict[str, Any]]:
        """Return list of currently connected users in an org."""
        return [
            {
                "user_id": c.user_id,
                "full_name": c.full_name,
                "initials": c.initials,
                "color": c.avatar_color,
                "cursor_x": c.cursor_x,
                "cursor_y": c.cursor_y,
            }
            for c in self._rooms.get(org_id, [])
        ]

    # ── Internal ────────────────────────────────────────────────────────────

    async def _broadcast_to_room(
        self,
        org_id: str,
        message: dict[str, Any],
        exclude_user: str | None = None,
    ) -> None:
        room = self._rooms.get(org_id, [])
        disconnected = []
        for client in room:
            if exclude_user and client.user_id == exclude_user:
                continue
            try:
                await self._send(client.websocket, message)
            except Exception:
                disconnected.append(client)

        for client in disconnected:
            await self.disconnect(client)

    @staticmethod
    async def _send(websocket: WebSocket, message: dict[str, Any]) -> None:
        await websocket.send_text(json.dumps(message))


# Singleton — shared across the app
manager = ConnectionManager()


# ── FastAPI WebSocket endpoint ─────────────────────────────────────────────────

from fastapi import APIRouter, Depends, Query
from app.api.auth import decode_token
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import User

ws_router = APIRouter(tags=["websocket"])


@ws_router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    WebSocket endpoint.
    Client connects with: ws://host/ws?token=<access_token>
    """
    # Authenticate via JWT in query param (headers not supported in WS)
    try:
        claims = decode_token(token)
        user_id = claims.get("sub")
        org_id = claims.get("org_id")
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Load user details
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        await websocket.close(code=4003, reason="User not found")
        return

    client = ConnectedClient(
        websocket=websocket,
        user_id=str(user.id),
        org_id=str(user.org_id),
        full_name=user.full_name,
        initials=user.initials or "",
        avatar_color=user.avatar_color,
    )

    await manager.connect(websocket, client)

    try:
        while True:
            data = await websocket.receive_text()
            await manager.handle_message(client, data)
    except WebSocketDisconnect:
        await manager.disconnect(client)
