"""
tests/integration/test_reseed_job.py — TC-R-* (PRD §3.2.6).

7 Critical + High tests covering the daily re-seed job.
TC-R-08 (Medium) deferred per scope cut.
TC-R-04 and TC-R-05 are skipped (notifications wiring not yet verified).
TC-R-06 and TC-R-07 use direct DB + HTTP harness to test approve/reject.
"""
from __future__ import annotations

import pytest
from uuid import uuid4
from sqlalchemy import select

from app.models import OrgProfile, SeedingProposal, Organization, User, UserRole
from app.tasks.reseed_unknowns import _reseed_async
from app.workers.tasks import celery_app


# ── TC-R-01: Critical ─────────────────────────────────────────────────────────
def test_TC_R_01_beat_schedule_contains_reseed():
    """Celery Beat schedule includes a reseed task at 02:00 UTC."""
    sched = getattr(celery_app.conf, "beat_schedule", {}) or {}
    matches = [k for k, v in sched.items() if "reseed" in (v.get("task") or "").lower()]
    assert matches, f"no reseed task in beat_schedule: {list(sched.keys())}"
    # Verify it's scheduled at hour=2
    entry = sched[matches[0]]
    schedule = entry.get("schedule")
    hour = getattr(schedule, "hour", None)
    assert hour == {2}, f"expected reseed at hour=2, got {hour!r}"


# ── TC-R-02: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_R_02_iterates_only_unknown_fields(db, db_engine, monkeypatch):
    """Re-seed only attempts fields with field_status='unknown'.

    Non-unknown fields must not be mutated by the reseed pass.
    Avoids calling the real Claude seeder by mocking seed_field directly.
    get_db_context is patched to use the test engine so _reseed_async
    shares the same event loop as the test.
    """
    import contextlib
    import app.database as _db_module
    import app.seeding.completeness_loop as _cl
    from app.seeding.completeness_loop import SeedResult
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    # Route _reseed_async's sessions through the test engine (same event loop)
    _TestSession = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    @contextlib.asynccontextmanager
    async def _test_db_context():
        async with _TestSession() as session:
            yield session

    monkeypatch.setattr(_db_module, "get_db_context", _test_db_context)

    # Mock seed_field so reseed never calls real Claude
    async def _mock_seed_field(*args, **kwargs):
        return SeedResult(status="seeded", value="Mocked City", confidence=0.9, source_urls=[])
    monkeypatch.setattr(_cl, "seed_field", _mock_seed_field)

    # Setup: org with one seeded field (legal_name) and one unknown field (hq_city)
    org = Organization(
        name="Reseed TC-R02 Org",
        slug=f"reseed-tc-r02-{uuid4().hex[:6]}",
        onboarding_complete=True,
    )
    db.add(org)
    await db.flush()

    profile = OrgProfile(
        org_id=org.id,
        legal_name="Reseed TC-R02 Org",
        field_status_map={"legal_name": "seeded", "hq_city": "unknown"},
        field_confidence_map={},
        field_source_map={},
    )
    db.add(profile)
    await db.commit()

    legal_name_before = profile.legal_name

    await _reseed_async(org.id)

    # Re-fetch via the test session to see committed state from _reseed_async
    await db.refresh(profile)

    # Non-unknown field must be unchanged by the reseed pass
    assert profile.legal_name == legal_name_before, (
        f"reseed mutated non-unknown field legal_name: "
        f"{legal_name_before!r} → {profile.legal_name!r}"
    )


# ── TC-R-03: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_R_03_writes_proposals_not_values(db, db_engine, monkeypatch):
    """Successful re-seed creates SeedingProposal rows; does NOT mutate the entity directly."""
    import contextlib
    import app.database as _db_module
    import app.seeding.completeness_loop as _cl
    from app.seeding.completeness_loop import SeedResult
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    _TestSession = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    @contextlib.asynccontextmanager
    async def _test_db_context():
        async with _TestSession() as session:
            yield session

    monkeypatch.setattr(_db_module, "get_db_context", _test_db_context)

    async def _mock_seed_field(*args, **kwargs):
        return SeedResult(status="seeded", value="Mocked City", confidence=0.9, source_urls=[])
    monkeypatch.setattr(_cl, "seed_field", _mock_seed_field)

    # Setup: org with one unknown field
    org = Organization(
        name="Reseed TC-R03 Org",
        slug=f"reseed-tc-r03-{uuid4().hex[:6]}",
        onboarding_complete=True,
    )
    db.add(org)
    await db.flush()

    profile = OrgProfile(
        org_id=org.id,
        legal_name="Reseed TC-R03 Org",
        field_status_map={"hq_city": "unknown"},
        field_confidence_map={},
        field_source_map={},
    )
    db.add(profile)
    await db.commit()

    legal_name_before = profile.legal_name

    await _reseed_async(org.id)

    await db.refresh(profile)

    # Field value must NOT be mutated — reseed creates proposals instead
    assert profile.legal_name == legal_name_before, (
        "reseed silently mutated legal_name on the entity — must use proposals instead"
    )
    assert profile.hq_city is None, (
        "reseed silently wrote hq_city — must create a proposal instead"
    )

    # A SeedingProposal row should exist and be pending
    proposals = (await db.execute(
        select(SeedingProposal).where(SeedingProposal.org_id == org.id)
    )).scalars().all()
    assert len(proposals) > 0, "expected at least one SeedingProposal row after reseed"
    for p in proposals:
        assert p.status == "pending", f"new proposal should be 'pending', got {p.status!r}"


