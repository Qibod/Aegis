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


async def run(company_name: str, field_name: str, field_label: str, context: dict) -> StrategyResult:
    """Infer the field value from existing profile context — lowest confidence, last resort."""
    context_summary = json.dumps({k: v for k, v in context.items() if v}, indent=2)[:2000]

    t0 = time.monotonic()
    try:
        response = await claude.messages.create(
            model=settings.claude_model,
            max_tokens=400,
            system=(
                "You are a GRC data analyst. Based only on the company profile context provided, "
                "infer the requested field value. This is a last-resort inference — be honest about "
                "uncertainty. Confidence should rarely exceed 0.80 for inferred values.\n"
                'Respond ONLY with JSON: {"value": <inferred value or null>, "confidence": <0.0-1.0>}'
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Company: {company_name}\n"
                    f"Field to infer: {field_label}\n\n"
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
        confidence = min(float(data.get("confidence", 0.0)), 0.85)  # cap inferred confidence
        logger.debug("llm_inference %s.%s confidence=%.2f elapsed=%dms", company_name, field_name, confidence, elapsed_ms)
        return StrategyResult(value=value, confidence=confidence, source_urls=[])

    except Exception as exc:
        logger.warning("llm_inference failed for %s.%s: %s", company_name, field_name, exc)
        return StrategyResult(value=None, confidence=0.0)
