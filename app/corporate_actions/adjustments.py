import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.corporate_actions import (
    StockSplit,
)
from app.db.models.market_data import (
    DailyPriceBar,
    DataSource,
)


PRICE_PROVIDER = "alpha_vantage"
PRICE_DATASET = "TIME_SERIES_DAILY"

SPLIT_PROVIDER = "alpha_vantage"
SPLIT_DATASET = "SPLITS"


def build_split_adjusted_prices(
    database: Session,
    listing_id: uuid.UUID,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    price_source = database.scalar(
        select(
            DataSource
        ).where(
            DataSource.provider_name
            == PRICE_PROVIDER,

            DataSource.dataset_name
            == PRICE_DATASET,
        )
    )

    if price_source is None:
        return []

    statement = select(
        DailyPriceBar
    ).where(
        DailyPriceBar.listing_id
        == listing_id,

        DailyPriceBar.source_id
        == price_source.id,
    )

    if start_date is not None:
        statement = statement.where(
            DailyPriceBar.trading_date
            >= start_date
        )

    if end_date is not None:
        statement = statement.where(
            DailyPriceBar.trading_date
            <= end_date
        )

    statement = statement.order_by(
        DailyPriceBar.trading_date
    )

    bars = list(
        database.scalars(
            statement
        ).all()
    )

    split_source = database.scalar(
        select(
            DataSource
        ).where(
            DataSource.provider_name
            == SPLIT_PROVIDER,

            DataSource.dataset_name
            == SPLIT_DATASET,
        )
    )

    if split_source is None:
        splits = []

    else:
        splits = list(
            database.scalars(
                select(
                    StockSplit
                )
                .where(
                    StockSplit.listing_id
                    == listing_id,

                    StockSplit.source_id
                    == split_source.id,
                )
                .order_by(
                    StockSplit.effective_date
                )
            ).all()
        )

    result = []

    for bar in bars:
        adjustment_factor = Decimal(
            "1"
        )

        for split in splits:
            if (
                split.effective_date
                > bar.trading_date
            ):
                adjustment_factor *= (
                    split.split_factor
                )

        adjusted_open = (
            bar.open_price
            / adjustment_factor
        )

        adjusted_high = (
            bar.high_price
            / adjustment_factor
        )

        adjusted_low = (
            bar.low_price
            / adjustment_factor
        )

        adjusted_close = (
            bar.close_price
            / adjustment_factor
        )

        adjusted_volume = (
            Decimal(
                bar.volume
            )
            * adjustment_factor
        )

        result.append(
            {
                "trading_date":
                    bar.trading_date,

                "raw_open":
                    bar.open_price,

                "raw_high":
                    bar.high_price,

                "raw_low":
                    bar.low_price,

                "raw_close":
                    bar.close_price,

                "raw_volume":
                    bar.volume,

                "split_adjustment_factor":
                    adjustment_factor,

                "adjusted_open":
                    adjusted_open,

                "adjusted_high":
                    adjusted_high,

                "adjusted_low":
                    adjusted_low,

                "adjusted_close":
                    adjusted_close,

                "adjusted_volume":
                    adjusted_volume,
            }
        )

    return result