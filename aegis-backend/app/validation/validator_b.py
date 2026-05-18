"""
app/validation/validator_b.py
───────────────────────────────
Validator B — "Adversarial Reviewer".
Second-pass review of disputed fields + 5% QA sample of verified fields.
"""
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.validation.sources.allowlist_b import SEARCH_GUIDANCE_B
from app.validation.validator_a import ValidatorAResult

logger = logging.getLogger(__name__)
settings = get_settings()
claude = AsyncAnthropic(api_key=settings.anthropic_api_key)


def _slugify(name: str) -> str:
    return name.lower().replace(",", "").replace(".", "").replace(" ", "_")[:40]


@dataclass
class ValidatorBResult:
    field_name: str
    final_status: Literal[
        "verified_after_dispute",
        "flagged_for_review",
        "verified_qa_pass",
        "verified_qa_fail",
    ]
    seeded_value: Any
    proposed_alternative: Any | None
    rationale: str
    sources: list[str]
    duration_ms: int = 0


async def validate_field(
    company_name: str,
    entity_type: str,
    field_name: str,
    field_label: str,
    seeded_value: Any,
    validator_a_result: ValidatorAResult,
    is_qa_sample: bool = False,
) -> ValidatorBResult:
    """Adversarially review a field that A disputed, or a 5% QA sample of verified fields."""
    if not settings.anthropic_api_key:
        status = "verified_qa_pass" if is_qa_sample else "flagged_for_review"
        return ValidatorBResult(
            field_name=field_name, final_status=status,
            seeded_value=seeded_value, proposed_alternative=None,
            rationale="API key not configured", sources=[],
        )

    mode = "QA sample check" if is_qa_sample else "dispute resolution"
    t0 = time.monotonic()

    try:
        _meta = f"# META: agent=validator_b company={_slugify(company_name)} field={field_name}\n"
        response = await claude.messages.create(
            model="claude-opus-4-7",
            max_tokens=700,
            system=(
                _meta
                + f"You are Validator B, an adversarial fact-checker ({mode}).\n"
                f"{SEARCH_GUIDANCE_B}\n\n"
                "Actively look for evidence that contradicts the seeded value. "
                "If this is a QA sample, verify the value even if A already verified it.\n"
                "Respond ONLY with JSON:\n"
                '{"final_status": "verified_after_dispute"|"flagged_for_review"|"verified_qa_pass"|"verified_qa_fail", '
                '"proposed_alternative": <alternative value or null>, '
                '"rationale": <string>, "sources": [<url>, ...]}'
            ),
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}],
            messages=[{
                "role": "user",
                "content": (
                    f"Company: {company_name}\n"
                    f"Field: {field_label} ({field_name})\n"
                    f"Seeded value: {json.dumps(seeded_value)}\n"
                    f"Validator A status: {validator_a_result.verification_status}\n"
                    f"Validator A notes: {validator_a_result.notes}\n\n"
                    f"Mode: {mode}. Challenge this value."
                ),
            }],
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        text = next((b.text for b in response.content if hasattr(b, "text")), "")
        m = re.search(r'\{.*\}', text, re.DOTALL)
        data = json.loads(m.group()) if m else {}

        valid_statuses = {"verified_after_dispute", "flagged_for_review", "verified_qa_pass", "verified_qa_fail"}
        final_status = data.get("final_status", "flagged_for_review")
        if final_status not in valid_statuses:
            final_status = "flagged_for_review"

        return ValidatorBResult(
            field_name=field_name,
            final_status=final_status,
            seeded_value=seeded_value,
            proposed_alternative=data.get("proposed_alternative"),
            rationale=data.get("rationale", ""),
            sources=data.get("sources", []),
            duration_ms=elapsed_ms,
        )

    except Exception as exc:
        logger.warning("validator_b failed for %s.%s: %s", entity_type, field_name, exc)
        fallback = "verified_qa_pass" if is_qa_sample else "flagged_for_review"
        return ValidatorBResult(
            field_name=field_name, final_status=fallback,
            seeded_value=seeded_value, proposed_alternative=None,
            rationale=str(exc), sources=[],
        )
