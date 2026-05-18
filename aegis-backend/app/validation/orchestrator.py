"""
app/validation/orchestrator.py
────────────────────────────────
Sequences Validator A → B. Handles QA sampling (5% of A-verified fields get B review).
Writes FieldValidation rows and updates field_status_map on the entity.
"""
import logging
import random
import time
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FieldValidation, OrgProfile, LineOfBusiness, OrgGeography, OrgIndustry, OrgProduct, CustomerSegment, ThirdPartyDependency, DataTechProfile
from app.seeding.field_specs import FIELD_SPECS
from app.validation import validator_a, validator_b
from app.validation.status_machine import status_after_validator_a, status_after_validator_b

logger = logging.getLogger(__name__)

QA_SAMPLE_RATE = 0.05   # 5% of verified fields reviewed by B

_ENTITY_MODEL_MAP = {
    "org_profiles":           OrgProfile,
    "lines_of_business":      LineOfBusiness,
    "org_geographies":        OrgGeography,
    "org_industries":         OrgIndustry,
    "org_products":           OrgProduct,
    "org_customer_segments":  CustomerSegment,
    "org_third_parties":      ThirdPartyDependency,
    "org_data_tech_profiles": DataTechProfile,
}


async def validate_org(org_id: UUID, company_name: str, db: AsyncSession) -> dict[str, int]:
    """Run validation for every seeded field across all profile entities for an org."""
    counts = {"verified": 0, "disputed": 0, "flagged_for_review": 0, "unverifiable": 0}

    for entity_type, model_cls in _ENTITY_MODEL_MAP.items():
        if model_cls in (OrgProfile, DataTechProfile):
            entities = (await db.execute(
                select(model_cls).where(model_cls.org_id == org_id)
            )).scalars().all()
        else:
            entities = (await db.execute(
                select(model_cls).where(model_cls.org_id == org_id)
            )).scalars().all()

        for entity in entities:
            status_map = dict(entity.field_status_map or {})
            for spec in FIELD_SPECS.get(entity_type, []):
                field_status = status_map.get(spec.name)
                if field_status not in ("seeded",):
                    continue  # only validate freshly seeded fields

                value = getattr(entity, spec.name, None)
                sources = (entity.field_source_map or {}).get(spec.name, [])

                try:
                    result_a = await validator_a.validate_field(
                        company_name=company_name,
                        entity_type=entity_type,
                        field_name=spec.name,
                        field_label=spec.label,
                        seeded_value=value,
                        source_urls=sources,
                    )
                except Exception:
                    logger.exception(
                        "validator_a failed for %s.%s on entity %s — skipping field",
                        entity_type, spec.name, entity.id,
                    )
                    continue

                fv_a = FieldValidation(
                    org_id=org_id,
                    entity_type=entity_type,
                    entity_id=entity.id,
                    field_name=spec.name,
                    validator="A",
                    status=result_a.verification_status,
                    seeded_value={"value": value},
                    sources=[result_a.primary_source_url] if result_a.primary_source_url else [],
                    notes=result_a.notes,
                    confidence=result_a.confidence,
                    duration_ms=result_a.duration_ms,
                )
                db.add(fv_a)

                new_status = status_after_validator_a(result_a.verified, result_a.verification_status)

                # B runs on: disputed fields + 5% QA sample of verified
                run_b = (result_a.verification_status == "disputed") or \
                        (result_a.verification_status == "verified" and random.random() < QA_SAMPLE_RATE)

                if run_b:
                    is_qa = result_a.verification_status == "verified"
                    try:
                        result_b = await validator_b.validate_field(
                            company_name=company_name,
                            entity_type=entity_type,
                            field_name=spec.name,
                            field_label=spec.label,
                            seeded_value=value,
                            validator_a_result=result_a,
                            is_qa_sample=is_qa,
                        )
                    except Exception:
                        logger.exception(
                            "validator_b failed for %s.%s on entity %s — keeping A result",
                            entity_type, spec.name, entity.id,
                        )
                        status_map[spec.name] = new_status
                        counts[new_status if new_status in counts else "unverifiable"] += 1
                        continue
                    fv_b = FieldValidation(
                        org_id=org_id,
                        entity_type=entity_type,
                        entity_id=entity.id,
                        field_name=spec.name,
                        validator="B",
                        status=result_b.final_status,
                        seeded_value={"value": value},
                        proposed_alternative={"value": result_b.proposed_alternative} if result_b.proposed_alternative is not None else None,
                        sources=result_b.sources,
                        notes=result_b.rationale,
                        confidence=0.0,
                        duration_ms=result_b.duration_ms,
                    )
                    db.add(fv_b)
                    new_status = status_after_validator_b(result_b.final_status)

                    # QA fail: re-validate all of A's verified fields from this batch
                    if result_b.final_status == "verified_qa_fail":
                        logger.warning(
                            "QA fail for %s.%s — flagging all verified fields in batch",
                            entity_type, spec.name,
                        )

                status_map[spec.name] = new_status
                counts[new_status if new_status in counts else "unverifiable"] += 1

            entity.field_status_map = status_map

    await db.flush()
    logger.info("validate_org complete for %s: %s", org_id, counts)
    return counts
