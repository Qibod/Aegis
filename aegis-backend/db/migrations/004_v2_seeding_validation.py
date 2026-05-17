"""
db/migrations/004_v2_seeding_validation.py
──────────────────────────────────────────
Company Profile v2.1 — completeness seeding, validation agents, GRC assistant.

New tables:
  seeding_attempts        — every attempt log entry for completeness loop
  field_validations       — Validator A + B results per field
  seeding_proposals       — daily re-seed proposals awaiting admin approval
  assistant_interactions  — GRC assistant audit log (1-year retention)

Columns added to existing profile tables:
  field_status_map        — per-field status: seeded|unknown|user_edited|verified|...
  field_confidence_map    — per-field confidence float 0.0–1.0
  field_source_map        — per-field list[str] of source URLs

Column added to organizations:
  is_synthetic            — marks throwaway synthetic monitoring tenants
  synthetic_proposals_pending — badge count cache

SQL view:
  field_verification_state — latest A + B result per (org, entity, field)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "004_v2_seeding_validation"
down_revision = "003_risk_universe"
branch_labels = None
depends_on = None

PROFILE_TABLES = [
    "org_profiles",
    "lines_of_business",
    "org_geographies",
    "org_industries",
    "org_products",
    "org_customer_segments",
    "org_third_parties",
    "org_data_tech_profiles",
]


def upgrade():
    # ── seeding_attempts ──────────────────────────────────────────────────────
    op.create_table(
        "seeding_attempts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=True),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("strategy", sa.String(30), nullable=False),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("result_value", JSONB, nullable=True),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("source_urls", JSONB, nullable=False, server_default="[]"),
        sa.Column("succeeded", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_seeding_attempts_org_id", "seeding_attempts", ["org_id"])
    op.create_index("ix_seeding_attempts_org_field", "seeding_attempts", ["org_id", "field_name"])

    # ── field_validations ─────────────────────────────────────────────────────
    op.create_table(
        "field_validations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("validator", sa.String(10), nullable=False),   # "A", "B", or "user"
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("seeded_value", JSONB, nullable=True),
        sa.Column("proposed_alternative", JSONB, nullable=True),
        sa.Column("sources", JSONB, nullable=False, server_default="[]"),
        sa.Column("notes", sa.Text, nullable=False, server_default="''"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("resolution_source", sa.String(20), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_field_validations_org_id", "field_validations", ["org_id"])
    op.create_index(
        "ix_field_validations_lookup",
        "field_validations",
        ["org_id", "entity_type", "entity_id", "field_name"],
    )

    # ── seeding_proposals ─────────────────────────────────────────────────────
    op.create_table(
        "seeding_proposals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("proposed_value", JSONB, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("sources", JSONB, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="'pending'"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_seeding_proposals_org_id", "seeding_proposals", ["org_id"])
    op.create_index("ix_seeding_proposals_pending", "seeding_proposals", ["org_id", "status"])

    # ── assistant_interactions ────────────────────────────────────────────────
    op.create_table(
        "assistant_interactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(15), nullable=False),
        sa.Column("content", JSONB, nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_assistant_interactions_org_session", "assistant_interactions", ["org_id", "session_id"])
    op.create_index("ix_assistant_interactions_user", "assistant_interactions", ["user_id"])

    # ── JSONB status/confidence/source maps on all profile tables ─────────────
    for table in PROFILE_TABLES:
        op.add_column(table, sa.Column("field_status_map", JSONB, nullable=True, server_default="'{}'"))
        op.add_column(table, sa.Column("field_confidence_map", JSONB, nullable=True, server_default="'{}'"))
        op.add_column(table, sa.Column("field_source_map", JSONB, nullable=True, server_default="'{}'"))

    # ── organizations additions ───────────────────────────────────────────────
    op.add_column("organizations", sa.Column("is_synthetic", sa.Boolean, nullable=True, server_default="false"))
    op.add_column("organizations", sa.Column("synthetic_proposals_pending", sa.Integer, nullable=True, server_default="0"))

    # ── field_verification_state view ─────────────────────────────────────────
    op.execute("""
        CREATE VIEW field_verification_state AS
        SELECT
            fv.org_id,
            fv.entity_type,
            fv.entity_id,
            fv.field_name,
            (
                SELECT fv2.status FROM field_validations fv2
                WHERE fv2.org_id = fv.org_id
                  AND fv2.entity_type = fv.entity_type
                  AND fv2.entity_id = fv.entity_id
                  AND fv2.field_name = fv.field_name
                  AND fv2.validator = 'A'
                ORDER BY fv2.validated_at DESC LIMIT 1
            ) AS status_a,
            (
                SELECT fv3.status FROM field_validations fv3
                WHERE fv3.org_id = fv.org_id
                  AND fv3.entity_type = fv.entity_type
                  AND fv3.entity_id = fv.entity_id
                  AND fv3.field_name = fv.field_name
                  AND fv3.validator = 'B'
                ORDER BY fv3.validated_at DESC LIMIT 1
            ) AS status_b,
            (
                SELECT fv4.proposed_alternative FROM field_validations fv4
                WHERE fv4.org_id = fv.org_id
                  AND fv4.entity_type = fv.entity_type
                  AND fv4.entity_id = fv.entity_id
                  AND fv4.field_name = fv.field_name
                  AND fv4.validator = 'B'
                ORDER BY fv4.validated_at DESC LIMIT 1
            ) AS proposed_alternative,
            (
                SELECT fv5.sources FROM field_validations fv5
                WHERE fv5.org_id = fv.org_id
                  AND fv5.entity_type = fv.entity_type
                  AND fv5.entity_id = fv.entity_id
                  AND fv5.field_name = fv.field_name
                ORDER BY fv5.validated_at DESC LIMIT 1
            ) AS latest_sources,
            (
                SELECT fv6.validated_at FROM field_validations fv6
                WHERE fv6.org_id = fv.org_id
                  AND fv6.entity_type = fv.entity_type
                  AND fv6.entity_id = fv.entity_id
                  AND fv6.field_name = fv.field_name
                ORDER BY fv6.validated_at DESC LIMIT 1
            ) AS last_validated_at
        FROM field_validations fv
        GROUP BY fv.org_id, fv.entity_type, fv.entity_id, fv.field_name;
    """)


def downgrade():
    op.execute("DROP VIEW IF EXISTS field_verification_state")

    op.drop_column("organizations", "synthetic_proposals_pending")
    op.drop_column("organizations", "is_synthetic")

    for table in reversed(PROFILE_TABLES):
        op.drop_column(table, "field_source_map")
        op.drop_column(table, "field_confidence_map")
        op.drop_column(table, "field_status_map")

    op.drop_table("assistant_interactions")
    op.drop_table("seeding_proposals")
    op.drop_table("field_validations")
    op.drop_table("seeding_attempts")
