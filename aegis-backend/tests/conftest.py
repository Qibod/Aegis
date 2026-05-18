"""
tests/conftest.py
─────────────────
Shared fixtures: ephemeral async DB, mock-Claude bank, test-companies loader,
fakeredis, and an httpx AsyncClient bound to the FastAPI app.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


FIXTURES_DIR = Path(__file__).parent / "fixtures"
CLAUDE_RESPONSES_DIR = FIXTURES_DIR / "claude_responses"

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/aegis_test",
)


# ── DB ────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function")
async def db_engine():
    from app.database import Base
    engine = create_async_engine(TEST_DB_URL, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db(db_engine):
    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        yield session


# ── HTTP client ───────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function")
async def http_client(db_engine):
    from app.database import get_db
    from app.main import app

    Session = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ── Mock Claude ───────────────────────────────────────────────────────────────

class MockClaudeBank:
    """Returns canned responses keyed by (agent, company, field).

    Raises AssertionError on unknown keys — forces tests to declare fixtures
    explicitly. No silent fallback (most common source of false-green LLM tests).
    """

    def __init__(self):
        self._cache: dict[str, dict] = {}
        self._calls: list[dict] = []

    def for_call(self, agent: str, company: str, field: str) -> dict:
        key = f"{agent}__{company}__{field}.json"
        self._calls.append({"agent": agent, "company": company, "field": field})
        if key in self._cache:
            return self._cache[key]
        path = CLAUDE_RESPONSES_DIR / key
        if not path.exists():
            raise AssertionError(
                f"Missing Claude fixture: {key}.\n"
                f"  Record it (LIVE_CLAUDE=1 python tests/scripts/record_fixtures.py "
                f"--agent {agent} --company {company} --field {field}) "
                f"or add a stub JSON to tests/fixtures/claude_responses/."
            )
        data = json.loads(path.read_text())
        self._cache[key] = data
        return data

    @property
    def calls(self) -> list[dict]:
        return list(self._calls)


@pytest.fixture
def mock_claude(monkeypatch) -> MockClaudeBank:
    """Patches the Anthropic SDK with the MockClaudeBank.

    Seeder/validator system prompts must include `# META: agent=X company=Y field=Z`.
    """
    bank = MockClaudeBank()
    import anthropic

    class _FakeBlock:
        def __init__(self, text: str):
            self.type = "text"
            self.text = text

    class _FakeAnthropicResponse:
        def __init__(self, payload):
            self.content = [_FakeBlock(json.dumps(payload))]
            self.stop_reason = "end_turn"

    class _FakeMessages:
        async def create(self, **kwargs):
            meta = _extract_meta(kwargs)
            resp = bank.for_call(**meta)
            return _FakeAnthropicResponse(resp)

    class _FakeClient:
        def __init__(self, *a, **kw):
            self.messages = _FakeMessages()

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeClient)
    return bank


def _extract_meta(kwargs: dict) -> dict[str, str]:
    """Extract (agent, company, field) from Anthropic call kwargs.

    Convention: seeder/validator system prompts begin with
        `# META: agent=<name> company=<slug> field=<name>`
    """
    system = kwargs.get("system") or ""
    if isinstance(system, list):
        system = " ".join(b.get("text", "") for b in system if isinstance(b, dict))
    msgs = kwargs.get("messages") or []
    haystack = system + " " + " ".join(
        m.get("content", "") if isinstance(m.get("content"), str) else "" for m in msgs
    )
    parts = {}
    for tag in ("agent", "company", "field"):
        marker = f"{tag}="
        if marker in haystack:
            tail = haystack.split(marker, 1)[1]
            parts[tag] = tail.split()[0].strip(",.;")
    if set(parts) != {"agent", "company", "field"}:
        raise AssertionError(
            f"Could not extract meta from Claude call. Tests must call agents with "
            f"`# META: agent=... company=... field=...` in the system prompt. Got: {parts!r}"
        )
    return parts


# ── Live Claude (opt-in) ──────────────────────────────────────────────────────

@pytest.fixture
def live_claude():
    if os.getenv("LIVE_CLAUDE") != "1":
        pytest.skip("Set LIVE_CLAUDE=1 to run this test against live Claude.")
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.fail("LIVE_CLAUDE=1 but ANTHROPIC_API_KEY is not set.")
    return True


# ── Test companies ────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def test_companies() -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / "test_companies.json").read_text())


@pytest.fixture(scope="session")
def golden_values() -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / "golden_seeded_values.json").read_text())


# ── fakeredis ─────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_redis(monkeypatch):
    """Patches app.assistant.session._store with an in-memory fakeredis instance.

    session.py holds the Redis connection in a module-global `_store` variable,
    which is initialised lazily by _redis(). We bypass the lazy init entirely by
    patching _store directly so that every _redis() call returns our fake instance.

    NOTE: fakeredis.aioredis is used if available; the session module currently
    uses synchronous redis calls (setex/get/delete), so FakeRedis (sync) is the
    correct variant.
    """
    try:
        import fakeredis
        fake = fakeredis.FakeRedis(decode_responses=True)
    except ImportError:
        pytest.skip("fakeredis not installed — run `pip install fakeredis`")
        return  # unreachable, satisfies type checkers

    import app.assistant.session as _session_module
    monkeypatch.setattr(_session_module, "_store", fake)
    # Also reset the global so teardown of one test doesn't bleed into the next
    yield fake
    monkeypatch.setattr(_session_module, "_store", None)
