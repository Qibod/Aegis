"""
app/validation/validator_a.py
───────────────────────────────
Validator A — "Source Verifier".
First-pass verification of a seeded field against primary sources.
"""
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.validation.sources.allowlist_a import SEARCH_GUIDANCE_A

logger = logging.getLogger(__name__)
settings = get_settings()
claude = AsyncAnthropic(api_key=settings.anthropic_api_key)


def _slugify(name: str) -> str:
    return name.lower().replace(",", "").replace(".", "").replace(" ", "_")[:40]


@dataclass
class ValidatorAResult:
    field_name: str
    seeded_value: Any
    verified: bool
    verification_status: Literal["verified", "disputed", "unverifiable"]
    primary_source_url: str | None
    notes: str
    confidence: float
    duration_ms: int = 0


async def validate_field(
    company_name: str,
    entity_type: str,
    field_name: str,
    field_label: str,
    seeded_value: Any,
    source_urls: list[str],
) -> ValidatorAResult:
    """Verify a single seeded field against primary sources."""
    if not settings.anthropic_api_key:
        return ValidatorAResult(
            field_name=field_name, seeded_value=seeded_value,
            verified=False, verification_status="unverifiable",
            primary_source_url=None, notes="API key not configured", confidence=0.0,
        )

    source_hint = f"Original sources: {source_urls}" if source_urls else "No original sources provided."
    t0 = time.monotonic()

    try:
        _meta = f"# META: agent=validator_a company={_slugify(company_name)} field={field_name}\n"
        response = await claude.messages.create(
            model="claude-opus-4-7",
            max_tokens=600,
            system=(
                _meta
                + f"You are Validator A, a rigorous fact-checker for GRC data.\n"
                f"{SEARCH_GUIDANCE_A}\n\n"
                "Verify whether the seeded value is accurate. Respond ONLY with JSON:\n"
                '{"verified": <bool>, "verification_status": "verified"|"disputed"|"unverifiable", '
                '"primary_source_url": <url or null>, "notes": <string>, "confidence": <0.0-1.0>}'
            ),
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{
                "role": "user",
                "content": (
                    f"Company: {company_name}\n"
                    f"Field: {field_label} ({field_name})\n"
                    f"Seeded value: {json.dumps(seeded_value)}\n"
                    f"{source_hint}\n\n"
                    "Verify this value against primary sources."
                ),
            }],
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        text = next((b.text for b in response.content if hasattr(b, "text")), "")
        m = re.search(r'\{.*\}', text, re.DOTALL)
        data = json.loads(m.group()) if m else {}

        status = data.get("verification_status", "unverifiable")
        if status not in ("verified", "disputed", "unverifiable"):
            status = "unverifiable"

        return ValidatorAResult(
            field_name=field_name,
            seeded_value=seeded_value,
            verified=data.get("verified", False),
            verification_status=status,
            primary_source_url=data.get("primary_source_url"),
            notes=data.get("notes", ""),
            confidence=float(data.get("confidence", 0.0)),
            duration_ms=elapsed_ms,
        )

    except Exception as exc:
        logger.warning("validator_a failed for %s.%s: %s", entity_type, field_name, exc)
        return ValidatorAResult(
            field_name=field_name, seeded_value=seeded_value,
            verified=False, verification_status="unverifiable",
            primary_source_url=None, notes=str(exc), confidence=0.0,
        )
