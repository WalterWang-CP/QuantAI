import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.identity import Listing
from app.db.models.market_data import (
    DailyPriceBar,
    DataSource,
    IngestionRun,
)
from app.providers.alpha_vantage import AlphaVantageProvider


ALPHA_VANTAGE_DAILY_DATASET = "TIME_SERIES_DAILY"


def get_or_create_data_source(
    database: Session,
    provider_name: str,
    dataset_name: str,
) -> DataSource:
    statement = select(DataSource).where(
        DataSource.provider_name == provider_name,
        DataSource.dataset_name == dataset_name,
    )

    source = database.scalar(statement)

    if source is not None:
        return source

    source = DataSource(
        provider_name=provider_name,
        dataset_name=dataset_name,
    )

    database.add(source)
    database.commit()
    database.refresh(source)

    return source


def import_alpha_vantage_daily_prices(
    database: Session,
    listing_id: uuid.UUID,
    full_history: bool,
) -> dict:
    listing = database.get(
        Listing,
        listing_id,
    )

    if listing is None:
        raise LookupError(
            "Listing does not exist."
        )

    provider = AlphaVantageProvider()

    source = get_or_create_data_source(
        database=database,
        provider_name=provider.provider_name,
        dataset_name=ALPHA_VANTAGE_DAILY_DATASET,
    )

    ingestion_run = IngestionRun(
        source_id=source.id,
        listing_id=listing.id,
        requested_symbol=listing.ticker,
        full_history=full_history,
        status="running",
    )

    database.add(ingestion_run)
    database.commit()
    database.refresh(ingestion_run)

    try:
        bars = provider.get_daily_prices(
            symbol=listing.ticker,
            full_history=full_history,
        )

        inserted = 0
        updated = 0

        for bar in bars:
            statement = select(
                DailyPriceBar
            ).where(
                DailyPriceBar.listing_id
                == listing.id,
                DailyPriceBar.source_id
                == source.id,
                DailyPriceBar.trading_date
                == bar.trading_date,
            )

            existing_bar = database.scalar(
                statement
            )

            if existing_bar is None:
                price_bar = DailyPriceBar(
                    listing_id=listing.id,
                    source_id=source.id,
                    last_ingestion_run_id=
                        ingestion_run.id,
                    trading_date=bar.trading_date,
                    open_price=bar.open_price,
                    high_price=bar.high_price,
                    low_price=bar.low_price,
                    close_price=bar.close_price,
                    volume=bar.volume,
                )

                database.add(price_bar)
                inserted += 1

            else:
                existing_bar.open_price = (
                    bar.open_price
                )

                existing_bar.high_price = (
                    bar.high_price
                )

                existing_bar.low_price = (
                    bar.low_price
                )

                existing_bar.close_price = (
                    bar.close_price
                )

                existing_bar.volume = bar.volume

                existing_bar.last_ingestion_run_id = (
                    ingestion_run.id
                )

                updated += 1

        ingestion_run.rows_received = len(
            bars
        )

        ingestion_run.rows_inserted = inserted
        ingestion_run.rows_updated = updated

        ingestion_run.status = "completed"

        ingestion_run.completed_at = (
            datetime.now(timezone.utc)
        )

        database.commit()
        database.refresh(ingestion_run)

        return {
            "ingestion_run_id":
                ingestion_run.id,
            "provider":
                provider.provider_name,
            "dataset":
                ALPHA_VANTAGE_DAILY_DATASET,
            "symbol":
                listing.ticker,
            "status":
                ingestion_run.status,
            "rows_received":
                ingestion_run.rows_received,
            "rows_inserted":
                ingestion_run.rows_inserted,
            "rows_updated":
                ingestion_run.rows_updated,
            "first_date":
                bars[0].trading_date
                if bars
                else None,
            "last_date":
                bars[-1].trading_date
                if bars
                else None,
            "started_at":
                ingestion_run.started_at,
            "completed_at":
                ingestion_run.completed_at,
        }

    except Exception as error:
        database.rollback()

        failed_run = database.get(
            IngestionRun,
            ingestion_run.id,
        )

        if failed_run is not None:
            failed_run.status = "failed"

            failed_run.error_message = str(
                error
            )

            failed_run.completed_at = (
                datetime.now(timezone.utc)
            )

            database.commit()

        raise

def get_daily_prices_for_listing(
    database: Session,
    listing_id: uuid.UUID,
) -> list[DailyPriceBar]:
    listing = database.get(
        Listing,
        listing_id,
    )

    if listing is None:
        raise LookupError(
            "Listing does not exist."
        )

    statement = (
        select(DailyPriceBar)
        .where(
            DailyPriceBar.listing_id
            == listing_id
        )
        .order_by(
            DailyPriceBar.trading_date
        )
    )

    return list(
        database.scalars(
            statement
        ).all()
    )