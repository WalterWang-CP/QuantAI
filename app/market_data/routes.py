import uuid
from typing import Annotated

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