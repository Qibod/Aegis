"""
db/migrations/002_company_profile.py
──────────────────────────────────────
Company Profile tables — 9 new tables for org profile, LOBs, geographies,
industries, products, customer segments, third-party deps, data/tech profile,
and change log.

Run with: alembic upgrade head
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "002_company_profile"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade():
    # ── org_profiles ──────────────────────────────────────────────────────
    op.create_table("org_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("trading_name", sa.String(255)),
        sa.Column("year_founded", sa.Integer),
        sa.Column("employee_range", sa.String(50)),
        sa.Column("annual_revenue_range", sa.String(50)),
        sa.Column("hq_country", sa.String(2)),
        sa.Column("hq_city", sa.String(100)),
        sa.Column("stock_ticker", sa.String(20)),
        sa.Column("website", sa.String(500)),
        sa.Column("description", sa.String(500)),
        sa.Column("logo_url", sa.String(500)),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_org_profiles_org_id", "org_profiles", ["org_id"])

    # ── lines_of_business ─────────────────────────────────────────────────
    op.create_table("lines_of_business",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(20), nullable=False, server_default="'active'"),
        sa.Column("launch_date", sa.Date),
        sa.Column("revenue_contribution_pct", sa.Integer),
        sa.Column("is_primary", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_lob_org_id", "lines_of_business", ["org_id"])

    # ── org_geographies ───────────────────────────────────────────────────
    op.create_table("org_geographies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("region", sa.String(50)),
        sa.Column("state_province", sa.String(100)),
        sa.Column("presence_type", sa.String(30), nullable=False, server_default="'operational'"),
        sa.Column("lob_ids", JSONB, server_default="[]"),
        sa.Column("regulatory_flags", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_geo_org_id", "org_geographies", ["org_id"])

    # ── org_industries ────────────────────────────────────────────────────
    op.create_table("org_industries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("classification", sa.String(20), nullable=False, server_default="'secondary'"),
        sa.Column("lob_ids", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_industry_org_id", "org_industries", ["org_id"])

    # ── org_products ──────────────────────────────────────────────────────
    op.create_table("org_products",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("product_type", sa.String(30), nullable=False, server_default="'product'"),
        sa.Column("lob_id", UUID(as_uuid=True)),
        sa.Column("geography_ids", JSONB, server_default="[]"),
        sa.Column("customer_segment_ids", JSONB, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="'live'"),
        sa.Column("launch_date", sa.Date),
        sa.Column("data_sensitivity", sa.String(20), nullable=False, server_default="'low'"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_products_org_id", "org_products", ["org_id"])

    # ── org_customer_segments ─────────────────────────────────────────────
    op.create_table("org_customer_segments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("segment_type", sa.String(20), nullable=False, server_default="'b2b'"),
        sa.Column("includes_minors", sa.Boolean, server_default="false"),
        sa.Column("includes_healthcare", sa.Boolean, server_default="false"),
        sa.Column("includes_financial", sa.Boolean, server_default="false"),
        sa.Column("geography_ids", JSONB, server_default="[]"),
        sa.Column("lob_ids", JSONB, server_default="[]"),
        sa.Column("estimated_size", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_segments_org_id", "org_customer_segments", ["org_id"])

    # ── org_third_parties ─────────────────────────────────────────────────
    op.create_table("org_third_parties",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(40), nullable=False, server_default="'saas_vendor'"),
        sa.Column("tier", sa.String(10), nullable=False, server_default="'tier_2'"),
        sa.Column("geography_ids", JSONB, server_default="[]"),
        sa.Column("sub_processors", JSONB, server_default="[]"),
        sa.Column("last_assessed", sa.Date),
        sa.Column("assessment_status", sa.String(20), nullable=False, server_default="'not_assessed'"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_third_parties_org_id", "org_third_parties", ["org_id"])

    # ── org_data_tech_profiles ────────────────────────────────────────────
    op.create_table("org_data_tech_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("uses_ai_ml", sa.Boolean, server_default="false"),
        sa.Column("ai_use_cases", JSONB, server_default="[]"),
        sa.Column("cloud_providers", JSONB, server_default="[]"),
        sa.Column("data_residency_requirements", JSONB, server_default="[]"),
        sa.Column("handles_personal_data", sa.Boolean, server_default="false"),
        sa.Column("handles_sensitive_personal_data", sa.Boolean, server_default="false"),
        sa.Column("handles_payment_data", sa.Boolean, server_default="false"),
        sa.Column("handles_health_data", sa.Boolean, server_default="false"),
        sa.Column("handles_classified_data", sa.Boolean, server_default="false"),
        sa.Column("core_tech_stack", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_data_tech_org_id", "org_data_tech_profiles", ["org_id"])

    # ── profile_change_logs ───────────────────────────────────────────────
    op.create_table("profile_change_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("changed_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True)),
        sa.Column("field_changed", sa.String(100)),
        sa.Column("old_value", JSONB),
        sa.Column("new_value", JSONB),
        sa.Column("change_summary", sa.Text),
        sa.Column("propagation_status", sa.String(20), server_default="'pending'"),
        sa.Column("affected_modules", JSONB, server_default="[]"),
        sa.Column("propagation_result", JSONB, server_default="{}"),
    )
    op.create_index("ix_change_log_org_id", "profile_change_logs", ["org_id"])
    op.create_index("ix_change_log_changed_at", "profile_change_logs", ["org_id", "changed_at"])


def downgrade():
    op.drop_table("profile_change_logs")
    op.drop_table("org_data_tech_profiles")
    op.drop_table("org_third_parties")
    op.drop_table("org_customer_segments")
    op.drop_table("org_products")
    op.drop_table("org_industries")
    op.drop_table("org_geographies")
    op.drop_table("lines_of_business")
    op.drop_table("org_profiles")
