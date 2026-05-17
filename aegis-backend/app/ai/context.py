"""
app/ai/context.py
─────────────────
OrgProfileContext — the canonical context layer for all Aegis AI features.

Every AI feature reads from this compiled context instead of inferring from
the company name alone. Built from the Company Profile tables (Phase 1-3).
Falls back gracefully when no profile exists.
"""
from __future__ import annotations

import logging
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    OrgProfile, LineOfBusiness, OrgGeography, OrgIndustry,
    OrgProduct, CustomerSegment, ThirdPartyDependency, DataTechProfile,
    Organization,
)

logger = logging.getLogger(__name__)


class OrgProfileContext(BaseModel):
    """Compiled, serialisable context object injected into every Claude call."""
    legal_name: str
    description: str | None = None
    lines_of_business: list[str] = []
    geographies: list[dict] = []        # [{country, presence_type, regulations}]
    industries: list[str] = []
    products: list[dict] = []           # [{name, type, status, data_sensitivity}]
    customer_segments: list[dict] = []  # [{name, type, includes_minors, includes_healthcare, includes_financial}]
    third_parties: list[dict] = []      # [{name, category, tier, assessment_status}]
    data_flags: dict = {}               # {handles_personal_data, handles_payment_data, ...}
    tech_flags: dict = {}               # {uses_ai_ml, cloud_providers, ai_use_cases}


async def build_org_profile_context(
    org_id: UUID | str,
    db: AsyncSession,
) -> OrgProfileContext | None:
    """
    Load all Company Profile tables and compile an OrgProfileContext.
    Returns a minimal context from the organizations table if no Company
    Profile has been created yet.
    """
    if isinstance(org_id, str):
        org_id = UUID(org_id)

    identity = (await db.execute(
        select(OrgProfile).where(OrgProfile.org_id == org_id)
    )).scalar_one_or_none()

    if identity is None:
        org = (await db.execute(
            select(Organization).where(Organization.id == org_id)
        )).scalar_one_or_none()
        if org is None:
            return None
        return OrgProfileContext(legal_name=org.name)

    lobs = (await db.execute(
        select(LineOfBusiness)
        .where(LineOfBusiness.org_id == org_id, LineOfBusiness.status != "archived")
        .order_by(LineOfBusiness.is_primary.desc())
    )).scalars().all()

    geos = (await db.execute(
        select(OrgGeography).where(OrgGeography.org_id == org_id)
    )).scalars().all()

    industries = (await db.execute(
        select(OrgIndustry).where(OrgIndustry.org_id == org_id)
        .order_by(OrgIndustry.classification)
    )).scalars().all()

    products = (await db.execute(
        select(OrgProduct)
        .where(OrgProduct.org_id == org_id, OrgProduct.status != "sunset")
        .order_by(OrgProduct.name)
    )).scalars().all()

    segments = (await db.execute(
        select(CustomerSegment).where(CustomerSegment.org_id == org_id)
    )).scalars().all()

    third_parties = (await db.execute(
        select(ThirdPartyDependency)
        .where(ThirdPartyDependency.org_id == org_id)
        .order_by(ThirdPartyDependency.tier)
    )).scalars().all()

    data_tech = (await db.execute(
        select(DataTechProfile).where(DataTechProfile.org_id == org_id)
    )).scalar_one_or_none()

    return OrgProfileContext(
        legal_name=identity.legal_name,
        description=identity.description,
        lines_of_business=[lob.name for lob in lobs],
        geographies=[
            {
                "country": g.country,
                "presence_type": g.presence_type,
                "regulations": g.regulatory_flags or [],
            }
            for g in geos
        ],
        industries=[
            f"{ind.name} ({'primary' if ind.classification == 'primary' else 'secondary'})"
            for ind in industries
        ],
        products=[
            {
                "name": p.name,
                "type": p.product_type,
                "status": p.status,
                "data_sensitivity": p.data_sensitivity,
            }
            for p in products
        ],
        customer_segments=[
            {
                "name": s.name,
                "type": s.segment_type,
                "includes_minors": s.includes_minors,
                "includes_healthcare": s.includes_healthcare,
                "includes_financial": s.includes_financial,
                "estimated_size": s.estimated_size,
            }
            for s in segments
        ],
        third_parties=[
            {
                "name": tp.name,
                "category": tp.category,
                "tier": tp.tier,
                "assessment_status": tp.assessment_status,
            }
            for tp in third_parties
        ],
        data_flags={
            "handles_personal_data": data_tech.handles_personal_data if data_tech else False,
            "handles_sensitive_personal_data": data_tech.handles_sensitive_personal_data if data_tech else False,
            "handles_payment_data": data_tech.handles_payment_data if data_tech else False,
            "handles_health_data": data_tech.handles_health_data if data_tech else False,
            "handles_classified_data": data_tech.handles_classified_data if data_tech else False,
        },
        tech_flags={
            "uses_ai_ml": data_tech.uses_ai_ml if data_tech else False,
            "cloud_providers": data_tech.cloud_providers if data_tech else [],
            "ai_use_cases": data_tech.ai_use_cases if data_tech else [],
            "data_residency_requirements": data_tech.data_residency_requirements if data_tech else [],
        },
    )


