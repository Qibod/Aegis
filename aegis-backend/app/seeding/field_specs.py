"""
app/seeding/field_specs.py
──────────────────────────
Required-field registry per entity type.

FIELD_SPECS maps entity_type → list of FieldSpec.
Each FieldSpec describes one required field: its name, a human label used in
search queries, and whether the filings strategy is applicable.
"""
from dataclasses import dataclass


@dataclass
class FieldSpec:
    name: str
    label: str                        # human-readable label used in search queries
    filings_applicable: bool = True   # False for fields irrelevant to SEC filings


FIELD_SPECS: dict[str, list[FieldSpec]] = {
    "org_profiles": [
        FieldSpec("legal_name",           "legal registered company name"),
        FieldSpec("trading_name",         "trading name or brand name"),
        FieldSpec("year_founded",         "year the company was founded"),
        FieldSpec("employee_range",       "number of employees / headcount range"),
        FieldSpec("annual_revenue_range", "annual revenue range"),
        FieldSpec("hq_country",           "headquarters country (ISO 2-letter code)"),
        FieldSpec("hq_city",              "headquarters city"),
        FieldSpec("website",              "official website URL"),
        FieldSpec("description",          "company description or business summary"),
        FieldSpec("logo_url",             "company logo image URL"),
        FieldSpec("stock_ticker",         "stock ticker symbol", filings_applicable=True),
    ],
    "lines_of_business": [
        FieldSpec("name",       "business line or division name",              filings_applicable=False),
        FieldSpec("status",     "business line status (active/planned/...)",   filings_applicable=False),
        FieldSpec("is_primary", "primary line of business flag",               filings_applicable=False),
    ],
    "org_geographies": [
        FieldSpec("country",          "country of operation (ISO 2-letter code)", filings_applicable=False),
        FieldSpec("presence_type",    "type of presence (headquarters/operational/...)", filings_applicable=False),
        FieldSpec("regulatory_flags", "applicable regulations in this geography",  filings_applicable=False),
    ],
    "org_industries": [
        FieldSpec("code",           "NAICS or GICS industry classification code"),
        FieldSpec("name",           "industry name"),
        FieldSpec("classification", "primary or secondary industry classification"),
    ],
    "org_products": [
        FieldSpec("name",             "product or service name",        filings_applicable=False),
        FieldSpec("product_type",     "product type category",          filings_applicable=False),
        FieldSpec("status",           "product status (live/beta/...)", filings_applicable=False),
        FieldSpec("data_sensitivity", "data sensitivity level",         filings_applicable=False),
    ],
    "org_customer_segments": [
        FieldSpec("name",                "customer segment name",               filings_applicable=False),
        FieldSpec("segment_type",        "segment type (b2b/b2c/...)",          filings_applicable=False),
        FieldSpec("includes_minors",     "whether segment includes minors",     filings_applicable=False),
        FieldSpec("includes_healthcare", "whether segment includes healthcare", filings_applicable=False),
        FieldSpec("includes_financial",  "whether segment includes financial",  filings_applicable=False),
    ],
    "org_third_parties": [
        FieldSpec("name",     "third-party vendor name",     filings_applicable=False),
        FieldSpec("category", "vendor category",             filings_applicable=False),
        FieldSpec("tier",     "vendor tier (tier_1/tier_2)", filings_applicable=False),
    ],
    "org_data_tech_profiles": [
        FieldSpec("uses_ai_ml",                      "whether company uses AI/ML",           filings_applicable=False),
        FieldSpec("handles_personal_data",           "handles personal data flag",           filings_applicable=False),
        FieldSpec("handles_sensitive_personal_data", "handles sensitive personal data flag", filings_applicable=False),
        FieldSpec("handles_payment_data",            "handles payment data flag",            filings_applicable=False),
        FieldSpec("handles_health_data",             "handles health data flag",             filings_applicable=False),
        FieldSpec("handles_classified_data",         "handles classified data flag",         filings_applicable=False),
        FieldSpec("cloud_providers",                 "cloud infrastructure providers used",  filings_applicable=False),
    ],
}


def get_field_spec(entity_type: str, field_name: str) -> FieldSpec | None:
    return next((s for s in FIELD_SPECS.get(entity_type, []) if s.name == field_name), None)
