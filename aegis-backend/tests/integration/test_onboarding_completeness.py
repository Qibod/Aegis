"""
tests/integration/test_onboarding_completeness.py — TC-O-* (PRD §3.2.2).

21 Critical + High tests covering completeness after onboarding.
Drops 3 Medium (TC-O-05, 21, 23) per scope cut.
"""
from __future__ import annotations

import re
import time

import pytest
from sqlalchemy import select

from app.models import (
    OrgProfile, LineOfBusiness, OrgGeography, OrgIndustry, OrgProduct,
    CustomerSegment, ThirdPartyDependency, DataTechProfile, Risk, Control,
    CanvasNode, CanvasEdge,
)
from tests.integration._helpers import onboard_test_org, get_seeding_attempts


REQUIRED_ORG_IDENTITY_FIELDS = [
    "legal_name", "trading_name", "year_founded", "employee_range",
    "annual_revenue_range", "hq_country", "hq_city", "website",
    "description", "logo_url",
]

LOB_VALID_STATUSES = {"active", "inactive", "sunset", "planned"}

SENTINEL_VALUES = {"unknown", "n/a", "tbd", "n/a"}


def _norm(s: str | None) -> str:
    return (s or "").strip().casefold()


# ── TC-O-01: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_01_org_identity_completeness(db, mock_claude, test_companies):
    """All required Org Identity fields are non-null OR explicitly 'unknown' with logged reason."""
    org = await onboard_test_org(db, "uber", test_companies)
    profile = (await db.execute(select(OrgProfile).where(OrgProfile.org_id == org.id))).scalar_one()
    status_map = profile.field_status_map or {}
    for field in REQUIRED_ORG_IDENTITY_FIELDS:
        value = getattr(profile, field, None)
        status = status_map.get(field)
        if value is None:
            assert status == "unknown", f"{field}: value=None but status={status!r}"
            assert len(await get_seeding_attempts(db, org.id, field)) >= 1
        else:
            assert status in (
                "seeded", "verified", "verified_after_dispute", "user_edited", "flagged_for_review"
            ), f"{field}: invalid status {status!r}"


# ── TC-O-02: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_02_legal_name_matches_fixture(db, mock_claude, test_companies):
    """legal_name matches canonical fixture value (case-insensitive, whitespace-normalised)."""
    org = await onboard_test_org(db, "uber", test_companies)
    profile = (await db.execute(select(OrgProfile).where(OrgProfile.org_id == org.id))).scalar_one()
    expected = test_companies["uber"]["expected"]["legal_name"]
    assert _norm(profile.legal_name) == _norm(expected)


# ── TC-O-03: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_03_hq_country_iso_code(db, mock_claude, test_companies):
    """hq_country is a valid ISO 3166-1 alpha-2 code."""
    import pycountry
    org = await onboard_test_org(db, "uber", test_companies)
    profile = (await db.execute(select(OrgProfile).where(OrgProfile.org_id == org.id))).scalar_one()
    if profile.hq_country is not None:
        assert pycountry.countries.get(alpha_2=profile.hq_country.upper()) is not None


# ── TC-O-04: High ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
@pytest.mark.xfail(reason="field not found: is_public_company — not a column on OrgProfile; stock_ticker presence inferred from stock_ticker being non-null")
async def test_TC_O_04_public_company_has_valid_stock_ticker(db, mock_claude, test_companies):
    """is_public_company=True → stock_ticker non-null AND matches ^[A-Z.\\-]{1,8}$."""
    org = await onboard_test_org(db, "uber", test_companies)
    profile = (await db.execute(select(OrgProfile).where(OrgProfile.org_id == org.id))).scalar_one()
    # is_public_company does not exist as a column; this test is xfail pending the field being added
    is_public = getattr(profile, "is_public_company", None)
    if is_public:
        assert profile.stock_ticker is not None, "is_public_company=True but stock_ticker is null"
        assert re.match(r"^[A-Z.\-]{1,8}$", profile.stock_ticker), \
            f"stock_ticker {profile.stock_ticker!r} does not match ^[A-Z.\\-]{{1,8}}$"


