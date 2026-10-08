"""Enforce ranking snapshot status without modifying historical rows.

Revision ID: 9b7e21a4c6d8
Revises: 6d4c9a21e8b7
"""
from alembic import context, op
import sqlalchemy as sa

revision = "9b7e21a4c6d8"
down_revision = "6d4c9a21e8b7"
branch_labels = None
depends_on = None

STATUS_CHECK = "status IN ('legacy', 'draft', 'approved', 'rejected')"


def upgrade() -> None:
    if not context.is_offline_mode():
        invalid = op.get_bind().execute(sa.text(
            "SELECT 1 FROM ranking_snapshots "
            f"WHERE status IS NULL OR NOT ({STATUS_CHECK}) LIMIT 1"
        )).first()
        if invalid is not None:
            raise RuntimeError(
                "Cannot enforce ranking snapshot status: invalid statuses exist. "
                "Review those rows before retrying; no rows have been changed."
            )
    with op.batch_alter_table("ranking_snapshots") as batch:
        batch.create_check_constraint("ck_ranking_snapshot_status", STATUS_CHECK)


def downgrade() -> None:
    with op.batch_alter_table("ranking_snapshots") as batch:
        batch.drop_constraint("ck_ranking_snapshot_status", type_="check")
