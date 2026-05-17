"""
db/migrations/003_risk_universe.py
────────────────────────────────────
Risk Universe — adds lob_id, geography_ids, product_ids, segment_ids to risks table.

Run with: alembic upgrade head
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY

revision = "003_risk_universe"
down_revision = "002_company_profile"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("risks",
        sa.Column("lob_id", UUID(as_uuid=True),
                  sa.ForeignKey("lines_of_business.id", ondelete="SET NULL"),
                  nullable=True))
    op.add_column("risks",
        sa.Column("geography_ids", ARRAY(UUID(as_uuid=True)),
                  nullable=False, server_default="{}"))
    op.add_column("risks",
        sa.Column("product_ids", ARRAY(UUID(as_uuid=True)),
                  nullable=False, server_default="{}"))
    op.add_column("risks",
        sa.Column("segment_ids", ARRAY(UUID(as_uuid=True)),
                  nullable=False, server_default="{}"))
    op.create_index("ix_risks_lob_id", "risks", ["lob_id"])


def downgrade():
    op.drop_index("ix_risks_lob_id", "risks")
    op.drop_column("risks", "segment_ids")
    op.drop_column("risks", "product_ids")
    op.drop_column("risks", "geography_ids")
    op.drop_column("risks", "lob_id")
