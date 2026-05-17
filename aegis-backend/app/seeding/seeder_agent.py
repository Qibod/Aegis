"""
app/seeding/seeder_agent.py
────────────────────────────
Dispatches seeding strategies in order and returns the best result.
Each strategy gets one attempt per call to run().
"""
import logging
from dataclasses import dataclass
from typing import Any

from app.seeding.strategies import web_search, site_scrape, filings, llm_inference
from app.seeding.strategies.web_search import StrategyResult

logger = logging.getLogger(__name__)

STRATEGIES = ["web_search", "site_scrape", "filings", "llm_inference"]

_STRATEGY_MAP = {
    "web_search":    web_search.run,
    "site_scrape":   site_scrape.run,
    "filings":       filings.run,
    "llm_inference": llm_inference.run,
}


async def run(
    company_name: str,
    field_name: str,
    field_label: str,
    strategy: str,
    context: dict,
) -> StrategyResult:
    """Run a single strategy and return its result."""
    fn = _STRATEGY_MAP.get(strategy)
    if fn is None:
        logger.error("Unknown strategy: %s", strategy)
        return StrategyResult(value=None, confidence=0.0)
    return await fn(company_name, field_name, field_label, context)
