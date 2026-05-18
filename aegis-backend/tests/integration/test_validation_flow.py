"""
tests/integration/test_validation_flow.py — TC-V-* (PRD §3.2.3).

10 Critical + High tests covering Validator A → B flow.
4 tests skipped pending uber_disputed fixture set.
"""
from __future__ import annotations

import time

import pytest
from sqlalchemy import select

from app.models import FieldValidation, OrgProfile
from tests.integration._helpers import onboard_test_org


# ── TC-V-01: Critical ─────────────────────────────────────────────────────────
@pytest.mark.needs_live_claude
@pytest.mark.asyncio
async def test_TC_V_01_validator_a_runs_on_seeded_fields(db, mock_claude, test_companies):
    """After seeding, Validator A produces a FieldValidation row for each seeded field."""
    org = await onboard_test_org(db, "uber", test_companies)
    rows = (await db.execute(
        select(FieldValidation).where(
            FieldValidation.org_id == org.id, FieldValidation.validator == "A"
        )
    )).scalars().all()
    assert len(rows) >= 5, f"expected ≥5 Validator A rows, got {len(rows)}"


# ── TC-V-02: Critical ─────────────────────────────────────────────────────────
@pytest.mark.needs_live_claude
@pytest.mark.asyncio
async def test_TC_V_02_validator_a_status_is_valid(db, mock_claude, test_companies):
    """Validator A status is one of {verified, disputed, unverifiable}."""
    org = await onboard_test_org(db, "uber", test_companies)
    rows = (await db.execute(
        select(FieldValidation).where(
            FieldValidation.org_id == org.id, FieldValidation.validator == "A"
        )
    )).scalars().all()
    for row in rows:
        assert row.status in {"verified", "disputed", "unverifiable"}, \
            f"{row.field_name}: {row.status}"


# ── TC-V-03: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_V_03_disputed_triggers_validator_b(db, mock_claude, test_companies):
    """Any 'disputed' A-row is followed by a Validator B row."""
    pytest.skip("Pending uber_disputed fixture set — requires recorded fixtures producing disputed verdicts")


# ── TC-V-04: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_V_04_validator_b_disagrees_yields_flagged_for_review(db, mock_claude, test_companies):
    """When B disagrees, final status is flagged_for_review and seeded_value is preserved."""
    pytest.skip("Pending uber_disputed fixture set")


# ── TC-V-05: High ─────────────────────────────────────────────────────────────
@pytest.mark.needs_live_claude
@pytest.mark.asyncio
async def test_TC_V_05_uber_critical_fields_verified(db, mock_claude, test_companies):
    """For Uber, key fields end at verified or verified_after_dispute."""
    org = await onboard_test_org(db, "uber", test_companies)
    profile = (await db.execute(select(OrgProfile).where(OrgProfile.org_id == org.id))).scalar_one()
    status_map = profile.field_status_map or {}
    for field in ("legal_name", "hq_country", "stock_ticker"):
        assert status_map.get(field) in ("verified", "verified_after_dispute"), \
            f"{field}: {status_map.get(field)!r}"


# ── TC-V-06: High ─────────────────────────────────────────────────────────────
@pytest.mark.needs_live_claude
@pytest.mark.asyncio
async def test_TC_V_06_validation_within_120s(db, mock_claude, test_companies):
    """Validation completes within 120s of onboarding finishing (mocked Claude is instant)."""
    start = time.perf_counter()
    await onboard_test_org(db, "uber", test_companies)
    assert time.perf_counter() - start < 120


# ── TC-V-07: Critical ─────────────────────────────────────────────────────────
@pytest.mark.needs_live_claude
@pytest.mark.asyncio
async def test_TC_V_07_verified_fields_have_source_urls(db, mock_claude, test_companies):
    """Every Validator A row with status='verified' has ≥ 1 source URL."""
    org = await onboard_test_org(db, "uber", test_companies)
    rows = (await db.execute(
        select(FieldValidation).where(
            FieldValidation.org_id == org.id,
            FieldValidation.validator == "A",
            FieldValidation.status == "verified",
        )
    )).scalars().all()
    for row in rows:
        assert row.sources and len(row.sources) >= 1, \
            f"{row.field_name} verified but no sources"


# ── TC-V-08: Critical ─────────────────────────────────────────────────────────
@pytest.mark.needs_live_claude
@pytest.mark.asyncio
async def test_TC_V_08_verified_field_locked_against_silent_reseed(db, mock_claude, test_companies):
    """A 'verified' field cannot be silently changed by a re-seed."""
    from app.tasks.reseed_unknowns import reseed_unknown_fields_for_org
    org = await onboard_test_org(db, "uber", test_companies)
    profile = (await db.execute(select(OrgProfile).where(OrgProfile.org_id == org.id))).scalar_one()
    locked_value = profile.legal_name
    await reseed_unknown_fields_for_org(org.id)
    await db.refresh(profile)
    assert profile.legal_name == locked_value


# ── TC-V-09: High ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_V_09_qa_sample_runs_b_on_5pct(db, mock_claude, test_companies):
    """~5% of verified A-fields are reviewed by B as QA sample (probabilistic)."""
    pytest.skip("Skipping; requires multi-onboard scaffolding for probabilistic assertion")


# ── TC-V-10: High ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_V_10_qa_failure_triggers_batch_revalidation(db, mock_claude, test_companies):
    """If B disagrees with QA-sample A verdict, all of A's verified fields are re-validated."""
    pytest.skip("Pending QA-fail fixture set + batch-revalidation hook")


# ── Live-Claude variants (nightly only) ───────────────────────────────────────

@pytest.mark.needs_live_claude
@pytest.mark.asyncio
async def test_TC_V_05_LIVE(db, live_claude, test_companies):
    """Real Claude: Uber key fields reach verified or verified_after_dispute."""
    org = await onboard_test_org(db, "uber", test_companies)
    profile = (await db.execute(select(OrgProfile).where(OrgProfile.org_id == org.id))).scalar_one()
    status_map = profile.field_status_map or {}
    for field in ("legal_name", "hq_country", "stock_ticker"):
        assert status_map.get(field) in ("verified", "verified_after_dispute"), \
            f"{field}: {status_map.get(field)!r}"


@pytest.mark.needs_live_claude
@pytest.mark.asyncio
async def test_TC_V_07_LIVE(db, live_claude, test_companies):
    """Real Claude: every verified A-row has ≥ 1 source URL."""
    org = await onboard_test_org(db, "uber", test_companies)
    rows = (await db.execute(
        select(FieldValidation).where(
            FieldValidation.org_id == org.id,
            FieldValidation.validator == "A",
            FieldValidation.status == "verified",
        )
    )).scalars().all()
    for row in rows:
        assert row.sources and len(row.sources) >= 1, \
            f"{row.field_name} verified but no sources"
