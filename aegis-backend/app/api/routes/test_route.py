"""
app/api/routes/test_route.py
────────────────────────────
Test-only endpoints. Mounted at /api/v1/test ONLY when AEGIS_ENABLE_TEST_ENDPOINTS=1.
Used by Playwright e2e tests. DO NOT MOUNT IN PRODUCTION.

Data is inserted directly (no Claude calls) so tests run without ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import create_access_token
from app.database import get_db
from app.models import (
    FieldValidation, LineOfBusiness, OrgGeography, OrgProfile,
    Organization, User, UserRole,
)

router = APIRouter(prefix="/test", tags=["test-only"])

FIXTURES_PATH = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "test_companies.json"

# Pre-seeded fixture values written directly to DB — no Claude call needed
FIXTURE_PROFILES: dict[str, dict] = {
    "uber": {
        "legal_name": "Uber Technologies, Inc.",
        "trading_name": "Uber",
        "hq_country": "US",
        "hq_city": "San Francisco",
        "stock_ticker": "UBER",
        "year_founded": 2009,
        "website": "https://www.uber.com",
        "employee_range": ">20000",
        "annual_revenue_range": ">$1B",
        "description": "Uber is a mobility platform operating in ride-sharing, food delivery, and freight.",
        "field_status_map": {
            "legal_name": "verified",
            "hq_country": "verified",
            "hq_city": "verified",
            "stock_ticker": "verified",
            "year_founded": "verified",
            "website": "verified",
            "employee_range": "seeded",
            "annual_revenue_range": "seeded",
            "description": "seeded",
        },
        "field_confidence_map": {
            "legal_name": 0.99,
            "hq_country": 0.99,
            "hq_city": 0.97,
            "stock_ticker": 0.99,
            "year_founded": 0.98,
            "website": 0.99,
        },
        "field_source_map": {
            "legal_name": ["https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=UBER"],
            "hq_country": ["https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=UBER"],
            "stock_ticker": ["https://finance.yahoo.com/quote/UBER"],
        },
    },
    "stripe": {
        "legal_name": "Stripe, Inc.",
        "trading_name": "Stripe",
        "hq_country": "US",
        "hq_city": "South San Francisco",
        "year_founded": 2010,
        "website": "https://stripe.com",
        "field_status_map": {"legal_name": "verified", "hq_country": "verified"},
        "field_confidence_map": {"legal_name": 0.98, "hq_country": 0.97},
        "field_source_map": {"legal_name": ["https://stripe.com/about"]},
    },
    "anthropic": {
        "legal_name": "Anthropic PBC",
        "hq_country": "US",
        "year_founded": 2021,
        "website": "https://www.anthropic.com",
        "field_status_map": {"legal_name": "verified", "hq_country": "verified"},
        "field_confidence_map": {"legal_name": 0.97},
        "field_source_map": {"legal_name": ["https://www.anthropic.com/about"]},
    },
    "maersk": {
        "legal_name": "A.P. Moller-Maersk A/S",
        "trading_name": "Maersk",
        "hq_country": "DK",
        "hq_city": "Copenhagen",
        "stock_ticker": "MAERSK-B",
        "year_founded": 1904,
        "website": "https://www.maersk.com",
        "field_status_map": {"legal_name": "verified", "hq_country": "verified", "stock_ticker": "verified"},
        "field_confidence_map": {"legal_name": 0.98, "hq_country": 0.99, "stock_ticker": 0.97},
        "field_source_map": {"legal_name": ["https://www.maersk.com/about"]},
    },
    "acme_shell_001": {
        "legal_name": "Acme Shell Holdings 001",
        "hq_country": None,
        "field_status_map": {"legal_name": "unknown"},
        "field_confidence_map": {},
        "field_source_map": {},
    },
}


class ProvisionRequest(BaseModel):
    fixture_company: str
    role: str = "admin"


class ProvisionResponse(BaseModel):
    email: str
    password: str
    role: str
    orgId: str
    accessToken: str


def _check_enabled():
    if os.getenv("AEGIS_ENABLE_TEST_ENDPOINTS") != "1":
        raise HTTPException(404, "Not found")


@router.post("/provision-tenant", response_model=ProvisionResponse)
async def provision_tenant(payload: ProvisionRequest, db: AsyncSession = Depends(get_db)):
    _check_enabled()

    fixtures = {}
    if FIXTURES_PATH.exists():
        fixtures = json.loads(FIXTURES_PATH.read_text())

    if payload.fixture_company not in (list(FIXTURE_PROFILES.keys()) + list(fixtures.keys())):
        raise HTTPException(400, f"Unknown fixture: {payload.fixture_company}")

    company_meta = fixtures.get(payload.fixture_company, {})
    company_name = company_meta.get("company_name", payload.fixture_company.replace("_", " ").title())
    domain = company_meta.get("domain", f"{payload.fixture_company}.example.com")

    # ── Create org ────────────────────────────────────────────────────────────
    org = Organization(
        name=company_name,
        slug=f"e2e-{uuid4().hex[:8]}",
        onboarding_complete=True,
        is_synthetic=True,
        fingerprint_data={"company_name": company_name, "domain": domain},
    )
    db.add(org)
    await db.flush()

    # ── Create user ───────────────────────────────────────────────────────────
    role_enum = UserRole.org_admin
    if payload.role == "auditor":
        role_enum = UserRole.auditor
    elif payload.role == "head_of_audit":
        role_enum = UserRole.head_of_audit

    user = User(
        email=f"{payload.role}+{org.slug}@example.test",
        full_name="E2E Test User",
        org_id=org.id,
        role=role_enum,
        hashed_password="$2b$12$abcdefghijklmnopqrstuvwxyz0123456789",
        is_active=True,
    )
    db.add(user)
    await db.flush()

    # ── Create pre-seeded profile data ────────────────────────────────────────
    profile_data = FIXTURE_PROFILES.get(payload.fixture_company, {
        "legal_name": company_name,
        "field_status_map": {"legal_name": "seeded"},
        "field_confidence_map": {},
        "field_source_map": {},
    })

    profile = OrgProfile(
        org_id=org.id,
        legal_name=profile_data.get("legal_name", company_name),
        trading_name=profile_data.get("trading_name"),
        hq_country=profile_data.get("hq_country"),
        hq_city=profile_data.get("hq_city"),
        stock_ticker=profile_data.get("stock_ticker"),
        year_founded=profile_data.get("year_founded"),
        website=profile_data.get("website"),
        employee_range=profile_data.get("employee_range"),
        annual_revenue_range=profile_data.get("annual_revenue_range"),
        description=profile_data.get("description"),
        field_status_map=profile_data.get("field_status_map", {}),
        field_confidence_map=profile_data.get("field_confidence_map", {}),
        field_source_map=profile_data.get("field_source_map", {}),
    )
    db.add(profile)
    await db.flush()

    # ── Create FieldValidation rows for verified fields ───────────────────────
    now = datetime.now(timezone.utc)
    for field_name, status in profile_data.get("field_status_map", {}).items():
        if status == "verified":
            sources = profile_data.get("field_source_map", {}).get(field_name, [])
            confidence = profile_data.get("field_confidence_map", {}).get(field_name, 0.95)
            db.add(FieldValidation(
                org_id=org.id,
                entity_type="org_profiles",
                entity_id=profile.id,
                field_name=field_name,
                validator="A",
                status="verified",
                seeded_value={field_name: getattr(profile, field_name, None)},
                sources=sources,
                confidence=confidence,
                notes="Pre-seeded fixture for E2E test",
                validated_at=now,
                duration_ms=0,
            ))

    # ── Create a Line of Business ─────────────────────────────────────────────
    lob = LineOfBusiness(
        org_id=org.id,
        name="Core Operations",
        status="active",
        is_primary=True,
        field_status_map={"name": "seeded"},
        field_confidence_map={},
        field_source_map={},
    )
    db.add(lob)

    # ── Create HQ geography ───────────────────────────────────────────────────
    if profile_data.get("hq_country"):
        geo = OrgGeography(
            org_id=org.id,
            country=profile_data["hq_country"],
            presence_type="headquarters",
            regulatory_flags=[],
            field_status_map={"country": "seeded"},
            field_confidence_map={},
            field_source_map={},
        )
        db.add(geo)

    await db.commit()

    token = create_access_token(
        str(user.id),
        str(org.id),
        str(user.role.value if hasattr(user.role, "value") else user.role),
    )

    return ProvisionResponse(
        email=user.email,
        password="e2e-only",
        role=str(user.role.value if hasattr(user.role, "value") else user.role),
        orgId=str(org.id),
        accessToken=token,
    )


@router.delete("/teardown-tenant/{org_id}")
async def teardown_tenant(org_id: UUID, db: AsyncSession = Depends(get_db)):
    _check_enabled()
    from sqlalchemy import delete
    org = await db.get(Organization, org_id)
    if org and str(getattr(org, "slug", "")).startswith("e2e-"):
        await db.execute(delete(Organization).where(Organization.id == org_id))
        await db.commit()
    return {"deleted": str(org_id)}
