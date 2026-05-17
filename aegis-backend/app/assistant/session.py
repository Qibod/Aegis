"""
app/assistant/session.py
─────────────────────────
Redis-backed assistant session lifecycle.
Key: assistant:session:{user_id}:{session_id}  TTL: 4 hours.
Sessions reset per PRD decision #3 — no cross-session memory.
"""
import json
import logging
from uuid import UUID, uuid4

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
SESSION_TTL = 4 * 3600   # 4 hours in seconds


def _get_redis():
    """Lazy Redis connection — falls back to in-memory dict for dev/test."""
    try:
        import redis
        return redis.from_url(settings.redis_url, decode_responses=True)
    except Exception:
        logger.warning("Redis unavailable — using in-memory session store")
        return _InMemoryStore()


class _InMemoryStore:
    """Development fallback when Redis is unavailable."""
    def __init__(self):
        self._data: dict = {}

    def get(self, key):
        return self._data.get(key)

    def setex(self, key, ttl, value):
        self._data[key] = value

    def delete(self, key):
        self._data.pop(key, None)

    def expire(self, key, ttl):
        pass


_store = None


def _redis():
    global _store
    if _store is None:
        _store = _get_redis()
    return _store


def _key(user_id: UUID, session_id: UUID) -> str:
    return f"assistant:session:{user_id}:{session_id}"


def create_session(user_id: UUID) -> UUID:
    """Create a new session and return its ID."""
    session_id = uuid4()
    _redis().setex(_key(user_id, session_id), SESSION_TTL, json.dumps([]))
    logger.debug("assistant session created user=%s session=%s", user_id, session_id)
    return session_id


def get_history(user_id: UUID, session_id: UUID) -> list[dict]:
    """Return message history for this session (empty list if expired/not found)."""
    raw = _redis().get(_key(user_id, session_id))
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def append_message(user_id: UUID, session_id: UUID, role: str, content) -> None:
    """Append a message to session history and refresh TTL."""
    key = _key(user_id, session_id)
    history = get_history(user_id, session_id)
    history.append({"role": role, "content": content})
    _redis().setex(key, SESSION_TTL, json.dumps(history))


def clear_session(user_id: UUID, session_id: UUID) -> None:
    """Explicitly clear a session (e.g. user opens new chat)."""
    _redis().delete(_key(user_id, session_id))
