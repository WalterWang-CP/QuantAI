"""Add versioned SEC market-cap calculations.
Revision ID: 8c3f1a6e9b42
Revises: 7a2d6f9c4e81
"""
from alembic import op
import sqlalchemy as sa
revision = "8c3f1a6e9b42"
down_revision = "7a2d6f9c4e81"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("sec_market_cap_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("valuation_date", sa.Date(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.UniqueConstraint("listing_id", "valuation_date", "input_hash", name="uq_sec_market_cap_inputs"),
    )
    for column in ("listing_id", "company_id", "valuation_date"):
        op.create_index("ix_sec_market_cap_snapshots_" + column, "sec_market_cap_snapshots", [column])


def downgrade():
    for column in ("listing_id", "company_id", "valuation_date"):
        op.drop_index("ix_sec_market_cap_snapshots_" + column, table_name="sec_market_cap_snapshots")
    op.drop_table("sec_market_cap_snapshots")