def format_context_for_prompt(ctx: OrgProfileContext) -> str:
    """Serialise OrgProfileContext into a compact, prompt-friendly text block."""
    lines = [f"## Company: {ctx.legal_name}"]

    if ctx.description:
        lines.append(f"Description: {ctx.description}")

    if ctx.lines_of_business:
        lines.append(f"Lines of business: {', '.join(ctx.lines_of_business)}")

    if ctx.industries:
        lines.append(f"Industries: {', '.join(ctx.industries)}")

    if ctx.geographies:
        geo_parts = []
        for g in ctx.geographies:
            regs = ", ".join(g["regulations"]) if g["regulations"] else "none identified"
            geo_parts.append(f"{g['country']} ({g['presence_type']}, regulations: {regs})")
        lines.append(f"Operating geographies: {'; '.join(geo_parts)}")

    if ctx.products:
        high_sensitivity = [p["name"] for p in ctx.products if p["data_sensitivity"] in ("high", "critical")]
        lines.append(f"Products & services: {', '.join(p['name'] for p in ctx.products)}")
        if high_sensitivity:
            lines.append(f"High data-sensitivity products: {', '.join(high_sensitivity)}")

    if ctx.customer_segments:
        seg_parts = []
        for s in ctx.customer_segments:
            flags = []
            if s["includes_minors"]:
                flags.append("includes minors")
            if s["includes_healthcare"]:
                flags.append("healthcare data")
            if s["includes_financial"]:
                flags.append("financial services")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            seg_parts.append(f"{s['name']} ({s['type']}){flag_str}")
        lines.append(f"Customer segments: {'; '.join(seg_parts)}")

    if ctx.third_parties:
        tier1 = [tp["name"] for tp in ctx.third_parties if tp["tier"] == "tier_1"]
        if tier1:
            lines.append(f"Tier-1 (critical) vendors: {', '.join(tier1)}")
        lines.append(f"Total third-party dependencies: {len(ctx.third_parties)}")

    data_active = [k.replace("handles_", "").replace("_", " ") for k, v in ctx.data_flags.items() if v]
    if data_active:
        lines.append(f"Data handled: {', '.join(data_active)}")

    if ctx.tech_flags.get("uses_ai_ml"):
        ai_uses = ctx.tech_flags.get("ai_use_cases") or []
        if ai_uses:
            lines.append(f"AI/ML use cases: {', '.join(ai_uses[:5])}")
        else:
            lines.append("Uses AI/ML (use cases not specified)")

    clouds = ctx.tech_flags.get("cloud_providers") or []
    if clouds:
        lines.append(f"Cloud providers: {', '.join(clouds)}")

    return "\n".join(lines)
