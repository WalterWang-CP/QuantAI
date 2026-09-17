import uuid
from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.market_cap.manual_service import (
    get_fx_rates,
    get_shares_outstanding_history,
    upsert_fx_rate,
    upsert_shares_outstanding,
)
from app.market_cap.schemas import (
    FxRateCreate,
    FxRateRead,
    MarketCapBatchRequest,
    MarketCapBatchResult,
    MarketCapObservationRead,
    SharesOutstandingCreate,
    SharesOutstandingRead,
)
from app.market_cap.service import (
    get_market_cap_history,
    reconstruct_market_cap,
    reconstruct_market_caps_batch,
)


router = APIRouter(
    prefix="/market-cap",
    tags=["Market Cap"],
)


DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]


@router.post(
    "/manual/shares-outstanding",
    response_model=
        SharesOutstandingRead,
)
def create_manual_shares(
    payload: SharesOutstandingCreate,
    database: DatabaseSession,
):
    try:
        return upsert_shares_outstanding(
            database=database,
            payload=payload,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        )


@router.get(
    "/companies/{company_id}/shares-outstanding",
    response_model=list[
        SharesOutstandingRead
    ],
)
def read_shares_history(
    company_id: uuid.UUID,
    database: DatabaseSession,
):
    return (
        get_shares_outstanding_history(
            database=database,
            company_id=company_id,
        )
    )


@router.post(
    "/manual/fx-rates",
    response_model=FxRateRead,
)
def create_manual_fx_rate(
    payload: FxRateCreate,
    database: DatabaseSession,
):
    return upsert_fx_rate(
        database=database,
        payload=payload,
    )


@router.get(
    "/fx-rates",
    response_model=list[
        FxRateRead
    ],
)
def read_fx_rates(
    database: DatabaseSession,
    base_currency: str | None = None,
    quote_currency: str | None = None,
):
    return get_fx_rates(
        database=database,

        base_currency=
            base_currency,

        quote_currency=
            quote_currency,
    )


@router.post(
    "/listings/{listing_id}/reconstruct",
    response_model=
        MarketCapObservationRead,
)
def reconstruct_listing_market_cap(
    listing_id: uuid.UUID,
    valuation_date: date,
    database: DatabaseSession,
):
    try:
        return reconstruct_market_cap(
            database=database,

            listing_id=listing_id,

            valuation_date=
                valuation_date,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        )


@router.get(
    "/listings/{listing_id}/observations",
    response_model=list[
        MarketCapObservationRead
    ],
)
def read_market_cap_history(
    listing_id: uuid.UUID,
    database: DatabaseSession,
):
    return get_market_cap_history(
        database=database,
        listing_id=listing_id,
    )


@router.post(
    "/reconstruct-batch",
    response_model=
        MarketCapBatchResult,
)
def reconstruct_batch(
    payload: MarketCapBatchRequest,
    database: DatabaseSession,
):
    return reconstruct_market_caps_batch(
        database=database,

        valuation_date=
            payload.valuation_date,

        listing_ids=
            payload.listing_ids,

        primary_only=
            payload.primary_only,

        limit=
            payload.limit,
    )