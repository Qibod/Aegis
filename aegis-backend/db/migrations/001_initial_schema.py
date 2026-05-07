"""
db/migrations/001_initial_schema.py
─────────────────────────────────────
Initial Alembic migration — creates all Aegis tables.
Run with: alembic upgrade head
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Enable pgvector and uuid-ossp extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── organizations ─────────────────────────────────────────────────────
    op.create_table("organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("industry_code", sa.String(20)),
        sa.Column("industry_label", sa.String(255)),
        sa.Column("jurisdiction", sa.String(100)),
        sa.Column("regulator", sa.String(100)),
        sa.Column("employee_range", sa.String(50)),
        sa.Column("fingerprint_data", JSONB, server_default="{}"),
        sa.Column("onboarding_complete", sa.Boolean, server_default="false"),
        sa.Column("fingerprinted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    # ── users ─────────────────────────────────────────────────────────────
    op.create_table("users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("initials", sa.String(4)),
        sa.Column("avatar_color", sa.String(7), server_default="'#6c63ff'"),
        sa.Column("role", sa.String(50), nullable=False, server_default="'auditor'"),
        sa.Column("hashed_password", sa.String(255)),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_users_org_id", "users", ["org_id"])
    op.create_unique_constraint("uq_user_org_email", "users", ["org_id", "email"])

    # ── risks ─────────────────────────────────────────────────────────────
    op.create_table("risks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("domain", sa.String(100)),
        sa.Column("inherent_severity", sa.String(20), server_default="'medium'", nullable=False),
        sa.Column("residual_severity", sa.String(20), server_default="'medium'", nullable=False),
        sa.Column("likelihood", sa.Integer, server_default="3"),
        sa.Column("impact", sa.Integer, server_default="3"),
        sa.Column("velocity", sa.String(50)),
        sa.Column("control_coverage_pct", sa.Float, server_default="0.0"),
        sa.Column("ai_assessment", JSONB, server_default="{}"),
        sa.Column("framework_tags", JSONB, server_default="[]"),
        sa.Column("ai_seeded", sa.Boolean, server_default="false"),
        sa.Column("embedding", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_risks_org_id", "risks", ["org_id"])
    op.create_index("ix_risks_org_severity", "risks", ["org_id", "inherent_severity"])

    # ── controls ──────────────────────────────────────────────────────────
    op.create_table("controls",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("domain", sa.String(100)),
        sa.Column("control_type", sa.String(30), server_default="'manual'"),
        sa.Column("status", sa.String(30), server_default="'not_tested'"),
        sa.Column("last_tested_at", sa.DateTime(timezone=True)),
        sa.Column("test_frequency_days", sa.Integer, server_default="90"),
        sa.Column("next_test_due", sa.DateTime(timezone=True)),
        sa.Column("integration_source", sa.String(100)),
        sa.Column("integration_config", JSONB, server_default="{}"),
        sa.Column("framework_tags", JSONB, server_default="[]"),
        sa.Column("ai_seeded", sa.Boolean, server_default="false"),
        sa.Column("embedding", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_controls_org_id", "controls", ["org_id"])

    # ── canvas_nodes ──────────────────────────────────────────────────────
    op.create_table("canvas_nodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_type", sa.String(20), nullable=False),
        sa.Column("risk_id", UUID(as_uuid=True), sa.ForeignKey("risks.id", ondelete="CASCADE")),
        sa.Column("control_id", UUID(as_uuid=True), sa.ForeignKey("controls.id", ondelete="CASCADE")),
        sa.Column("pos_x", sa.Float, server_default="0.0", nullable=False),
        sa.Column("pos_y", sa.Float, server_default="0.0", nullable=False),
        sa.Column("label", sa.String(255)),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("is_orphan", sa.Boolean, server_default="false"),
        sa.Column("ai_gap_flag", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_canvas_nodes_org_id", "canvas_nodes", ["org_id"])

    # ── canvas_edges ──────────────────────────────────────────────────────
    op.create_table("canvas_edges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_node_id", UUID(as_uuid=True), sa.ForeignKey("canvas_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_node_id", UUID(as_uuid=True), sa.ForeignKey("canvas_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("edge_type", sa.String(30), server_default="'mitigates'", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_unique_constraint("uq_canvas_edge", "canvas_edges", ["from_node_id", "to_node_id", "edge_type"])

    # ── evidence ──────────────────────────────────────────────────────────
    op.create_table("evidence",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("control_id", UUID(as_uuid=True), sa.ForeignKey("controls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("file_key", sa.String(500)),
        sa.Column("file_size_bytes", sa.Integer),
        sa.Column("mime_type", sa.String(100)),
        sa.Column("period_start", sa.DateTime(timezone=True)),
        sa.Column("period_end", sa.DateTime(timezone=True)),
        sa.Column("age_days", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # ── audit_plans ───────────────────────────────────────────────────────
    op.create_table("audit_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(30), server_default="'planning'"),
        sa.Column("planned_start", sa.DateTime(timezone=True)),
        sa.Column("planned_end", sa.DateTime(timezone=True)),
        sa.Column("actual_start", sa.DateTime(timezone=True)),
        sa.Column("actual_end", sa.DateTime(timezone=True)),
        sa.Column("ai_plan_data", JSONB, server_default="{}"),
        sa.Column("scope_risk_ids", JSONB, server_default="[]"),
        sa.Column("task_count", sa.Integer, server_default="0"),
        sa.Column("done_count", sa.Integer, server_default="0"),
        sa.Column("progress_pct", sa.Float, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # ── audit_tasks ───────────────────────────────────────────────────────
    op.create_table("audit_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("plan_id", UUID(as_uuid=True), sa.ForeignKey("audit_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assignee_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("phase", sa.Integer, server_default="1", nullable=False),
        sa.Column("phase_label", sa.String(100)),
        sa.Column("label", sa.String(500), nullable=False),
        sa.Column("status", sa.String(30), server_default="'pending'"),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        sa.Column("is_priority", sa.Boolean, server_default="false"),
        sa.Column("due_date", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # ── signals ───────────────────────────────────────────────────────────
    op.create_table("signals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text),
        sa.Column("external_url", sa.String(1000)),
        sa.Column("external_id", sa.String(255)),
        sa.Column("tags", JSONB, server_default="[]"),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("relevance_score", sa.Float, server_default="0.0"),
        sa.Column("is_surfaced", sa.Boolean, server_default="false"),
        sa.Column("impacted_control_ids", JSONB, server_default="[]"),
        sa.Column("impacted_risk_ids", JSONB, server_default="[]"),
        sa.Column("ai_recommendation", sa.Text),
        sa.Column("is_new", sa.Boolean, server_default="true"),
        sa.Column("dismissed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_signals_org_surfaced", "signals", ["org_id", "is_surfaced", "severity"])
    op.create_unique_constraint("uq_signal_source_external", "signals", ["org_id", "source", "external_id"])

    # ── control_checks ────────────────────────────────────────────────────
    op.create_table("control_checks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("control_id", UUID(as_uuid=True), sa.ForeignKey("controls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("metrics", JSONB, server_default="{}"),
        sa.Column("raw_response", JSONB),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_control_checks_control_time", "control_checks", ["control_id", "checked_at"])

    # ── frameworks ────────────────────────────────────────────────────────
    op.create_table("frameworks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("coverage_pct", sa.Float, server_default="0.0"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("ai_seeded", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_unique_constraint("uq_framework_org_code", "frameworks", ["org_id", "code"])

    # ── Row-level security (production) ───────────────────────────────────
    # Enable RLS on all org-scoped tables for defense in depth
    for table in ["risks", "controls", "canvas_nodes", "canvas_edges",
                  "evidence", "audit_plans", "audit_tasks",
                  "signals", "control_checks", "frameworks"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade():
    tables = [
        "frameworks", "control_checks", "signals", "audit_tasks",
        "audit_plans", "evidence", "canvas_edges", "canvas_nodes",
        "controls", "risks", "users", "organizations",
    ]
    for table in tables:
        op.drop_table(table)
