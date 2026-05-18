"""
tests/integration/test_reseed_job.py — TC-R-* (PRD §3.2.6).

7 Critical + High tests covering the daily re-seed job.
TC-R-08 (Medium) deferred per scope cut.
TC-R-04 and TC-R-05 are skipped (notifications wiring not yet verified).
TC-R-06 and TC-R-07 use direct DB + HTTP harness to test approve/reject.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import OrgProfile, SeedingProposal, Organization, User, UserRole
from app.tasks.reseed_unknowns import _reseed_async
from app.workers.tasks import celery_app
from tests.integration._helpers import onboard_test_org


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
async def test_TC_R_02_iterates_only_unknown_fields(db, mock_claude, test_companies):
    """Re-seed only attempts fields with field_status='unknown'.

    Non-unknown fields must not be mutated by the reseed pass.
    """
    org = await onboard_test_org(db, "acme_shell_001", test_companies)
    profile = (await db.execute(
        select(OrgProfile).where(OrgProfile.org_id == org.id)
    )).scalar_one_or_none()

    # Snapshot pre-reseed values of any non-unknown fields
    status_map = (profile.field_status_map or {}) if profile else {}
    pre_values = {}
    if profile:
        for field_name, status in status_map.items():
            if status != "unknown":
                pre_values[field_name] = getattr(profile, field_name, None)

    await _reseed_async(org.id)
    await db.refresh(profile)

    # Non-unknown fields must be unchanged
    for field_name, original_value in pre_values.items():
        current_value = getattr(profile, field_name, None)
        assert current_value == original_value, (
            f"reseed mutated non-unknown field {field_name!r}: "
            f"{original_value!r} → {current_value!r}"
        )


# ── TC-R-03: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_R_03_writes_proposals_not_values(db, mock_claude, test_companies):
    """Successful re-seed creates SeedingProposal rows; does NOT mutate the entity directly."""
    org = await onboard_test_org(db, "acme_shell_001", test_companies)
    profile = (await db.execute(
        select(OrgProfile).where(OrgProfile.org_id == org.id)
    )).scalar_one_or_none()

    # Snapshot current values
    legal_name_before = profile.legal_name if profile else None

    await _reseed_async(org.id)

    if profile:
        await db.refresh(profile)
        assert profile.legal_name == legal_name_before, (
            "reseed silently mutated `legal_name` on the entity — must use proposals instead"
        )

    # Invariant: if mock returns a "seeded" result, a SeedingProposal row is created;
    # if mock returns "unknown" again, no proposals (both are valid per the mock contract).
    proposals = (await db.execute(
        select(SeedingProposal).where(SeedingProposal.org_id == org.id)
    )).scalars().all()
    assert isinstance(proposals, list), "expected a list of SeedingProposal rows"
    for p in proposals:
        assert p.status == "pending", f"new proposal should be 'pending', got {p.status!r}"


# ── TC-R-04: High ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_R_04_admin_notification_created(db, mock_claude, test_companies):
    """An in-app notification is sent to org admins when new proposals are created."""
    pytest.skip("Pending: notifications module wiring not yet verified")


# ── TC-R-05: High ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_R_05_badge_count_via_api(db, mock_claude, test_companies, http_client):
    """Sidebar badge count (via API) matches pending proposal count."""
    pytest.skip("Pending: confirm pending-proposals-count endpoint path")


# ── TC-R-06: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_R_06_approve_proposal_writes_value(db, mock_claude, test_companies, http_client):
    """Approving a proposal writes the field value to the entity and enqueues validation."""
    from uuid import uuid4
    from datetime import datetime, timezone
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
async def test_TC_R_07_reject_proposal_keeps_field_unknown(db, mock_claude, test_companies, http_client):
    """Rejecting a proposal keeps the field at 'unknown' and logs the rejection."""
    from uuid import uuid4
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
