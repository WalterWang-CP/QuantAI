import uuid
from datetime import (
    datetime,
    timezone,
)

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.corporate_actions import (
    Dividend,
    StockSplit,
)
from app.db.models.identity import (
    Listing,
)
from app.db.models.market_data import (
    DataSource,
    IngestionRun,
    RawDataArtifact,
)
from app.market_data.raw_archive import (
    archive_raw_response,
)
from app.market_data.service import (
    get_or_create_data_source,
)
from app.providers.alpha_vantage import (
    AlphaVantageProvider,
)


SPLITS_DATASET = "SPLITS"

DIVIDENDS_DATASET = "DIVIDENDS"


def import_alpha_vantage_splits(
    database: Session,
    listing_id: uuid.UUID,
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
        provider_name=
            provider.provider_name,
        dataset_name=
            SPLITS_DATASET,
    )

    ingestion_run = IngestionRun(
        source_id=source.id,
        listing_id=listing.id,
        requested_symbol=listing.ticker,
        full_history=True,
        status="running",
    )

    database.add(
        ingestion_run
    )

    database.commit()
    database.refresh(
        ingestion_run
    )

    try:
        raw_response = (
            provider.fetch_splits_response(
                listing.ticker
            )
        )

        archive = archive_raw_response(
            ingestion_run_id=
                ingestion_run.id,

            provider_name=
                provider.provider_name,

            dataset_name=
                SPLITS_DATASET,

            symbol=
                listing.ticker,

            body=
                raw_response.body,
        )

        raw_artifact = RawDataArtifact(
            ingestion_run_id=
                ingestion_run.id,

            source_id=
                source.id,

            listing_id=
                listing.id,

            storage_path=
                archive[
                    "storage_path"
                ],

            sha256=
                archive["sha256"],

            content_type=
                raw_response.content_type,

            byte_count=
                archive["byte_count"],
        )

        database.add(
            raw_artifact
        )

        database.commit()
        database.refresh(
            raw_artifact
        )

        events = provider.parse_splits(
            raw_response
        )

        inserted = 0
        updated = 0

        for event in events:
            statement = select(
                StockSplit
            ).where(
                StockSplit.listing_id
                == listing.id,

                StockSplit.source_id
                == source.id,

                StockSplit.effective_date
                == event.effective_date,
            )

            existing = database.scalar(
                statement
            )

            if existing is None:
                split = StockSplit(
                    listing_id=
                        listing.id,

                    source_id=
                        source.id,

                    last_ingestion_run_id=
                        ingestion_run.id,

                    effective_date=
                        event.effective_date,

                    split_factor=
                        event.split_factor,
                )

                database.add(
                    split
                )

                inserted += 1

            else:
                existing.split_factor = (
                    event.split_factor
                )

                existing.last_ingestion_run_id = (
                    ingestion_run.id
                )

                updated += 1

        ingestion_run.rows_received = len(
            events
        )

        ingestion_run.rows_inserted = (
            inserted
        )

        ingestion_run.rows_updated = (
            updated
        )

        ingestion_run.status = (
            "completed"
        )

        ingestion_run.completed_at = (
            datetime.now(
                timezone.utc
            )
        )

        database.commit()
        database.refresh(
            ingestion_run
        )

        return {
            "ingestion_run_id":
                ingestion_run.id,

            "raw_artifact_id":
                raw_artifact.id,

            "provider":
                provider.provider_name,

            "dataset":
                SPLITS_DATASET,

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
                datetime.now(
                    timezone.utc
                )
            )

            database.commit()

        raise

def import_alpha_vantage_dividends(
database: Session,
listing_id: uuid.UUID,
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
        provider_name=
            provider.provider_name,
        dataset_name=
            DIVIDENDS_DATASET,
    )

    ingestion_run = IngestionRun(
        source_id=source.id,
        listing_id=listing.id,
        requested_symbol=listing.ticker,
        full_history=True,
        status="running",
    )

    database.add(
        ingestion_run
    )

    database.commit()
    database.refresh(
        ingestion_run
    )

    try:
        raw_response = (
            provider.fetch_dividends_response(
                listing.ticker
            )
        )

        archive = archive_raw_response(
            ingestion_run_id=
                ingestion_run.id,

            provider_name=
                provider.provider_name,

            dataset_name=
                DIVIDENDS_DATASET,

            symbol=
                listing.ticker,

            body=
                raw_response.body,
        )

        raw_artifact = RawDataArtifact(
            ingestion_run_id=
                ingestion_run.id,

            source_id=
                source.id,

            listing_id=
                listing.id,

            storage_path=
                archive[
                    "storage_path"
                ],

            sha256=
                archive["sha256"],

            content_type=
                raw_response.content_type,

            byte_count=
                archive["byte_count"],
        )

        database.add(
            raw_artifact
        )

        database.commit()
        database.refresh(
            raw_artifact
        )

        events = provider.parse_dividends(
            raw_response
        )

        inserted = 0
        updated = 0

        for event in events:
            statement = select(
                Dividend
            ).where(
                Dividend.listing_id
                == listing.id,

                Dividend.source_id
                == source.id,

                Dividend.ex_dividend_date
                == event.ex_dividend_date,

                Dividend.amount
                == event.amount,
            )

            existing = database.scalar(
                statement
            )

            if existing is None:
                dividend = Dividend(
                    listing_id=
                        listing.id,

                    source_id=
                        source.id,

                    last_ingestion_run_id=
                        ingestion_run.id,

                    ex_dividend_date=
                        event.ex_dividend_date,

                    declaration_date=
                        event.declaration_date,

                    record_date=
                        event.record_date,

                    payment_date=
                        event.payment_date,

                    amount=
                        event.amount,

                    currency_code=None,
                )

                database.add(
                    dividend
                )

                inserted += 1

            else:
                existing.declaration_date = (
                    event.declaration_date
                )

                existing.record_date = (
                    event.record_date
                )

                existing.payment_date = (
                    event.payment_date
                )

                existing.last_ingestion_run_id = (
                    ingestion_run.id
                )

                updated += 1

        ingestion_run.rows_received = len(
            events
        )

        ingestion_run.rows_inserted = (
            inserted
        )

        ingestion_run.rows_updated = (
            updated
        )

        ingestion_run.status = (
            "completed"
        )

        ingestion_run.completed_at = (
            datetime.now(
                timezone.utc
            )
        )

        database.commit()
        database.refresh(
            ingestion_run
        )

        return {
            "ingestion_run_id":
                ingestion_run.id,

            "raw_artifact_id":
                raw_artifact.id,

            "provider":
                provider.provider_name,

            "dataset":
                DIVIDENDS_DATASET,

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
                datetime.now(
                    timezone.utc
                )
            )

            database.commit()

        raise