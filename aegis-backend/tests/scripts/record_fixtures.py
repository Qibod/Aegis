"""
tests/scripts/record_fixtures.py
─────────────────────────────────
One-shot recorder. Runs the relevant agent against real Claude (requires
LIVE_CLAUDE=1 and ANTHROPIC_API_KEY) and writes JSON to
tests/fixtures/claude_responses/<agent>__<company>__<field>.json.

Usage:
    LIVE_CLAUDE=1 python tests/scripts/record_fixtures.py \
        --agent seeder --company uber --field legal_name --strategy web_search

    LIVE_CLAUDE=1 python tests/scripts/record_fixtures.py \
        --agent validator_a --company uber --field legal_name

    # validator_b requires a prior validator_a fixture for the same company+field:
    LIVE_CLAUDE=1 python tests/scripts/record_fixtures.py \
        --agent validator_b --company uber --field legal_name

Re-run after seeder/validator prompt changes to refresh fixtures.

NOTE ON MODULE SHAPES (as of 2026-05-18)
─────────────────────────────────────────
* app.seeding.seeder_agent  — module-level async run() function, NOT a class.
  Signature: run(company_name, field_name, field_label, strategy, context) -> StrategyResult
  StrategyResult fields: value, confidence, source_urls, raw_response

* app.seeding.field_specs.FIELD_SPECS — dict[entity_type, list[FieldSpec]]
  Lookup helper: get_field_spec(entity_type, field_name) -> FieldSpec | None
  org_profiles fields are the most commonly recorded; pass --entity-type to override.

* app.validation.validator_a.validate_field
  Signature: validate_field(company_name, entity_type, field_name, field_label,
                            seeded_value, source_urls) -> ValidatorAResult

* app.validation.validator_b.validate_field
  Signature: validate_field(company_name, entity_type, field_name, field_label,
                            seeded_value, validator_a_result, is_qa_sample=False)
                            -> ValidatorBResult
  validator_b requires a ValidatorAResult — this script re-runs validator_a
  (or loads a cached fixture) to obtain one before calling validator_b.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Allow running from the repo root or aegis-backend/ without installing the package.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent  # aegis-backend/
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
RESP_DIR = FIXTURES_DIR / "claude_responses"


def _fixture_path(agent: str, company: str, field: str) -> Path:
    return RESP_DIR / f"{agent}__{company}__{field}.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record live-Claude fixtures for seeder/validator agents."
    )
    parser.add_argument(
        "--agent",
        required=True,
        choices=["seeder", "validator_a", "validator_b"],
        help="Which agent to invoke.",
    )
    parser.add_argument(
        "--company",
        required=True,
        help="Key in tests/fixtures/test_companies.json (e.g. uber, stripe).",
    )
    parser.add_argument(
        "--field",
        required=True,
        help="Field name to seed/validate (e.g. legal_name, hq_country).",
    )
    parser.add_argument(
        "--strategy",
        default="web_search",
        choices=["web_search", "site_scrape", "filings", "llm_inference"],
        help="Seeder strategy (only used when --agent seeder).",
    )
    parser.add_argument(
        "--entity-type",
        default="org_profiles",
        help="Entity type for FieldSpec lookup (default: org_profiles).",
    )
    args = parser.parse_args()

    if os.getenv("LIVE_CLAUDE") != "1":
        print(
            "ERROR: set LIVE_CLAUDE=1 to record fixtures.\n"
            "       Also ensure ANTHROPIC_API_KEY is set.",
            file=sys.stderr,
        )
        return 2

    RESP_DIR.mkdir(parents=True, exist_ok=True)
    asyncio.run(_record(args))
    return 0


async def _record(args: argparse.Namespace) -> None:
    companies = json.loads((FIXTURES_DIR / "test_companies.json").read_text())
    if args.company not in companies:
        raise SystemExit(
            f"Company {args.company!r} not found in test_companies.json. "
            f"Available: {list(companies.keys())}"
        )
    company = companies[args.company]

    payload = await _invoke_agent(
        agent=args.agent,
        strategy=args.strategy,
        entity_type=args.entity_type,
        company=company,
        field=args.field,
    )

    out = _fixture_path(args.agent, args.company, args.field)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"Wrote {out}")


async def _invoke_agent(
    agent: str,
    strategy: str,
    entity_type: str,
    company: dict,
    field: str,
) -> dict:
    company_name: str = company["company_name"]

    # ──────────────────────────────────────────────────────────────────
    # Resolve FieldSpec — searches all entity types if none found in the
    # requested entity_type, for convenience when the caller omits --entity-type.
    # ──────────────────────────────────────────────────────────────────
    from app.seeding.field_specs import FIELD_SPECS, get_field_spec

    spec = get_field_spec(entity_type, field)
    if spec is None:
        # Fall back: search all entity types.
        for et, specs in FIELD_SPECS.items():
            for s in specs:
                if s.name == field:
                    spec = s
                    entity_type = et
                    break
            if spec is not None:
                break

    if spec is None:
        raise SystemExit(
            f"No FieldSpec for field {field!r} in any entity type. "
            f"Known fields: {[s.name for sl in FIELD_SPECS.values() for s in sl]}"
        )

    field_label: str = spec.label

    # ──────────────────────────────────────────────────────────────────
    # SEEDER
    # app.seeding.seeder_agent.run(company_name, field_name, field_label,
    #                              strategy, context) -> StrategyResult
    # ──────────────────────────────────────────────────────────────────
    if agent == "seeder":
        from app.seeding import seeder_agent
        context: dict = {
            "domain": company.get("domain", ""),
            "is_public_company": company.get("is_public_company", False),
        }
        result = await seeder_agent.run(
            company_name=company_name,
            field_name=field,
            field_label=field_label,
            strategy=strategy,
            context=context,
        )
        return {
            "value": result.value,
            "confidence": result.confidence,
            "source_urls": result.source_urls,
            "strategy_used": strategy,
        }

    # ──────────────────────────────────────────────────────────────────
    # VALIDATOR A
    # app.validation.validator_a.validate_field(
    #     company_name, entity_type, field_name, field_label,
    #     seeded_value, source_urls) -> ValidatorAResult
    # ──────────────────────────────────────────────────────────────────
    if agent == "validator_a":
        from app.validation import validator_a

        # Use the expected value from test_companies.json if available;
        # otherwise fall back to re-running the seeder.
        seeded_value = company.get("expected", {}).get(field)
        source_urls: list[str] = []
        if seeded_value is None:
            seeder_fixture = _fixture_path("seeder", _company_key(company), field)
            if seeder_fixture.exists():
                seeder_data = json.loads(seeder_fixture.read_text())
                seeded_value = seeder_data.get("value")
                source_urls = seeder_data.get("source_urls", [])
            else:
                print(
                    f"WARNING: no expected value for {field!r} in test_companies.json "
                    f"and no seeder fixture at {seeder_fixture}. "
                    "Validating against null.",
                    file=sys.stderr,
                )

        result = await validator_a.validate_field(
            company_name=company_name,
            entity_type=entity_type,
            field_name=field,
            field_label=field_label,
            seeded_value=seeded_value,
            source_urls=source_urls,
        )
        return {
            "field_name": result.field_name,
            "seeded_value": result.seeded_value,
            "verified": result.verified,
            "verification_status": result.verification_status,
            "primary_source_url": result.primary_source_url,
            "notes": result.notes,
            "confidence": result.confidence,
            "duration_ms": result.duration_ms,
        }

    # ──────────────────────────────────────────────────────────────────
    # VALIDATOR B
    # app.validation.validator_b.validate_field(
    #     company_name, entity_type, field_name, field_label,
    #     seeded_value, validator_a_result, is_qa_sample=False) -> ValidatorBResult
    #
    # Requires a ValidatorAResult — loads from an existing fixture if
    # available, otherwise runs validator_a live first.
    # ──────────────────────────────────────────────────────────────────
    if agent == "validator_b":
        from app.validation import validator_a, validator_b
        from app.validation.validator_a import ValidatorAResult

        company_key = _company_key(company)
        va_fixture = _fixture_path("validator_a", company_key, field)

        if va_fixture.exists():
            va_data = json.loads(va_fixture.read_text())
            a_result = ValidatorAResult(
                field_name=va_data["field_name"],
                seeded_value=va_data["seeded_value"],
                verified=va_data["verified"],
                verification_status=va_data["verification_status"],
                primary_source_url=va_data.get("primary_source_url"),
                notes=va_data.get("notes", ""),
                confidence=va_data.get("confidence", 0.0),
                duration_ms=va_data.get("duration_ms", 0),
            )
            seeded_value = va_data["seeded_value"]
            print(f"Loaded validator_a fixture from {va_fixture}")
        else:
            print(
                f"No validator_a fixture found at {va_fixture}; "
                "running validator_a live first …",
                file=sys.stderr,
            )
            seeded_value = company.get("expected", {}).get(field)
            source_urls = []
            a_result = await validator_a.validate_field(
                company_name=company_name,
                entity_type=entity_type,
                field_name=field,
                field_label=field_label,
                seeded_value=seeded_value,
                source_urls=source_urls,
            )
            # Persist the intermediate validator_a result so future runs reuse it.
            va_fixture.write_text(
                json.dumps(
                    {
                        "field_name": a_result.field_name,
                        "seeded_value": a_result.seeded_value,
                        "verified": a_result.verified,
                        "verification_status": a_result.verification_status,
                        "primary_source_url": a_result.primary_source_url,
                        "notes": a_result.notes,
                        "confidence": a_result.confidence,
                        "duration_ms": a_result.duration_ms,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            print(f"Auto-saved intermediate validator_a fixture to {va_fixture}")

        b_result = await validator_b.validate_field(
            company_name=company_name,
            entity_type=entity_type,
            field_name=field,
            field_label=field_label,
            seeded_value=seeded_value,
            validator_a_result=a_result,
        )
        return {
            "field_name": b_result.field_name,
            "final_status": b_result.final_status,
            "seeded_value": b_result.seeded_value,
            "proposed_alternative": b_result.proposed_alternative,
            "rationale": b_result.rationale,
            "sources": b_result.sources,
            "duration_ms": b_result.duration_ms,
        }

    raise SystemExit(f"Unknown agent {agent!r}")


def _company_key(company: dict) -> str:
    """Reverse-lookup the company key from its company_name for fixture paths."""
    try:
        companies = json.loads((FIXTURES_DIR / "test_companies.json").read_text())
        for key, data in companies.items():
            if data.get("company_name") == company.get("company_name"):
                return key
    except Exception:
        pass
    # Fallback: slugify the company_name.
    return company.get("company_name", "unknown").lower().replace(" ", "_").replace(",", "").replace(".", "")


if __name__ == "__main__":
    sys.exit(main())
