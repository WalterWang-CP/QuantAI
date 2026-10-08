import importlib.util
import os
import uuid
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from app.db.database import Base
from app.db.models.universe import RankingSnapshot

ROOT = Path(__file__).resolve().parents[1]
HEAD = "2c8f4a91d7e6"
PREVIOUS = "6d4c9a21e8b7"


def migration_config():
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return config


def test_migration_chain_has_one_expected_head():
    scripts = ScriptDirectory.from_config(migration_config())
    assert scripts.get_heads() == [HEAD]
    assert scripts.get_revision(HEAD).down_revision == "9b7e21a4c6d8"
    revisions = list(scripts.walk_revisions())
    assert sum(revision.down_revision is None for revision in revisions) == 1


@pytest.mark.parametrize("status", ["legacy", "draft", "approved", "rejected"])
def test_metadata_accepts_supported_ranking_status(status):
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    try:
        RankingSnapshot.__table__.create(engine)
        with engine.begin() as connection:
            connection.execute(RankingSnapshot.__table__.insert(), {
                "id": uuid.uuid4(), "ranking_date": date(2020, 1, 1),
                "effective_date": date(2020, 1, 1), "status": status,
            })
    finally:
        engine.dispose()


def test_metadata_rejects_invalid_ranking_status():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    try:
        RankingSnapshot.__table__.create(engine)
        with engine.begin() as connection:
            with pytest.raises(sa.exc.IntegrityError):
                connection.execute(RankingSnapshot.__table__.insert(), {
                    "id": uuid.uuid4(), "ranking_date": date(2020, 1, 1),
                    "effective_date": date(2020, 1, 1), "status": "typo",
                })
    finally:
        engine.dispose()


@pytest.fixture
def status_migration(monkeypatch):
    path = ROOT / "migrations/versions/9b7e21a4c6d8_enforce_ranking_snapshot_status.py"
    spec = importlib.util.spec_from_file_location("snapshot_status_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(sa.text(
            "CREATE TABLE ranking_snapshots "
            "(id INTEGER PRIMARY KEY, status VARCHAR(20) NOT NULL)"
        ))
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        monkeypatch.setattr(migration.context, "is_offline_mode", lambda: False)
        yield connection, migration
    engine.dispose()


def test_status_migration_preserves_rows_and_can_downgrade(status_migration):
    connection, migration = status_migration
    connection.execute(sa.text("INSERT INTO ranking_snapshots VALUES (1, 'approved')"))
    migration.upgrade()
    assert connection.execute(sa.text("SELECT * FROM ranking_snapshots")).one() == (1, "approved")
    assert "ck_ranking_snapshot_status" in {
        item["name"] for item in sa.inspect(connection).get_check_constraints("ranking_snapshots")
    }
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(sa.text("INSERT INTO ranking_snapshots VALUES (2, 'typo')"))
    migration.downgrade()
    connection.execute(sa.text("INSERT INTO ranking_snapshots VALUES (2, 'typo')"))
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM ranking_snapshots")) == 2


def test_status_migration_refuses_invalid_existing_rows(status_migration):
    connection, migration = status_migration
    connection.execute(sa.text("INSERT INTO ranking_snapshots VALUES (1, 'typo')"))
    with pytest.raises(RuntimeError, match="invalid statuses"):
        migration.upgrade()
    assert connection.execute(sa.text("SELECT * FROM ranking_snapshots")).one() == (1, "typo")
    assert not sa.inspect(connection).get_check_constraints("ranking_snapshots")


@pytest.fixture
def postgres_migrations():
    database_url = os.environ.get("QUANTAI_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set QUANTAI_TEST_DATABASE_URL to enable PostgreSQL migration tests")
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail("QUANTAI_TEST_DATABASE_URL must use PostgreSQL")
    engine = sa.create_engine(url.set(drivername="postgresql+psycopg"))
    schema = "quantai_migration_test_" + uuid.uuid4().hex
    created = False
    try:
        with engine.begin() as connection:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        created = True
        with engine.begin() as connection:
            connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            # Alembic's default-schema inspection must follow this search path.
            engine.dialect.default_schema_name = schema
            config = migration_config()
            config.attributes["connection"] = connection
            yield connection, config
    finally:
        if created:
            with engine.begin() as connection:
                connection.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def test_postgres_fresh_migrations_match_models_and_round_trip(postgres_migrations):
    connection, config = postgres_migrations
    command.upgrade(config, "head")
    assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == HEAD
    assert set(sa.inspect(connection).get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
    command.check(config)
    assert "ck_ranking_snapshot_status" in {
        item["name"] for item in sa.inspect(connection).get_check_constraints("ranking_snapshots")
    }
    command.downgrade(config, "base")
    assert sa.inspect(connection).get_table_names() == ["alembic_version"]
    command.upgrade(config, "head")
    command.check(config)


def test_postgres_status_upgrade_preserves_historical_snapshot(postgres_migrations):
    connection, config = postgres_migrations
    command.upgrade(config, PREVIOUS)
    snapshot_id = uuid.uuid4()
    connection.execute(sa.text(
        "INSERT INTO ranking_snapshots "
        "(id, ranking_date, effective_date, ranking_metric, base_currency, status) "
        "VALUES (:id, '2020-01-01', '2020-01-01', 'market_cap_usd', 'USD', 'approved')"
    ), {"id": snapshot_id})
    command.upgrade(config, "head")
    assert connection.scalar(sa.text(
        "SELECT status FROM ranking_snapshots WHERE id = :id"
    ), {"id": snapshot_id}) == "approved"
    with pytest.raises(sa.exc.IntegrityError):
        with connection.begin_nested():
            connection.execute(sa.text(
                "UPDATE ranking_snapshots SET status = 'typo' WHERE id = :id"
            ), {"id": snapshot_id})
    command.downgrade(config, PREVIOUS)
    assert connection.scalar(sa.text("SELECT COUNT(*) FROM ranking_snapshots")) == 1
    command.upgrade(config, "head")
