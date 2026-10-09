"""Add audited SEC shares normalization without changing existing observations.

Revision ID: 4e9a2b7c1d63
Revises: 2c8f4a91d7e6
"""
from alembic import op
import sqlalchemy as sa

revision = "4e9a2b7c1d63"
down_revision = "2c8f4a91d7e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("normalized_share_facts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("raw_fact_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("known_date", sa.Date(), nullable=True),
        sa.Column("shares_text", sa.String(26), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("rule_version", sa.String(30), server_default="sec-shares-v1", nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["raw_fact_id"], ["raw_financial_facts.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.UniqueConstraint("raw_fact_id", name="uq_normalized_share_raw_fact"),
        sa.CheckConstraint("status IN ('accepted', 'excluded', 'conflict')", name="ck_normalized_share_status"),
        sa.CheckConstraint("shares_text IS NULL OR CAST(shares_text AS NUMERIC) > 0", name="ck_normalized_share_positive"),
        sa.CheckConstraint("known_date IS NULL OR known_date >= observation_date", name="ck_normalized_share_dates"),
        sa.CheckConstraint("status != 'accepted' OR (shares_text IS NOT NULL AND known_date IS NOT NULL)", name="ck_normalized_share_accepted"),
    )
    op.create_index("ix_normalized_share_facts_company_id", "normalized_share_facts", ["company_id"])
    op.create_index("ix_normalized_share_facts_known_date", "normalized_share_facts", ["known_date"])


def downgrade():
    op.drop_index("ix_normalized_share_facts_known_date", table_name="normalized_share_facts")
    op.drop_index("ix_normalized_share_facts_company_id", table_name="normalized_share_facts")
    op.drop_table("normalized_share_facts")
