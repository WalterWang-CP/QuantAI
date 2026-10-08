import uuid
from datetime import date
from decimal import Decimal, localcontext

from sqlalchemy import (
    desc,
    select,
)
from sqlalchemy.orm import Session

from app.db.models.corporate_actions import StockSplit
from app.db.models.fundamentals import (
    SharesOutstandingObservation,
)


def find_known_shares_outstanding(
    database: Session,
    company_id: uuid.UUID,
    valuation_date: date,
    security_id: uuid.UUID | None = None,
) -> SharesOutstandingObservation:
    statement = (
        select(
            SharesOutstandingObservation
        )
        .where(
            SharesOutstandingObservation.company_id
            == company_id,

            SharesOutstandingObservation.known_date
            <= valuation_date,

            SharesOutstandingObservation.observation_date
            <= valuation_date,
        )
    )

    if security_id is not None:
        statement = statement.where(
            (
                SharesOutstandingObservation
                .security_id
                == security_id
            )
            | (
                SharesOutstandingObservation
                .security_id
                .is_(None)
            )
        )

    statement = (
        statement
        .order_by(
            desc(
                SharesOutstandingObservation
                .observation_date
            ),

            desc(
                SharesOutstandingObservation
                .known_date
            ),
        )
        .limit(1)
    )

    observation = database.scalar(
        statement
    )

    if observation is None:
        raise LookupError(
            "No point-in-time shares "
            "outstanding observation is "
            "available for this company."
        )

    return observation


def adjust_shares_to_price_date(
    database: Session,
    observation: SharesOutstandingObservation,
    listing_id: uuid.UUID,
    price_date: date,
) -> Decimal:
    """Map observed shares to the selected raw close's split basis.

    Observations and prices dated on a split's effective date are treated
    as post-split. Source observations are never modified.
    """
    share_count = Decimal(observation.shares_outstanding)
    if observation.observation_date == price_date:
        return share_count

    start_date = min(observation.observation_date, price_date)
    end_date = max(observation.observation_date, price_date)
    splits = database.scalars(
        select(StockSplit)
        .where(
            StockSplit.listing_id == listing_id,
            StockSplit.effective_date > start_date,
            StockSplit.effective_date <= end_date,
        )
        .order_by(StockSplit.effective_date, StockSplit.id)
    ).all()

    factors_by_date: dict[date, Decimal] = {}
    for split in splits:
        factor = Decimal(split.split_factor)
        if not factor.is_finite() or factor <= 0:
            raise ValueError("Stock split factors must be finite and positive.")
        previous = factors_by_date.get(split.effective_date)
        if previous is not None and previous != factor:
            raise ValueError(
                f"Conflicting split factors for listing {listing_id} "
                f"on {split.effective_date}: {previous} and {factor}."
            )
        factors_by_date[split.effective_date] = factor

    with localcontext() as context:
        context.prec = 80
        cumulative_factor = Decimal("1")
        for factor in factors_by_date.values():
            cumulative_factor *= factor
        if observation.observation_date < price_date:
            return share_count * cumulative_factor
        return share_count / cumulative_factor