# ── TC-O-06: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_06_lines_of_business_seeded(db, mock_claude, test_companies):
    """≥ 1 LineOfBusiness row; exactly one has is_primary=True."""
    org = await onboard_test_org(db, "uber", test_companies)
    lobs = (await db.execute(
        select(LineOfBusiness).where(LineOfBusiness.org_id == org.id)
    )).scalars().all()
    assert len(lobs) >= 1, f"expected ≥1 LineOfBusiness rows, got {len(lobs)}"
    primary_lobs = [l for l in lobs if l.is_primary is True]
    assert len(primary_lobs) == 1, \
        f"expected exactly 1 primary LOB, got {len(primary_lobs)}: {[l.name for l in primary_lobs]}"


# ── TC-O-07: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_07_lob_status_valid(db, mock_claude, test_companies):
    """Every LineOfBusiness has status in {active, inactive, sunset, planned}."""
    org = await onboard_test_org(db, "uber", test_companies)
    lobs = (await db.execute(
        select(LineOfBusiness).where(LineOfBusiness.org_id == org.id)
    )).scalars().all()
    for lob in lobs:
        assert lob.status in LOB_VALID_STATUSES, \
            f"LOB {lob.name!r}: invalid status {lob.status!r}"


# ── TC-O-08: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_08_hq_geography_row_exists(db, mock_claude, test_companies):
    """≥ 1 OrgGeography row; HQ country row has presence_type containing 'headquarters'."""
    org = await onboard_test_org(db, "uber", test_companies)
    profile = (await db.execute(select(OrgProfile).where(OrgProfile.org_id == org.id))).scalar_one()
    geos = (await db.execute(
        select(OrgGeography).where(OrgGeography.org_id == org.id)
    )).scalars().all()
    assert len(geos) >= 1, f"expected ≥1 OrgGeography rows, got {len(geos)}"
    if profile.hq_country:
        hq_geos = [g for g in geos if g.country == profile.hq_country]
        assert any("headquarters" in (g.presence_type or "").lower() for g in hq_geos), \
            f"No headquarters presence_type for HQ country {profile.hq_country!r}; " \
            f"found: {[g.presence_type for g in hq_geos]}"


# ── TC-O-09: High ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_09_geography_regulatory_flags_non_null(db, mock_claude, test_companies):
    """Every OrgGeography has regulatory_flags as a non-null list (may be empty)."""
    org = await onboard_test_org(db, "uber", test_companies)
    geos = (await db.execute(
        select(OrgGeography).where(OrgGeography.org_id == org.id)
    )).scalars().all()
    for geo in geos:
        assert geo.regulatory_flags is not None, \
            f"Geography {geo.country!r}: regulatory_flags is None"
        assert isinstance(geo.regulatory_flags, list), \
            f"Geography {geo.country!r}: regulatory_flags is {type(geo.regulatory_flags)}, expected list"


# ── TC-O-10: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_10_primary_industry_exists(db, mock_claude, test_companies):
    """≥ 1 OrgIndustry with classification='primary'."""
    org = await onboard_test_org(db, "uber", test_companies)
    industries = (await db.execute(
        select(OrgIndustry).where(OrgIndustry.org_id == org.id)
    )).scalars().all()
    assert len(industries) >= 1, f"expected ≥1 OrgIndustry rows, got {len(industries)}"
    primary = [i for i in industries if i.classification == "primary"]
    assert len(primary) >= 1, \
        f"no OrgIndustry with classification='primary'; found: {[i.classification for i in industries]}"


# ── TC-O-11: High ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_11_industry_code_format(db, mock_claude, test_companies):
    """Every OrgIndustry code matches ^\\d{2,8}$."""
    org = await onboard_test_org(db, "uber", test_companies)
    industries = (await db.execute(
        select(OrgIndustry).where(OrgIndustry.org_id == org.id)
    )).scalars().all()
    for industry in industries:
        assert re.match(r"^\d{2,8}$", industry.code or ""), \
            f"OrgIndustry {industry.name!r}: code {industry.code!r} does not match ^\\d{{2,8}}$"


# ── TC-O-12: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_12_products_seeded_with_required_fields(db, mock_claude, test_companies):
    """≥ 1 OrgProduct with product_type, status, data_sensitivity all non-null."""
    org = await onboard_test_org(db, "uber", test_companies)
    products = (await db.execute(
        select(OrgProduct).where(OrgProduct.org_id == org.id)
    )).scalars().all()
    assert len(products) >= 1, f"expected ≥1 OrgProduct rows, got {len(products)}"
    for product in products:
        assert product.product_type is not None, f"Product {product.name!r}: product_type is None"
        assert product.status is not None, f"Product {product.name!r}: status is None"
        assert product.data_sensitivity is not None, f"Product {product.name!r}: data_sensitivity is None"


