"""
app/seeding/strategies/llm_inference.py
──────────────────────────────────────────
Strategy 4: infer the field from already-seeded context (lowest confidence).
Used only after all other strategies fail.
"""
import json
import logging
import time

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.seeding.strategies.web_search import StrategyResult

logger = logging.getLogger(__name__)
settings = get_settings()
claude = AsyncAnthropic(api_key=settings.anthropic_api_key)


def _slugify(name: str) -> str:
    return name.lower().replace(",", "").replace(".", "").replace(" ", "_")[:40]


_FIELD_TYPE_HINTS: dict[str, str] = {
    "hq_country":                      "ISO 3166-1 alpha-2 code (e.g. 'US', 'GB', 'NL')",
    "year_founded":                    "4-digit integer year (e.g. 2009)",
    "employee_range":                  "string range (e.g. '10001-50000' or 'enterprise')",
    "annual_revenue_range":            "string range (e.g. '$10B-$50B')",
    "website":                         "full URL with https:// (e.g. 'https://www.example.com')",
    "logo_url":                        "direct image URL (e.g. 'https://logo.clearbit.com/example.com')",
    "uses_ai_ml":                      "boolean true or false",
    "handles_personal_data":           "boolean true or false",
    "handles_sensitive_personal_data": "boolean true or false",
    "handles_payment_data":            "boolean true or false",
    "handles_health_data":             "boolean true or false",
    "handles_classified_data":         "boolean true or false",
    "is_primary":                      "boolean true or false",
    "data_sensitivity":                "one of: 'low', 'medium', 'high', 'critical'",
    "segment_type":                    "one of: 'b2b', 'b2c', 'b2g', 'mixed'",
    "presence_type":                   "one of: 'headquarters', 'operational', 'sales', 'legal'",
    "tier":                            "one of: 'tier_1', 'tier_2', 'tier_3'",
    "classification":                  "one of: 'primary', 'secondary'",
}


async def run(company_name: str, field_name: str, field_label: str, context: dict) -> StrategyResult:
    """Infer the field value from existing profile context — last resort after web strategies."""
    context_summary = json.dumps({k: v for k, v in context.items() if v}, indent=2)[:2000]
    type_hint = _FIELD_TYPE_HINTS.get(field_name, "")
    type_note = f"\nExpected format: {type_hint}" if type_hint else ""

    t0 = time.monotonic()
    try:
        _meta = f"# META: agent=seeder company={_slugify(company_name)} field={field_name}\n"
        response = await claude.messages.create(
            model=settings.claude_model,
            max_tokens=400,
            system=(
                _meta
                + "You are a GRC data analyst. Use the provided company context AND your training "
                "knowledge to determine the requested field value.\n\n"
                "Confidence guidelines:\n"
                "- Use 0.95-0.97 ONLY when you are genuinely certain (e.g. this is a globally "
                "recognised company and the fact is publicly established beyond doubt).\n"
                "- Use 0.70-0.89 for reasonable inferences from context clues.\n"
                "- Use 0.50-0.69 for educated guesses.\n"
                "- Return null with 0.0 if you cannot determine the value.\n"
                "Never fabricate values for obscure or unknown companies.\n\n"
                'Respond ONLY with JSON: {"value": <value or null>, "confidence": <0.0-1.0>}'
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Company: {company_name}\n"
                    f"Field to determine: {field_label}{type_note}\n\n"
                    f"Known context:\n{context_summary}"
                ),
            }],
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        text = response.content[0].text if response.content else ""

        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            import re
            m = re.search(r'\{.*\}', text, re.DOTALL)
            data = json.loads(m.group()) if m else {}

        value = data.get("value")
        # Cap at 0.97 — prevents overconfidence while allowing high-certainty known facts
        confidence = min(float(data.get("confidence", 0.0)), 0.97)
        logger.debug("llm_inference %s.%s confidence=%.2f elapsed=%dms", company_name, field_name, confidence, elapsed_ms)
        return StrategyResult(value=value, confidence=confidence, source_urls=[])

    except Exception as exc:
        logger.warning("llm_inference failed for %s.%s: %s", company_name, field_name, exc)
        return StrategyResult(value=None, confidence=0.0)
