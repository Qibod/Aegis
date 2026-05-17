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


@dataclass
class StrategyResult:
    value: Any
    confidence: float
    source_urls: list[str] = field(default_factory=list)
    raw_response: str = ""


async def run(company_name: str, field_name: str, field_label: str, context: dict) -> StrategyResult:
    """Search the web for a specific field value about a company."""
    if not settings.anthropic_api_key:
        return StrategyResult(value=None, confidence=0.0)

    query = f'{company_name} {field_label}'
    system = (
        "You are a data researcher. Given a web search result, extract the requested field "
        "value for the company. Respond with a JSON object containing:\n"
        '  "value": <the extracted value, or null if not found>,\n'
        '  "confidence": <float 0.0-1.0 reflecting how certain you are>,\n'
        '  "source_urls": <list of URLs where the value was found>\n'
        "Only include values you are highly confident about (≥0.95). "
        "Do not fabricate. If uncertain, return confidence < 0.95."
    )

    t0 = time.monotonic()
    try:
        response = await claude.messages.create(
            model=settings.claude_model,
            max_tokens=500,
            system=system,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
            messages=[{"role": "user", "content": f"Find the {field_label} for {company_name}. Query: {query}"}],
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        text = next((b.text for b in response.content if hasattr(b, "text")), "")
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            import re
            m = re.search(r'\{.*\}', text, re.DOTALL)
            data = json.loads(m.group()) if m else {}

        value = data.get("value")
        confidence = float(data.get("confidence", 0.0))
        source_urls = data.get("source_urls", [])

        logger.debug("web_search %s.%s confidence=%.2f elapsed=%dms", company_name, field_name, confidence, elapsed_ms)
        return StrategyResult(value=value, confidence=confidence, source_urls=source_urls, raw_response=text)

    except Exception as exc:
        logger.warning("web_search failed for %s.%s: %s", company_name, field_name, exc)
        return StrategyResult(value=None, confidence=0.0)
