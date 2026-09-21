from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models.market_data import (
    DataSource,
)
from app.data_sources.service import (
    get_or_create_data_source,
)
from sqlalchemy import (
    create_engine,
    select,
)

def create_database():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )

    DataSource.__table__.create(
        engine
    )

    return Session(engine)


def test_get_or_create_data_source_creates_source():
    database = create_database()

    source = get_or_create_data_source(
        database=database,
        provider_name="test_provider",
        dataset_name="TEST_DATASET",
    )

    assert source.id is not None

    assert (
        source.provider_name
        == "test_provider"
    )

    assert (
        source.dataset_name
        == "TEST_DATASET"
    )


def test_get_or_create_data_source_reuses_existing():
    database = create_database()

    first = get_or_create_data_source(
        database=database,
        provider_name="test_provider",
        dataset_name="TEST_DATASET",
    )

    second = get_or_create_data_source(
        database=database,
        provider_name="test_provider",
        dataset_name="TEST_DATASET",
    )

    assert first.id == second.id

    sources = list(
        database.scalars(
            select(DataSource)
        ).all()
    )

    assert len(sources) == 1


def test_different_datasets_create_different_sources():
    database = create_database()

    prices = get_or_create_data_source(
        database=database,
        provider_name="test_provider",
        dataset_name="PRICES",
    )

    shares = get_or_create_data_source(
        database=database,
        provider_name="test_provider",
        dataset_name="SHARES",
    )

    assert prices.id != shares.id