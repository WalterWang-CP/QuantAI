from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.corporate_actions.adjustments import (
    build_split_adjusted_prices,
)
from app.db.database import Base
from app.db.models.corporate_actions import (
    StockSplit,
)
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
from app.providers.alpha_vantage import (
    AlphaVantageProvider,
)
from app.providers.base import (
    RawProviderResponse,
)

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.corporate_actions.adjustments import (
    build_split_adjusted_prices,
)
from app.db.database import Base
from app.db.models.corporate_actions import (
    StockSplit,
)
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
from app.providers.alpha_vantage import (
    AlphaVantageProvider,
)
from app.providers.base import (
    RawProviderResponse,
)

def test_parse_split_events():
    provider = AlphaVantageProvider()

    response = RawProviderResponse(
        body=b"""
        {
          "symbol": "TEST",
          "data": [
            {
              "effective_date": "2024-06-10",
              "split_factor": "10.0"
            },
            {
              "effective_date": "2021-07-20",
              "split_factor": "4.0"
            }
          ]
        }
        """,
        content_type="application/json",
    )

    events = provider.parse_splits(
        response
    )

    assert len(events) == 2

    assert (
        events[0].effective_date
        == date(
            2021,
            7,
            20,
        )
    )

    assert (
        events[0].split_factor
        == Decimal("4.0")
    )

def test_parse_dividend_events():
    provider = AlphaVantageProvider()

    response = RawProviderResponse(
        body=b"""
        {
        "symbol": "TEST",
        "data": [
            {
            "ex_dividend_date": "2024-05-09",
            "declaration_date": "2024-04-30",
            "record_date": "2024-05-10",
            "payment_date": "2024-06-10",
            "amount": "1.67"
            }
        ]
        }
        """,
        content_type="application/json",
    )

    events = provider.parse_dividends(
        response
    )

    assert len(events) == 1

    event = events[0]

    assert (
        event.ex_dividend_date
        == date(
            2024,
            5,
            9,
        )
    )

    assert (
        event.amount
        == Decimal("1.67")
    )

    assert (
        event.declaration_date
        == date(
            2024,
            4,
            30,
        )
    )

def test_split_adjusted_price_series():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )

    Base.metadata.create_all(
        engine
    )

    database = Session(
        engine
    )

    company = Company(
        legal_name="Synthetic Company",
        country_code="US",
    )

    database.add(company)
    database.flush()

    security = Security(
        company_id=company.id,
        name="Synthetic Stock",
        security_type="common_stock",
        start_date=date(
            2020,
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
            2020,
            1,
            1,
        ),
        is_primary=True,
    )

    database.add(listing)
    database.flush()

    price_source = DataSource(
        provider_name="alpha_vantage",
        dataset_name="TIME_SERIES_DAILY",
    )

    split_source = DataSource(
        provider_name="alpha_vantage",
        dataset_name="SPLITS",
    )

    database.add_all(
        [
            price_source,
            split_source,
        ]
    )

    database.flush()

    price_run = IngestionRun(
        source_id=price_source.id,
        listing_id=listing.id,
        requested_symbol="TEST",
        full_history=False,
        status="completed",
    )

    split_run = IngestionRun(
        source_id=split_source.id,
        listing_id=listing.id,
        requested_symbol="TEST",
        full_history=True,
        status="completed",
    )

    database.add_all(
        [
            price_run,
            split_run,
        ]
    )

    database.flush()

    database.add(
        DailyPriceBar(
            listing_id=listing.id,
            source_id=price_source.id,
            last_ingestion_run_id=
                price_run.id,

            trading_date=date(
                2024,
                6,
                7,
            ),

            open_price=Decimal(
                "400"
            ),

            high_price=Decimal(
                "420"
            ),

            low_price=Decimal(
                "390"
            ),

            close_price=Decimal(
                "400"
            ),

            volume=1000000,
        )
    )

    database.add(
        DailyPriceBar(
            listing_id=listing.id,
            source_id=price_source.id,
            last_ingestion_run_id=
                price_run.id,

            trading_date=date(
                2024,
                6,
                10,
            ),

            open_price=Decimal(
                "100"
            ),

            high_price=Decimal(
                "105"
            ),

            low_price=Decimal(
                "98"
            ),

            close_price=Decimal(
                "100"
            ),

            volume=4000000,
        )
    )

    database.add(
        StockSplit(
            listing_id=listing.id,
            source_id=split_source.id,
            last_ingestion_run_id=
                split_run.id,

            effective_date=date(
                2024,
                6,
                10,
            ),

            split_factor=Decimal(
                "4"
            ),
        )
    )

    database.commit()

    adjusted = (
        build_split_adjusted_prices(
            database=database,
            listing_id=listing.id,
        )
    )

    assert len(adjusted) == 2

    before_split = adjusted[0]

    assert (
        before_split[
            "split_adjustment_factor"
        ]
        == Decimal("4")
    )

    assert (
        before_split[
            "adjusted_close"
        ]
        == Decimal("100")
    )

    assert (
        before_split[
            "adjusted_volume"
        ]
        == Decimal("4000000")
    )

    after_split = adjusted[1]

    assert (
        after_split[
            "split_adjustment_factor"
        ]
        == Decimal("1")
    )

    assert (
        after_split[
            "adjusted_close"
        ]
        == Decimal("100")
    )