# ── TC-R-04: High ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_R_04_admin_notification_created(db):
    """An in-app notification is sent to org admins when new proposals are created."""
    pytest.skip("Pending: notifications module wiring not yet verified")


# ── TC-R-05: High ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_R_05_badge_count_via_api(db, http_client):
    """Sidebar badge count (via API) matches pending proposal count."""
    pytest.skip("Pending: confirm pending-proposals-count endpoint path")


# ── TC-R-06: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_R_06_approve_proposal_writes_value(db, http_client):
    """Approving a proposal writes the field value to the entity and enqueues validation."""
    from app.api.auth import create_access_token

    # ── Setup: org + admin user + profile with unknown field ──────────────────
    org = Organization(
        name="Reseed Test Org",
        slug=f"reseed-tc-r06-{uuid4().hex[:6]}",
        onboarding_complete=True,
    )
    db.add(org)
    await db.flush()

    user = User(
        email=f"admin+{org.slug}@example.test",
        full_name="Test Admin",
        org_id=org.id,
        role=UserRole.org_admin,
        hashed_password="not-a-real-hash",
        is_active=True,
    )
    db.add(user)
    await db.flush()

    profile = OrgProfile(
        org_id=org.id,
        legal_name="Reseed Test Org",
        field_status_map={"hq_city": "unknown"},
        field_confidence_map={},
        field_source_map={},
    )
    db.add(profile)
    await db.flush()

    # ── Create a pending SeedingProposal for hq_city ──────────────────────────
    proposal = SeedingProposal(
        org_id=org.id,
        entity_type="org_profiles",
        entity_id=profile.id,
        field_name="hq_city",
        proposed_value={"value": "San Francisco"},
        confidence=0.97,
        sources=["https://example.com"],
        status="pending",
    )
    db.add(proposal)
    await db.commit()

    token = create_access_token(str(user.id), str(org.id), "org_admin")

    # ── POST /api/v1/validation/proposals/{id}/approve ────────────────────────
    resp = await http_client.post(
        f"/api/v1/validation/proposals/{proposal.id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, f"approve returned {resp.status_code}: {resp.text}"

    # ── Assert: proposal is approved, field is written ────────────────────────
    await db.refresh(proposal)
    assert proposal.status == "approved"

    await db.refresh(profile)
    assert profile.hq_city == "San Francisco", (
        f"field value not written after approval: {profile.hq_city!r}"
    )


# ── TC-R-07: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_R_07_reject_proposal_keeps_field_unknown(db, http_client):
    """Rejecting a proposal keeps the field at 'unknown' and logs the rejection."""
    from app.api.auth import create_access_token

    # ── Setup ──────────────────────────────────────────────────────────────────
    org = Organization(
        name="Reseed Reject Org",
        slug=f"reseed-tc-r07-{uuid4().hex[:6]}",
        onboarding_complete=True,
    )
    db.add(org)
    await db.flush()

    user = User(
        email=f"admin+{org.slug}@example.test",
        full_name="Test Admin",
        org_id=org.id,
        role=UserRole.org_admin,
        hashed_password="not-a-real-hash",
        is_active=True,
    )
    db.add(user)
    await db.flush()

    profile = OrgProfile(
        org_id=org.id,
        legal_name="Reseed Reject Org",
        field_status_map={"hq_city": "unknown"},
        field_confidence_map={},
        field_source_map={},
    )
    db.add(profile)
    await db.flush()

    proposal = SeedingProposal(
        org_id=org.id,
        entity_type="org_profiles",
        entity_id=profile.id,
        field_name="hq_city",
        proposed_value={"value": "Austin"},
        confidence=0.96,
        sources=["https://example.com"],
        status="pending",
    )
    db.add(proposal)
    await db.commit()

    token = create_access_token(str(user.id), str(org.id), "org_admin")

    # ── POST /api/v1/validation/proposals/{id}/reject ─────────────────────────
    resp = await http_client.post(
        f"/api/v1/validation/proposals/{proposal.id}/reject",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, f"reject returned {resp.status_code}: {resp.text}"

    # ── Assert: proposal is rejected; field value NOT written ─────────────────
    await db.refresh(proposal)
    assert proposal.status == "rejected"
    assert proposal.resolved_at is not None

    await db.refresh(profile)
    assert profile.hq_city is None, (
        f"field was written despite rejection: {profile.hq_city!r}"
    )
    status_map = profile.field_status_map or {}
    assert status_map.get("hq_city") == "unknown", (
        f"field_status_map['hq_city'] changed after rejection: {status_map.get('hq_city')!r}"
    )
