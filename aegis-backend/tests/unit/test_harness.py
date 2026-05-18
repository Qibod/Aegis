"""tests/unit/test_harness.py — proves the test harness boots."""
import pytest


def test_pytest_runs():
    assert True


@pytest.mark.asyncio
async def test_async_runs():
    import asyncio
    await asyncio.sleep(0)
    assert True


@pytest.mark.asyncio
async def test_db_fixture_provides_session(db):
    from sqlalchemy import text
    result = await db.execute(text("SELECT 1"))
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_http_client_serves_a_response(http_client):
    resp = await http_client.get("/health")
    assert resp.status_code in (200, 404)


def test_companies_fixture_has_five(test_companies):
    assert set(test_companies.keys()) == {"uber", "stripe", "anthropic", "maersk", "acme_shell_001"}


def test_mock_claude_bank_raises_on_unknown_fixture(mock_claude):
    with pytest.raises(AssertionError, match="Missing Claude fixture"):
        mock_claude.for_call(agent="seeder", company="nonexistent_company", field="legal_name")
