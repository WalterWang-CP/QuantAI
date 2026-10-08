"""Add tracking input fingerprints without replacing historical runs.

Revision ID: 6d4c9a21e8b7
Revises: 078715b21fb3
"""
from alembic import op
import sqlalchemy as sa

revision = "6d4c9a21e8b7"
down_revision = "078715b21fb3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tracking_runs") as batch:
        batch.add_column(sa.Column(
            "input_hash", sa.String(64), nullable=False, server_default="legacy",
        ))
        batch.drop_constraint("uq_tracking_run", type_="unique")
        batch.create_unique_constraint(
            "uq_tracking_run_inputs",
            ["snapshot_id", "policy_hash", "engine_version", "input_hash"],
        )


def downgrade() -> None:
    duplicate = op.get_bind().execute(sa.text(
        "SELECT 1 FROM tracking_runs "
        "GROUP BY snapshot_id, policy_hash, engine_version "
        "HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot downgrade: multiple input versions exist for a tracking run. "
            "Downgrade would remove their identity; no rows have been deleted."
        )
    with op.batch_alter_table("tracking_runs") as batch:
        batch.drop_constraint("uq_tracking_run_inputs", type_="unique")
        batch.drop_column("input_hash")
        batch.create_unique_constraint(
            "uq_tracking_run", ["snapshot_id", "policy_hash", "engine_version"],
        )