# ── TC-O-13: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_13_customer_segments_boolean_flags_non_null(db, mock_claude, test_companies):
    """≥ 1 CustomerSegment with all three is_* boolean flags non-null."""
    org = await onboard_test_org(db, "uber", test_companies)
    segments = (await db.execute(
        select(CustomerSegment).where(CustomerSegment.org_id == org.id)
    )).scalars().all()
    assert len(segments) >= 1, f"expected ≥1 CustomerSegment rows, got {len(segments)}"
    for seg in segments:
        assert seg.includes_minors is not None, \
            f"CustomerSegment {seg.name!r}: includes_minors is None"
        assert seg.includes_healthcare is not None, \
            f"CustomerSegment {seg.name!r}: includes_healthcare is None"
        assert seg.includes_financial is not None, \
            f"CustomerSegment {seg.name!r}: includes_financial is None"


# ── TC-O-14: High ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_14_cloud_providers_subset_of_third_parties(db, mock_claude, test_companies):
    """Every DataTechProfile.cloud_providers entry also exists as a ThirdPartyDependency (set subset check)."""
    org = await onboard_test_org(db, "uber", test_companies)
    dtp = (await db.execute(
        select(DataTechProfile).where(DataTechProfile.org_id == org.id)
    )).scalar_one_or_none()
    if dtp is None:
        pytest.skip("No DataTechProfile row — skipping subset check")

    cloud_providers = [p.casefold() for p in (dtp.cloud_providers or [])]
    if not cloud_providers:
        return  # nothing to check

    third_parties = (await db.execute(
        select(ThirdPartyDependency).where(ThirdPartyDependency.org_id == org.id)
    )).scalars().all()
    tp_names = {tp.name.casefold() for tp in third_parties}

    missing = [cp for cp in cloud_providers if cp not in tp_names]
    assert not missing, \
        f"Cloud providers not represented as ThirdPartyDependency: {missing}"


# ── TC-O-15: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_15_data_tech_profile_boolean_flags_non_null(db, mock_claude, test_companies):
    """DataTechProfile has all handles_*/uses_ai_ml boolean flags non-null."""
    org = await onboard_test_org(db, "uber", test_companies)
    dtp = (await db.execute(
        select(DataTechProfile).where(DataTechProfile.org_id == org.id)
    )).scalar_one_or_none()
    assert dtp is not None, "DataTechProfile row not created during onboarding"

    boolean_flags = [
        "uses_ai_ml",
        "handles_personal_data",
        "handles_sensitive_personal_data",
        "handles_payment_data",
        "handles_health_data",
        "handles_classified_data",
    ]
    for flag in boolean_flags:
        value = getattr(dtp, flag, None)
        assert value is not None, f"DataTechProfile.{flag} is None"


# ── TC-O-16: High ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_16_ai_ml_implies_cloud_providers(db, mock_claude, test_companies):
    """If uses_ai_ml=True, cloud_providers is non-empty."""
    org = await onboard_test_org(db, "uber", test_companies)
    dtp = (await db.execute(
        select(DataTechProfile).where(DataTechProfile.org_id == org.id)
    )).scalar_one_or_none()
    if dtp is None:
        pytest.skip("No DataTechProfile row")
    if dtp.uses_ai_ml:
        assert dtp.cloud_providers and len(dtp.cloud_providers) > 0, \
            "uses_ai_ml=True but cloud_providers is empty"


# ── TC-O-17: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_17_risks_seeded_with_tags(db, mock_claude, test_companies):
    """≥ 5 Risk rows; each has at least one lob_id or geography_ids entry."""
    org = await onboard_test_org(db, "uber", test_companies)
    risks = (await db.execute(
        select(Risk).where(Risk.org_id == org.id)
    )).scalars().all()
    assert len(risks) >= 5, f"expected ≥5 Risk rows, got {len(risks)}"
    for risk in risks:
        has_lob = risk.lob_id is not None
        has_geo = bool(risk.geography_ids)
        assert has_lob or has_geo, \
            f"Risk {risk.name!r}: no lob_id and no geography_ids"


