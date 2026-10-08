import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.fixture
def migrated_database(monkeypatch):
    path = (
        Path(__file__).resolve().parents[1]
        / "migrations/versions/6d4c9a21e8b7_add_tracking_input_fingerprint.py"
    )
    spec = importlib.util.spec_from_file_location("tracking_input_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        metadata = sa.MetaData()
        old_table = sa.Table(
            "tracking_runs", metadata,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("snapshot_id", sa.String(36), nullable=False),
            sa.Column("policy_hash", sa.String(64), nullable=False),
            sa.Column("engine_version", sa.String(20), nullable=False),
            sa.UniqueConstraint(
                "snapshot_id", "policy_hash", "engine_version",
                name="uq_tracking_run",
            ),
        )
        metadata.create_all(connection)
        connection.execute(old_table.insert(), {
            "id": "old", "snapshot_id": "snapshot", "policy_hash": "policy",
            "engine_version": "1.0",
        })
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        yield connection, migration
    engine.dispose()


def test_migration_preserves_old_run_and_supports_input_versions(migrated_database):
    connection, migration = migrated_database
    assert connection.execute(sa.text(
        "SELECT id, input_hash FROM tracking_runs"
    )).one() == ("old", "legacy")
    connection.execute(sa.text(
        "INSERT INTO tracking_runs "
        "(id, snapshot_id, policy_hash, engine_version, input_hash) "
        "VALUES ('new', 'snapshot', 'policy', '1.0', 'new-inputs')"
    ))
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM tracking_runs")) == 2
    constraints = sa.inspect(connection).get_unique_constraints("tracking_runs")
    assert constraints[0]["column_names"] == [
        "snapshot_id", "policy_hash", "engine_version", "input_hash",
    ]
    connection.execute(sa.text("DELETE FROM tracking_runs WHERE id = 'new'"))
    migration.downgrade()
    assert "input_hash" not in {
        column["name"] for column in sa.inspect(connection).get_columns("tracking_runs")
    }
    assert connection.scalar(sa.text("SELECT id FROM tracking_runs")) == "old"


def test_downgrade_refuses_to_discard_input_versions(migrated_database):
    connection, migration = migrated_database
    connection.execute(sa.text(
        "INSERT INTO tracking_runs "
        "(id, snapshot_id, policy_hash, engine_version, input_hash) "
        "VALUES ('new', 'snapshot', 'policy', '1.0', 'new-inputs')"
    ))
    with pytest.raises(RuntimeError, match="multiple input versions"):
        migration.downgrade()
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM tracking_runs")) == 2
    assert "input_hash" in {
        column["name"] for column in sa.inspect(connection).get_columns("tracking_runs")
    }
