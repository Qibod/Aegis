"""
app/seeding/confidence.py
─────────────────────────
Confidence scoring helpers for the completeness loop.
"""
import re
from typing import Any

MIN_CONFIDENCE: float = 0.95


def is_confident(confidence: float) -> bool:
    return confidence >= MIN_CONFIDENCE


def extract_confidence(response_text: str, value: Any) -> float:
    """
    Extract a confidence score from Claude's structured response.
    Claude is instructed to include: {"confidence": 0.97}
    Falls back to heuristic if not found.
    """
    match = re.search(r'"confidence"\s*:\s*([0-9.]+)', response_text)
    if match:
        try:
            return min(1.0, max(0.0, float(match.group(1))))
        except ValueError:
            pass

    # Heuristic fallback — below threshold so next strategy is tried
    if value is None or value == "" or value == [] or value == {}:
        return 0.0
    if isinstance(value, str) and value.lower() in {"unknown", "n/a", "tbd", "not available"}:
        return 0.0

    return 0.70
