"""
app/seeding/strategies/site_scrape.py
───────────────────────────────────────
Strategy 2: scrape the company's own domain, then extract via Claude.
"""
import json
import logging
import time
from typing import Any

import httpx
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.seeding.strategies.web_search import StrategyResult

logger = logging.getLogger(__name__)
settings = get_settings()
claude = AsyncAnthropic(api_key=settings.anthropic_api_key)

_PAGES = ["", "/about", "/about-us", "/company", "/investors", "/careers"]


async def run(company_name: str, field_name: str, field_label: str, context: dict) -> StrategyResult:
    """Fetch the company's own website and extract the field with Claude."""
    website: str = context.get("website", "")
    if not website:
        logger.debug("site_scrape skipped: no website in context for %s", company_name)
        return StrategyResult(value=None, confidence=0.0)

    base = website.rstrip("/")
    page_text = ""
    fetched_url = ""

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for path in _PAGES:
            url = base + path
            try:
                resp = await client.get(url, headers={"User-Agent": "Aegis-GRC/1.0 (+https://aegis.app)"})
                if resp.status_code == 200:
                    page_text = resp.text[:8000]
                    fetched_url = url
                    break
            except Exception:
                continue

    if not page_text:
        return StrategyResult(value=None, confidence=0.0)

    t0 = time.monotonic()
    try:
        response = await claude.messages.create(
            model=settings.claude_model,
            max_tokens=400,
            system=(
                "You are a data extraction assistant. Given webpage HTML/text, extract a specific "
                "company data field. Respond ONLY with JSON:\n"
                '{"value": <extracted value or null>, "confidence": <0.0-1.0>}'
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Extract the '{field_label}' for {company_name} from this webpage content.\n\n"
                    f"Page URL: {fetched_url}\n\n"
                    f"Content:\n{page_text}"
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
        confidence = float(data.get("confidence", 0.0))
        logger.debug("site_scrape %s.%s confidence=%.2f elapsed=%dms", company_name, field_name, confidence, elapsed_ms)
        return StrategyResult(value=value, confidence=confidence, source_urls=[fetched_url] if value else [])

    except Exception as exc:
        logger.warning("site_scrape extraction failed for %s.%s: %s", company_name, field_name, exc)
        return StrategyResult(value=None, confidence=0.0)
