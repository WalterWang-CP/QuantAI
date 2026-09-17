import uuid
from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session

from app.corporate_actions.adjustments import (
    build_split_adjusted_prices,
)
from app.corporate_actions.schemas import (
    CorporateActionImportResult,
    DividendRead,
    SplitAdjustedPriceBarRead,
    StockSplitRead,
)
from app.corporate_actions.service import (
    get_dividends_for_listing,
    get_splits_for_listing,
    import_alpha_vantage_dividends,
    import_alpha_vantage_splits,
)
from app.db.database import get_db
from app.providers.errors import (
    ProviderError,
)


router = APIRouter(
    prefix="/corporate-actions",
    tags=["Corporate Actions"],
)


DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]


@router.post(
    "/listings/{listing_id}/splits/import",
    response_model=CorporateActionImportResult,
)
def import_splits(
    listing_id: uuid.UUID,
    database: DatabaseSession,
):
    try:
        return import_alpha_vantage_splits(
            database=database,
            listing_id=listing_id,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except ProviderError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        )


@router.post(
    "/listings/{listing_id}/dividends/import",
    response_model=CorporateActionImportResult,
)
def import_dividends(
    listing_id: uuid.UUID,
    database: DatabaseSession,
):
    try:
        return import_alpha_vantage_dividends(
            database=database,
            listing_id=listing_id,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except ProviderError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        )


@router.get(
    "/listings/{listing_id}/splits",
    response_model=list[StockSplitRead],
)
def read_splits(
    listing_id: uuid.UUID,
    database: DatabaseSession,
):
    return get_splits_for_listing(
        database=database,
        listing_id=listing_id,
    )


@router.get(
    "/listings/{listing_id}/dividends",
    response_model=list[DividendRead],
)
def read_dividends(
    listing_id: uuid.UUID,
    database: DatabaseSession,
):
    return get_dividends_for_listing(
        database=database,
        listing_id=listing_id,
    )


@router.get(
    "/listings/{listing_id}/split-adjusted-daily",
    response_model=list[SplitAdjustedPriceBarRead],
)
def read_split_adjusted_prices(
    listing_id: uuid.UUID,
    database: DatabaseSession,
    start_date: date | None = None,
    end_date: date | None = None,
):
    return build_split_adjusted_prices(
        database=database,
        listing_id=listing_id,
        start_date=start_date,
        end_date=end_date,
    )