"""Add exact CSV price archives and import declarations.
Revision ID: a6d4e2c8f913
Revises: 8c3f1a6e9b42
"""
from alembic import op
import sqlalchemy as sa
revision = "a6d4e2c8f913"
down_revision = "8c3f1a6e9b42"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("csv_price_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("import_hash", sa.String(64), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("body", sa.LargeBinary(), nullable=False),
        sa.Column("byte_count", sa.Integer(), nullable=False),
        sa.Column("declaration_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["ingestion_run_id"], ["ingestion_runs.id"]),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"]),
        sa.UniqueConstraint("ingestion_run_id"),
        sa.UniqueConstraint("listing_id", "source_id", "import_hash", name="uq_csv_price_import"),
        sa.CheckConstraint("byte_count > 0", name="ck_csv_price_artifact_nonempty"),
    )
    op.create_index("ix_csv_price_artifacts_listing_id", "csv_price_artifacts", ["listing_id"])
    op.create_index("ix_csv_price_artifacts_source_id", "csv_price_artifacts", ["source_id"])


def downgrade():
    op.drop_index("ix_csv_price_artifacts_source_id", table_name="csv_price_artifacts")
    op.drop_index("ix_csv_price_artifacts_listing_id", table_name="csv_price_artifacts")
    op.drop_table("csv_price_artifacts")
