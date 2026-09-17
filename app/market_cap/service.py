import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.db.models.identity import (
    Listing,
    Security,
)
from app.db.models.market_cap import (
    MarketCapObservation,
)
from app.market_cap.fx_service import (
    find_fx_rate,
)
from app.market_cap.price_service import (
    find_historical_close,
)
from app.market_cap.shares_service import (
    find_known_shares_outstanding,
)


def reconstruct_market_cap(
    database: Session,
    listing_id: uuid.UUID,
    valuation_date: date,
) -> MarketCapObservation:
    listing = database.get(
        Listing,
        listing_id,
    )

    if listing is None:
        raise LookupError(
            "Listing does not exist."
        )

    if (
    valuation_date
    < listing.start_date
    ):
        raise ValueError(
            "Valuation date is before "
            "the listing start date."
        )

    if (
        listing.end_date is not None
        and valuation_date
        > listing.end_date
    ):
        raise ValueError(
            "Valuation date is after "
            "the listing end date."
        )

    security = database.get(
        Security,
        listing.security_id,
    )

    if security is None:
        raise LookupError(
            "Security does not exist."
        )

    company_id = security.company_id

    existing = database.scalar(
        select(
            MarketCapObservation
        ).where(
            MarketCapObservation.company_id
            == company_id,

            MarketCapObservation.listing_id
            == listing.id,

            MarketCapObservation.valuation_date
            == valuation_date,
        )
    )

    price_bar = find_historical_close(
        database=database,
        listing_id=listing.id,
        valuation_date=valuation_date,
    )

    shares = (
        find_known_shares_outstanding(
            database=database,
            company_id=company_id,
            security_id=security.id,
            valuation_date=valuation_date,
        )
    )

    price = Decimal(
        price_bar.close_price
    )

    share_count = Decimal(
        shares.shares_outstanding
    )

    local_market_cap = (
        price
        * share_count
    )

    fx_rate, fx_record = (
        find_fx_rate(
            database=database,
            from_currency=
                listing.currency_code,
            to_currency="USD",
            as_of_date=
                price_bar.trading_date,
        )
    )

    market_cap_usd = (
        local_market_cap
        * fx_rate
    )

    if existing is None:
        observation = (
            MarketCapObservation(
                company_id=company_id,

                listing_id=listing.id,

                valuation_date=
                    valuation_date,

                price_date=
                    price_bar.trading_date,

                shares_observation_id=
                    shares.id,

                fx_rate_id=(
                    fx_record.id
                    if fx_record
                    is not None
                    else None
                ),

                local_currency=
                    listing.currency_code,

                price=price,

                shares_outstanding=
                    share_count,

                local_market_cap=
                    local_market_cap,

                market_cap_usd=
                    market_cap_usd,
            )
        )

        database.add(
            observation
        )

    else:
        observation = existing

        observation.price_date = (
            price_bar.trading_date
        )

        observation.shares_observation_id = (
            shares.id
        )

        observation.fx_rate_id = (
            fx_record.id
            if fx_record is not None
            else None
        )

        observation.local_currency = (
            listing.currency_code
        )

        observation.price = price

        observation.shares_outstanding = (
            share_count
        )

        observation.local_market_cap = (
            local_market_cap
        )

        observation.market_cap_usd = (
            market_cap_usd
        )

    database.commit()
    database.refresh(
        observation
    )

    return observation

def get_market_cap_history(
    database: Session,
    listing_id: uuid.UUID,
) -> list[MarketCapObservation]:
    statement = (
        select(
            MarketCapObservation
        )
        .where(
            MarketCapObservation.listing_id
            == listing_id
        )
        .order_by(
            MarketCapObservation.valuation_date
        )
    )

    return list(
        database.scalars(
            statement
        ).all()
    )

def reconstruct_market_caps_batch(
    database: Session,
    valuation_date: date,
    listing_ids: list[
        uuid.UUID
    ] | None = None,
    primary_only: bool = True,
    limit: int = 1000,
) -> dict:
    if listing_ids is not None:
        statement = select(
            Listing
        ).where(
            Listing.id.in_(
                listing_ids
            )
        )

        found_listings = list(
            database.scalars(
                statement
            ).all()
        )

        listing_map = {
            listing.id: listing
            for listing
            in found_listings
        }

        targets = [
            listing_map[
                listing_id
            ]
            for listing_id
            in listing_ids
            if listing_id
            in listing_map
        ]

        missing_listing_ids = [
            listing_id
            for listing_id
            in listing_ids
            if listing_id
            not in listing_map
        ]

    else:
        statement = select(
            Listing
        ).where(
            Listing.start_date
            <= valuation_date,

            or_(
                Listing.end_date
                .is_(None),

                Listing.end_date
                >= valuation_date,
            ),
        )

        if primary_only:
            statement = statement.where(
                Listing.is_primary
                .is_(True)
            )

        statement = (
            statement
            .order_by(
                Listing.id
            )
            .limit(limit)
        )

        targets = list(
            database.scalars(
                statement
            ).all()
        )

        missing_listing_ids = []

    items = []

    completed = 0
    failed = 0

    for listing_id in (
        missing_listing_ids
    ):
        items.append(
            {
                "listing_id":
                    listing_id,

                "ticker":
                    "UNKNOWN",

                "status":
                    "failed",

                "observation":
                    None,

                "error_type":
                    "listing_not_found",

                "error_message":
                    "Listing does not exist.",
            }
        )

        failed += 1

    for listing in targets:
        try:
            observation = (
                reconstruct_market_cap(
                    database=database,

                    listing_id=
                        listing.id,

                    valuation_date=
                        valuation_date,
                )
            )

            items.append(
                {
                    "listing_id":
                        listing.id,

                    "ticker":
                        listing.ticker,

                    "status":
                        "completed",

                    "observation":
                        observation,

                    "error_type":
                        None,

                    "error_message":
                        None,
                }
            )

            completed += 1

        except (
            LookupError,
            ValueError,
        ) as error:
            items.append(
                {
                    "listing_id":
                        listing.id,

                    "ticker":
                        listing.ticker,

                    "status":
                        "failed",

                    "observation":
                        None,

                    "error_type":
                        "missing_or_invalid_input",

                    "error_message":
                        str(error),
                }
            )

            failed += 1

    return {
        "valuation_date":
            valuation_date,

        "target_count":
            len(items),

        "completed":
            completed,

        "failed":
            failed,

        "items":
            items,
    }