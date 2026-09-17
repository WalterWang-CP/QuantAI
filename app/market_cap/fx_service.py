from datetime import date
from decimal import Decimal

from sqlalchemy import (
    desc,
    select,
)
from sqlalchemy.orm import Session

from app.db.models.fx import FxRate


def find_fx_rate(
    database: Session,
    from_currency: str,
    to_currency: str,
    as_of_date: date,
) -> tuple[
    Decimal,
    FxRate | None,
]:
    from_currency = (
        from_currency
        .strip()
        .upper()
    )

    to_currency = (
        to_currency
        .strip()
        .upper()
    )

    if from_currency == to_currency:
        return Decimal("1"), None

    direct_statement = (
        select(FxRate)
        .where(
            FxRate.base_currency
            == from_currency,

            FxRate.quote_currency
            == to_currency,

            FxRate.rate_date
            <= as_of_date,
        )
        .order_by(
            desc(
                FxRate.rate_date
            )
        )
        .limit(1)
    )

    direct_rate = database.scalar(
        direct_statement
    )

    if direct_rate is not None:
        return (
            direct_rate.rate,
            direct_rate,
        )

    inverse_statement = (
        select(FxRate)
        .where(
            FxRate.base_currency
            == to_currency,

            FxRate.quote_currency
            == from_currency,

            FxRate.rate_date
            <= as_of_date,
        )
        .order_by(
            desc(
                FxRate.rate_date
            )
        )
        .limit(1)
    )

    inverse_rate = database.scalar(
        inverse_statement
    )

    if inverse_rate is not None:
        return (
            Decimal("1")
            / inverse_rate.rate,
            inverse_rate,
        )

    raise LookupError(
        "No FX rate is available for "
        f"{from_currency}/{to_currency} "
        f"on or before {as_of_date}."
    )