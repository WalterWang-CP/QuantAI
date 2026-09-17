import uuid
from datetime import date

from sqlalchemy import (
    desc,
    select,
)
from sqlalchemy.orm import Session

from app.db.models.market_data import (
    DailyPriceBar,
    DataSource,
)


def find_historical_close(
    database: Session,
    listing_id: uuid.UUID,
    valuation_date: date,
) -> DailyPriceBar:
    source = database.scalar(
        select(
            DataSource
        ).where(
            DataSource.provider_name
            == "alpha_vantage",

            DataSource.dataset_name
            == "TIME_SERIES_DAILY",
        )
    )

    if source is None:
        raise LookupError(
            "No daily-price data source exists."
        )

    statement = (
        select(
            DailyPriceBar
        )
        .where(
            DailyPriceBar.listing_id
            == listing_id,

            DailyPriceBar.source_id
            == source.id,

            DailyPriceBar.trading_date
            <= valuation_date,
        )
        .order_by(
            desc(
                DailyPriceBar.trading_date
            )
        )
        .limit(1)
    )

    bar = database.scalar(
        statement
    )

    if bar is None:
        raise LookupError(
            "No historical price is available "
            "on or before the valuation date."
        )

    return bar