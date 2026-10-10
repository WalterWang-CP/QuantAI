import uuid
from typing import Annotated
from datetime import date

import httpx
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.market_data.schemas import (
    DailyPriceBarRead,
    MarketDataImportResult,
)
from app.market_data.service import (
    get_daily_prices_for_listing,
    import_alpha_vantage_daily_prices,
)
from app.market_data.schemas import (
    DailyCoverageRead,
    DailyPriceBarRead,
    DataQualityIssueRead,
    MarketDataImportResult,
    RawDataArtifactRead,
)
from app.market_data.service import (
    get_daily_prices_for_listing,
    get_quality_issues_for_run,
    get_raw_artifact_for_run,
    import_alpha_vantage_daily_prices,
)

from app.calendars.service import (
    UnsupportedExchangeCalendar,
)
from app.market_data.coverage import (
    assess_daily_coverage,
)

router = APIRouter(
    prefix="/market-data",
    tags=["Market Data"],
)


DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]


@router.post(
    "/listings/{listing_id}/daily/import",
    response_model=MarketDataImportResult,
)
def import_daily_prices(
    listing_id: uuid.UUID,
    database: DatabaseSession,
    full_history: bool = False,
    start_date: date | None = None,
    end_date: date | None = None,
):
    try:
        return import_alpha_vantage_daily_prices(
            database=database,
            listing_id=listing_id,
            full_history=full_history,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        )

    except httpx.HTTPError:
        raise HTTPException(
            status_code=502,
            detail=(
                "Unable to communicate "
                "with the market-data provider."
            ),
        )

@router.get(
    "/listings/{listing_id}/coverage",
    response_model=DailyCoverageRead,
)
def read_daily_coverage(
    listing_id: uuid.UUID,
    start_date: date,
    end_date: date,
    database: DatabaseSession,
    provider_name: str =
        "alpha_vantage",
    dataset_name: str =
        "TIME_SERIES_DAILY",
):
    try:
        return assess_daily_coverage(
            database=database,
            listing_id=listing_id,
            provider_name=
                provider_name,
            dataset_name=
                dataset_name,
            start_date=start_date,
            end_date=end_date,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except UnsupportedExchangeCalendar as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        )

@router.get(
    "/listings/{listing_id}/daily",
    response_model=list[DailyPriceBarRead],
)
def read_daily_prices(
    listing_id: uuid.UUID,
    database: DatabaseSession,
):
    try:
        return get_daily_prices_for_listing(
            database=database,
            listing_id=listing_id,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

@router.get(
    "/ingestion-runs/{run_id}/quality-issues",
    response_model=list[DataQualityIssueRead],
)
def read_quality_issues(
    run_id: uuid.UUID,
    database: DatabaseSession,
):
    return get_quality_issues_for_run(
        database=database,
        run_id=run_id,
    )


@router.get(
    "/ingestion-runs/{run_id}/raw-artifact",
    response_model=RawDataArtifactRead,
)
def read_raw_artifact(
    run_id: uuid.UUID,
    database: DatabaseSession,
):
    try:
        return get_raw_artifact_for_run(
            database=database,
            run_id=run_id,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

from fastapi import Query, Response
from sqlalchemy import select
from app.db.models.csv_prices import CSVPriceArtifact
from app.db.models.market_data import DailyPriceBar, DataSource
from app.db.models.identity import Listing
from app.market_data.csv_service import CSVPriceImportRequest, CSVPriceImportResult, CSVPriceConflict, import_raw_price_csv


@router.post("/listings/{listing_id}/daily/import-csv", response_model=CSVPriceImportResult)
def import_daily_price_csv(listing_id: uuid.UUID, payload: CSVPriceImportRequest, database: DatabaseSession):
    try:
        return import_raw_price_csv(database, listing_id, payload)
    except LookupError as error:
        raise HTTPException(404, detail=str(error)) from error
    except CSVPriceConflict as error:
        raise HTTPException(409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(422, detail=str(error)) from error


@router.get("/csv-artifacts/{artifact_id}")
def download_csv_price_artifact(artifact_id: uuid.UUID, database: DatabaseSession):
    artifact = database.get(CSVPriceArtifact, artifact_id)
    if artifact is None:
        raise HTTPException(404, detail="CSV artifact does not exist")
    return Response(content=artifact.body, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{artifact.id}.csv"'})


@router.get("/listings/{listing_id}/price-sources")
def read_listing_price_sources(listing_id: uuid.UUID, database: DatabaseSession):
    if database.get(Listing, listing_id) is None:
        raise HTTPException(404, detail="Listing does not exist")
    ids = select(DailyPriceBar.source_id).where(DailyPriceBar.listing_id == listing_id).distinct()
    return [{"source_id": row.id, "provider_name": row.provider_name, "dataset_name": row.dataset_name}
        for row in database.scalars(select(DataSource).where(DataSource.id.in_(ids)).order_by(DataSource.id))]


@router.get("/listings/{listing_id}/daily/by-source", response_model=list[DailyPriceBarRead])
def read_daily_prices_by_source(listing_id: uuid.UUID, source_id: uuid.UUID, database: DatabaseSession,
                                limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    if database.get(Listing, listing_id) is None:
        raise HTTPException(404, detail="Listing does not exist")
    return list(database.scalars(select(DailyPriceBar).where(DailyPriceBar.listing_id == listing_id,
        DailyPriceBar.source_id == source_id).order_by(DailyPriceBar.trading_date).offset(offset).limit(limit)))
