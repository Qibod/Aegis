"""tests/scripts/synthesize_fixtures.py — generate mock Claude responses from golden values."""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
GOLDEN = json.loads((ROOT / "fixtures" / "golden_seeded_values.json").read_text())
OUT = ROOT / "fixtures" / "claude_responses"

SEEDER_TEMPLATE = {
    "value": None,
    "confidence": 0.96,
    "source_urls": ["https://www.example.com/source"],
    "strategy_used": "web_search",
}

VALIDATOR_A_TEMPLATE = {
    "field": "",
    "seeded_value": None,
    "verified": True,
    "verification_status": "verified",
    "primary_source_url": "https://www.example.com/source",
    "notes": "Synthesized fixture from golden values.",
    "confidence": 0.96,
    "duration_ms": 1200,
}


def emit(agent: str, company: str, field: str, value):
    if agent == "seeder":
        payload = {**SEEDER_TEMPLATE, "value": value}
    elif agent == "validator_a":
        payload = {**VALIDATOR_A_TEMPLATE, "field": field, "seeded_value": value}
    else:
        raise SystemExit(agent)
    out = OUT / f"{agent}__{company}__{field}.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))


def main():
    for company, sections in GOLDEN.items():
        for section, fields in sections.items():
            for field, value in fields.items():
                if field.endswith("_includes") or field == "primary_code_prefix":
                    continue  # assertion-only, not seeded directly
                emit("seeder", company, field, value)
                emit("validator_a", company, field, value)
    print(f"Wrote fixtures to {OUT}")


if __name__ == "__main__":
    main()
