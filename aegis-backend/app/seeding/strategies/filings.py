"""
app/seeding/strategies/filings.py
───────────────────────────────────
Strategy 3: SEC EDGAR — extract field from public company filings.
Skipped automatically for non-public companies (no stock_ticker).
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

EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index?q={query}&dateRange=custom&startdt=2023-01-01&forms=10-K,20-F"
EDGAR_HEADERS = {"User-Agent": "Aegis-GRC contact@aegis.app"}


async def run(company_name: str, field_name: str, field_label: str, context: dict) -> StrategyResult:
    """Fetch SEC EDGAR 10-K/20-F for a public company and extract the field."""
    ticker: str = context.get("stock_ticker", "")
    is_public: bool = bool(context.get("is_public_company") or ticker)

    if not is_public:
        logger.debug("filings skipped: %s is not a public company", company_name)
        return StrategyResult(value=None, confidence=0.0)

    search_query = ticker if ticker else company_name
    url = f"https://efts.sec.gov/LATEST/search-index?q=%22{search_query}%22&forms=10-K,20-F&dateRange=custom&startdt=2023-01-01"

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url, headers=EDGAR_HEADERS)
            data = resp.json()
        except Exception as exc:
            logger.warning("EDGAR search failed for %s: %s", company_name, exc)
            return StrategyResult(value=None, confidence=0.0)

    hits = data.get("hits", {}).get("hits", [])
    if not hits:
        return StrategyResult(value=None, confidence=0.0)

    filing = hits[0].get("_source", {})
    excerpt = filing.get("file_date", "") + " " + filing.get("entity_name", "") + "\n" + filing.get("description", "")[:3000]
    filing_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={search_query}&type=10-K&dateb=&owner=include&count=1"

    t0 = time.monotonic()
    try:
        response = await claude.messages.create(
            model=settings.claude_model,
            max_tokens=400,
            system=(
                "You are a financial data analyst. Extract a specific field value from SEC filing metadata. "
                'Respond ONLY with JSON: {"value": <extracted value or null>, "confidence": <0.0-1.0>}'
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Extract '{field_label}' for {company_name} from this SEC filing excerpt:\n\n{excerpt}"
                ),
            }],
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        text = response.content[0].text if response.content else ""

        try:
            result = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            import re
            m = re.search(r'\{.*\}', text, re.DOTALL)
            result = json.loads(m.group()) if m else {}

        value = result.get("value")
        confidence = float(result.get("confidence", 0.0))
        logger.debug("filings %s.%s confidence=%.2f elapsed=%dms", company_name, field_name, confidence, elapsed_ms)
        return StrategyResult(value=value, confidence=confidence, source_urls=[filing_url] if value else [])

    except Exception as exc:
        logger.warning("filings extraction failed for %s.%s: %s", company_name, field_name, exc)
        return StrategyResult(value=None, confidence=0.0)
