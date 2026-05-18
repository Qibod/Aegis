"""
app/seeding/strategies/web_search.py
──────────────────────────────────────
Strategy 1: web search via Claude's built-in web_search tool.
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.seeding.confidence import extract_confidence

logger = logging.getLogger(__name__)
settings = get_settings()
claude = AsyncAnthropic(api_key=settings.anthropic_api_key)


def _slugify(name: str) -> str:
    return name.lower().replace(",", "").replace(".", "").replace(" ", "_")[:40]


@dataclass
class StrategyResult:
    value: Any
    confidence: float
    source_urls: list[str] = field(default_factory=list)
    raw_response: str = ""


_FIELD_TYPE_HINTS: dict[str, str] = {
    "hq_country":                      "ISO 3166-1 alpha-2 code (e.g. 'US', 'GB', 'NL') — do NOT return the full country name",
    "year_founded":                    "4-digit integer year only (e.g. 2009)",
    "employee_range":                  "numeric range string (e.g. '10001-50000'); for large enterprises use '50001-100000' or '100001+'",
    "annual_revenue_range":            "revenue range string (e.g. '$10B-$50B' or '$1B-$10B')",
    "website":                         "the official website URL with https:// — do not include trailing slash",
    "logo_url":                        "direct logo image URL; prefer Clearbit format: https://logo.clearbit.com/{domain}",
    "uses_ai_ml":                      "boolean — true or false (not a string)",
    "handles_personal_data":           "boolean — true or false (not a string)",
    "handles_sensitive_personal_data": "boolean — true or false (not a string)",
    "handles_payment_data":            "boolean — true or false (not a string)",
    "handles_health_data":             "boolean — true or false (not a string)",
    "handles_classified_data":         "boolean — true or false (not a string)",
    "data_sensitivity":                "one of: 'low', 'medium', 'high', 'critical'",
    "segment_type":                    "one of: 'b2b', 'b2c', 'b2g', 'mixed'",
    "presence_type":                   "one of: 'headquarters', 'operational', 'sales', 'legal'",
    "tier":                            "one of: 'tier_1', 'tier_2', 'tier_3'",
}


async def run(company_name: str, field_name: str, field_label: str, context: dict) -> StrategyResult:
    """Search the web for a specific field value about a company."""
    if not settings.anthropic_api_key:
        return StrategyResult(value=None, confidence=0.0)

    type_hint = _FIELD_TYPE_HINTS.get(field_name, "")
    type_note = f"\nRequired format: {type_hint}" if type_hint else ""

    _meta = f"# META: agent=seeder company={_slugify(company_name)} field={field_name}\n"
    system = (
        _meta
        + "You are a data researcher. Use the web_search tool to find authoritative information "
        "about a company, then extract the specific field requested.\n\n"
        "After searching, respond with ONLY a JSON object — no markdown, no preamble:\n"
        '{"value": <the extracted value or null>, '
        '"confidence": <float 0.0-1.0>, '
        '"source_urls": <list of source URLs>}\n\n'
        "Set confidence ≥ 0.95 only when the value is definitively confirmed by an authoritative "
        "source (official website, regulatory filing, Wikipedia). "
        "Return null with confidence 0.0 if you cannot find the value."
    )

    t0 = time.monotonic()
    try:
        response = await claude.messages.create(
            model=settings.claude_model,
            max_tokens=600,
            system=system,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{
                "role": "user",
                "content": (
                    f"Find the {field_label} for {company_name}.{type_note}\n\n"
                    f"Search for: {company_name} {field_label}"
                ),
            }],
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        text = next((b.text for b in response.content if hasattr(b, "text")), "")
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            import re
            m = re.search(r'\{.*?\}', text, re.DOTALL)
            data = json.loads(m.group()) if m else {}

        value = data.get("value")
        confidence = float(data.get("confidence", 0.0))
        source_urls = data.get("source_urls", [])
        if isinstance(source_urls, str):
            source_urls = [source_urls]

        logger.debug("web_search %s.%s confidence=%.2f elapsed=%dms", company_name, field_name, confidence, elapsed_ms)
        return StrategyResult(value=value, confidence=confidence, source_urls=source_urls, raw_response=text)

    except Exception as exc:
        logger.warning("web_search failed for %s.%s: %s", company_name, field_name, exc)
        return StrategyResult(value=None, confidence=0.0)
