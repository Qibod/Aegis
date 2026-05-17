"""
app/seeding/completeness_loop.py
──────────────────────────────────
Completeness loop — iterates strategies per field until MIN_CONFIDENCE reached.

Entry points:
  seed_field(field_spec, company_name, context, db, org_id, entity_type, entity_id)
  seed_org(org_id, company_name, db)  — seeds all required fields for an org
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.seeding import seeder_agent
from app.seeding.confidence import MIN_CONFIDENCE, is_confident
from app.seeding.field_specs import FieldSpec, FIELD_SPECS
from app.models import (
    SeedingAttempt, OrgProfile, LineOfBusiness, OrgGeography,
    OrgIndustry, OrgProduct, CustomerSegment, ThirdPartyDependency, DataTechProfile,
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 4
STRATEGIES = ["web_search", "site_scrape", "filings", "llm_inference"]


@dataclass
class SeedResult:
    value: Any
    status: str                          # "seeded" | "unknown"
    source_urls: list[str] = field(default_factory=list)
    confidence: float = 0.0
    strategy_used: str = ""
    reason: str = ""


async def seed_field(
    spec: FieldSpec,
    company_name: str,
    context: dict,
    db: AsyncSession,
    org_id: UUID,
    entity_type: str,
    entity_id: UUID | None,
) -> SeedResult:
    """Run up to MAX_ATTEMPTS strategies for a single field. Logs every attempt."""
    strategies = [s for s in STRATEGIES if s != "filings" or spec.filings_applicable]

    for attempt_number, strategy in enumerate(strategies[:MAX_ATTEMPTS], start=1):
        t0 = time.monotonic()
        result = await seeder_agent.run(
            company_name=company_name,
            field_name=spec.name,
            field_label=spec.label,
            strategy=strategy,
            context=context,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        attempt = SeedingAttempt(
            org_id=org_id,
            entity_type=entity_type,
            entity_id=entity_id,
            field_name=spec.name,
            attempt_number=attempt_number,
            strategy=strategy,
            query=f"{company_name} {spec.label}",
            result_value={"value": result.value} if result.value is not None else None,
            confidence=result.confidence,
            source_urls=result.source_urls,
            succeeded=is_confident(result.confidence),
            failure_reason=None if is_confident(result.confidence) else "confidence below threshold",
            duration_ms=elapsed_ms,
        )
        db.add(attempt)
        await db.flush()

        if is_confident(result.confidence):
            logger.info(
                "seeded %s.%s via %s confidence=%.2f",
                entity_type, spec.name, strategy, result.confidence,
            )
            return SeedResult(
                value=result.value,
                status="seeded",
                source_urls=result.source_urls,
                confidence=result.confidence,
                strategy_used=strategy,
            )

    logger.info(
        "unknown %s.%s — all %d strategies below %.2f",
        entity_type, spec.name, MAX_ATTEMPTS, MIN_CONFIDENCE,
    )
    return SeedResult(
        value=None,
        status="unknown",
        reason=f"All {MAX_ATTEMPTS} strategies returned confidence < {MIN_CONFIDENCE}",
    )


async def seed_org(org_id: UUID, company_name: str, db: AsyncSession) -> dict[str, int]:
    """Seed all required fields for every profile entity belonging to an org."""
    profile = (await db.execute(
        select(OrgProfile).where(OrgProfile.org_id == org_id)
    )).scalar_one_or_none()
    if not profile:
        logger.warning("seed_org: no OrgProfile found for org %s", org_id)
        return {"seeded": 0, "unknown": 0}

    context = _build_context(profile)
    counts = {"seeded": 0, "unknown": 0}

    # Seed OrgProfile fields
    for spec in FIELD_SPECS.get("org_profiles", []):
        current_val = getattr(profile, spec.name, None)
        if current_val is not None and current_val != "" and current_val != [] and current_val != {}:
            continue  # already populated

        result = await seed_field(spec, company_name, context, db, org_id, "org_profiles", profile.id)
        _apply_result(profile, spec.name, result)
        counts[result.status] += 1

    await db.flush()

    # Seed child entities — only if at least one exists (they're created by fingerprint)
    await _seed_entity_list(
        db, org_id, company_name, context,
        select(LineOfBusiness).where(LineOfBusiness.org_id == org_id),
        "lines_of_business", counts,
    )
    await _seed_entity_list(
        db, org_id, company_name, context,
        select(OrgGeography).where(OrgGeography.org_id == org_id),
        "org_geographies", counts,
    )
    await _seed_entity_list(
        db, org_id, company_name, context,
        select(OrgIndustry).where(OrgIndustry.org_id == org_id),
        "org_industries", counts,
    )
    await _seed_entity_list(
        db, org_id, company_name, context,
        select(OrgProduct).where(OrgProduct.org_id == org_id),
        "org_products", counts,
    )
    await _seed_entity_list(
        db, org_id, company_name, context,
        select(CustomerSegment).where(CustomerSegment.org_id == org_id),
        "org_customer_segments", counts,
    )
    await _seed_entity_list(
        db, org_id, company_name, context,
        select(ThirdPartyDependency).where(ThirdPartyDependency.org_id == org_id),
        "org_third_parties", counts,
    )

    data_tech = (await db.execute(
        select(DataTechProfile).where(DataTechProfile.org_id == org_id)
    )).scalar_one_or_none()
    if data_tech:
        for spec in FIELD_SPECS.get("org_data_tech_profiles", []):
            result = await seed_field(spec, company_name, context, db, org_id, "org_data_tech_profiles", data_tech.id)
            _apply_result(data_tech, spec.name, result)
            counts[result.status] += 1
        await db.flush()

    logger.info("seed_org complete for %s: %s", org_id, counts)
    return counts


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_context(profile: OrgProfile) -> dict:
    return {
        "legal_name":    profile.legal_name,
        "website":       profile.website,
        "hq_country":    profile.hq_country,
        "stock_ticker":  profile.stock_ticker,
        "description":   profile.description,
        "is_public_company": bool(profile.stock_ticker),
    }


def _apply_result(entity: Any, field_name: str, result: SeedResult) -> None:
    if result.status == "seeded":
        setattr(entity, field_name, result.value)
    status_map = entity.field_status_map or {}
    confidence_map = entity.field_confidence_map or {}
    source_map = entity.field_source_map or {}
    status_map[field_name] = result.status
    confidence_map[field_name] = result.confidence
    source_map[field_name] = result.source_urls
    entity.field_status_map = status_map
    entity.field_confidence_map = confidence_map
    entity.field_source_map = source_map


async def _seed_entity_list(
    db: AsyncSession,
    org_id: UUID,
    company_name: str,
    context: dict,
    query,
    entity_type: str,
    counts: dict,
) -> None:
    entities = (await db.execute(query)).scalars().all()
    for entity in entities:
        for spec in FIELD_SPECS.get(entity_type, []):
            current_val = getattr(entity, spec.name, None)
            if current_val is not None and current_val != "" and current_val != [] and current_val != {}:
                continue
            result = await seed_field(spec, company_name, context, db, org_id, entity_type, entity.id)
            _apply_result(entity, spec.name, result)
            counts[result.status] += 1
    await db.flush()