# ── TC-O-18: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_18_controls_linked_to_risks(db, mock_claude, test_companies):
    """≥ 3 Control rows; each linked to ≥ 1 Risk via CanvasEdge (mitigates)."""
    org = await onboard_test_org(db, "uber", test_companies)
    controls = (await db.execute(
        select(Control).where(Control.org_id == org.id)
    )).scalars().all()
    assert len(controls) >= 3, f"expected ≥3 Control rows, got {len(controls)}"

    # Build set of control canvas node IDs
    control_nodes = (await db.execute(
        select(CanvasNode).where(
            CanvasNode.org_id == org.id,
            CanvasNode.control_id.isnot(None),
        )
    )).scalars().all()
    control_node_ids = {cn.id for cn in control_nodes}

    # For each control node, check there is at least one outgoing edge to a risk node
    risk_nodes = (await db.execute(
        select(CanvasNode).where(
            CanvasNode.org_id == org.id,
            CanvasNode.risk_id.isnot(None),
        )
    )).scalars().all()
    risk_node_ids = {rn.id for rn in risk_nodes}

    edges = (await db.execute(
        select(CanvasEdge).where(CanvasEdge.org_id == org.id)
    )).scalars().all()

    # Map: control_node_id → set of to_node_ids
    control_to_risk: dict = {}
    for edge in edges:
        if edge.from_node_id in control_node_ids and edge.to_node_id in risk_node_ids:
            control_to_risk.setdefault(edge.from_node_id, set()).add(edge.to_node_id)

    unlinked = [cn.control_id for cn in control_nodes if cn.id not in control_to_risk]
    assert not unlinked, \
        f"{len(unlinked)} Control(s) have no CanvasEdge to any Risk: {unlinked}"


# ── TC-O-19: High ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
@pytest.mark.xfail(reason="risk-radar signal scope wiring not yet verified", strict=False)
async def test_TC_O_19_risk_radar_signal_scope_wiring(db, mock_claude, test_companies):
    """Placeholder: risk-radar signal scope wiring is verified post-onboarding."""
    org = await onboard_test_org(db, "uber", test_companies)
    from app.models import Signal
    signals = (await db.execute(
        select(Signal).where(Signal.org_id == org.id)
    )).scalars().all()
    assert len(signals) >= 1, "no Signal rows created during onboarding"


# ── TC-O-20: Critical ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_20_geography_regulatory_flags_populated(db, mock_claude, test_companies):
    """≥ 1 geography row has a non-empty regulatory_flags list."""
    org = await onboard_test_org(db, "uber", test_companies)
    geos = (await db.execute(
        select(OrgGeography).where(OrgGeography.org_id == org.id)
    )).scalars().all()
    assert any(
        isinstance(g.regulatory_flags, list) and len(g.regulatory_flags) > 0
        for g in geos
    ), "No geography row has any regulatory_flags entries"


# ── TC-O-22: High ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_TC_O_22_no_sentinel_string_values(db, mock_claude, test_companies):
    """No string field value is literally 'unknown'/'N/A'/'TBD' — null+status='unknown' only."""
    org = await onboard_test_org(db, "uber", test_companies)
    profile = (await db.execute(select(OrgProfile).where(OrgProfile.org_id == org.id))).scalar_one()

    string_fields = [
        "legal_name", "trading_name", "employee_range", "annual_revenue_range",
        "hq_country", "hq_city", "stock_ticker", "website", "description", "logo_url",
    ]
    for field in string_fields:
        value = getattr(profile, field, None)
        if value is not None:
            normalised = value.strip().casefold()
            assert normalised not in SENTINEL_VALUES, \
                f"OrgProfile.{field} contains sentinel string {value!r}"


# ── TC-O-24: High ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
@pytest.mark.slow
async def test_TC_O_24_onboarding_completes_within_180s(db, mock_claude, test_companies):
    """Full onboarding (mocked Claude) completes in under 180 seconds."""
    start = time.perf_counter()
    await onboard_test_org(db, "uber", test_companies)
    elapsed = time.perf_counter() - start
    assert elapsed < 180, f"onboarding took {elapsed:.1f}s, expected < 180s"
