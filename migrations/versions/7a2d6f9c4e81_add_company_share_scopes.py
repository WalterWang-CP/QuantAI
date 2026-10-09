"""Add explicit evidence-backed company shares mappings.

Revision ID: 7a2d6f9c4e81
Revises: 4e9a2b7c1d63
"""
from alembic import op
import sqlalchemy as sa
revision = "7a2d6f9c4e81"
down_revision = "4e9a2b7c1d63"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("company_share_scopes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=False),
        sa.Column("known_date", sa.Date(), nullable=False),
        sa.Column("evidence_url", sa.Text(), nullable=False),
        sa.Column("evidence_note", sa.Text(), nullable=False),
        sa.Column("scope_type", sa.String(30), server_default="single_common_class", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["security_id"], ["securities.id"]),
        sa.UniqueConstraint("company_id", "valid_from", "valid_to", name="uq_company_share_scope_period"),
        sa.CheckConstraint("valid_to >= valid_from", name="ck_share_scope_period"),
        sa.CheckConstraint("known_date >= valid_from", name="ck_share_scope_known_date"),
        sa.CheckConstraint("scope_type = 'single_common_class'", name="ck_share_scope_type"),
    )
    op.create_index("ix_company_share_scopes_company_id", "company_share_scopes", ["company_id"])
    op.create_index("ix_company_share_scopes_security_id", "company_share_scopes", ["security_id"])


def downgrade():
    op.drop_index("ix_company_share_scopes_security_id", table_name="company_share_scopes")
    op.drop_index("ix_company_share_scopes_company_id", table_name="company_share_scopes")
    op.drop_table("company_share_scopes")
