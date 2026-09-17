from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.calendars.service import (
    get_expected_sessions,
)
from app.db.database import Base
from app.db.models.identity import (
    Company,
    Listing,
    Security,
)
from app.db.models.market_data import (
    DailyPriceBar,
    DataSource,
    IngestionRun,
)
from app.market_data.coverage import (
    assess_daily_coverage,
)
from app.retrieval.service import (
    requires_full_history,
)


def create_database():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )

    Base.metadata.create_all(
        engine
    )

    return Session(engine)


def create_listing(
    database: Session,
) -> Listing:
    company = Company(
        legal_name="Test Company",
        country_code="US",
    )

    database.add(company)
    database.flush()

    security = Security(
        company_id=company.id,
        name="Test Common Stock",
        security_type="common_stock",
        start_date=date(
            2000,
            1,
            1,
        ),
    )

    database.add(security)
    database.flush()

    listing = Listing(
        security_id=security.id,
        ticker="TEST",
        exchange_code="NASDAQ",
        currency_code="USD",
        start_date=date(
            2000,
            1,
            1,
        ),
        is_primary=True,
    )

    database.add(listing)
    database.commit()

    return listing


def create_source_and_run(
    database: Session,
    listing: Listing,
):
    source = DataSource(
        provider_name="alpha_vantage",
        dataset_name="TIME_SERIES_DAILY",
    )

    database.add(source)
    database.flush()

    ingestion_run = IngestionRun(
        source_id=source.id,
        listing_id=listing.id,
        requested_symbol="TEST",
        full_history=False,
        status="completed",
    )

    database.add(ingestion_run)
    database.commit()

    return source, ingestion_run


def add_bar(
    database: Session,
    listing: Listing,
    source: DataSource,
    ingestion_run: IngestionRun,
    trading_date: date,
):
    bar = DailyPriceBar(
        listing_id=listing.id,
        source_id=source.id,
        last_ingestion_run_id=
            ingestion_run.id,

        trading_date=trading_date,

        open_price=Decimal(
            "100.00"
        ),

        high_price=Decimal(
            "105.00"
        ),

        low_price=Decimal(
            "99.00"
        ),

        close_price=Decimal(
            "102.00"
        ),

        volume=1000000,
    )

    database.add(bar)
    database.commit()


def test_market_calendar_excludes_holiday():
    sessions = get_expected_sessions(
        exchange_code="NASDAQ",
        start_date=date(
            2024,
            7,
            3,
        ),
        end_date=date(
            2024,
            7,
            8,
        ),
    )

    assert date(
        2024,
        7,
        3,
    ) in sessions

    assert date(
        2024,
        7,
        4,
    ) not in sessions

    assert date(
        2024,
        7,
        5,
    ) in sessions

    assert date(
        2024,
        7,
        6,
    ) not in sessions


def test_coverage_detects_internal_gap():
    database = create_database()

    listing = create_listing(
        database
    )

    source, ingestion_run = (
        create_source_and_run(
            database,
            listing,
        )
    )

    add_bar(
        database,
        listing,
        source,
        ingestion_run,
        date(
            2024,
            7,
            3,
        ),
    )

    add_bar(
        database,
        listing,
        source,
        ingestion_run,
        date(
            2024,
            7,
            8,
        ),
    )

    coverage = assess_daily_coverage(
        database=database,
        listing_id=listing.id,
        provider_name="alpha_vantage",
        dataset_name=
            "TIME_SERIES_DAILY",
        start_date=date(
            2024,
            7,
            3,
        ),
        end_date=date(
            2024,
            7,
            8,
        ),
    )

    assert (
        coverage.expected_session_count
        == 3
    )

    assert (
        coverage.stored_session_count
        == 2
    )

    assert (
        coverage.missing_session_count
        == 1
    )

    assert len(
        coverage.gaps
    ) == 1

    assert (
        coverage.gaps[0].start_date
        == date(
            2024,
            7,
            5,
        )
    )


def test_complete_coverage_ignores_closed_days():
    database = create_database()

    listing = create_listing(
        database
    )

    source, ingestion_run = (
        create_source_and_run(
            database,
            listing,
        )
    )

    for trading_date in [
        date(2024, 7, 3),
        date(2024, 7, 5),
        date(2024, 7, 8),
    ]:
        add_bar(
            database,
            listing,
            source,
            ingestion_run,
            trading_date,
        )

    coverage = assess_daily_coverage(
        database=database,
        listing_id=listing.id,
        provider_name="alpha_vantage",
        dataset_name=
            "TIME_SERIES_DAILY",
        start_date=date(
            2024,
            7,
            3,
        ),
        end_date=date(
            2024,
            7,
            8,
        ),
    )

    assert (
        coverage.missing_session_count
        == 0
    )

    assert (
        coverage.coverage_percent
        == 100.0
    )


def test_recent_gap_uses_compact_history():
    full_history = requires_full_history(
        exchange_code="NASDAQ",
        missing_start_date=date(
            2024,
            7,
            5,
        ),
        as_of_date=date(
            2024,
            7,
            10,
        ),
    )

    assert full_history is False


def test_old_gap_requires_full_history():
    full_history = requires_full_history(
        exchange_code="NASDAQ",
        missing_start_date=date(
            2020,
            1,
            2,
        ),
        as_of_date=date(
            2024,
            7,
            10,
        ),
    )

    assert full_history is True