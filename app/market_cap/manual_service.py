import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.fundamentals import (
    SharesOutstandingObservation,
)
from app.db.models.fx import FxRate
from app.db.models.identity import (
    Company,
    Security,
)
from app.db.models.market_data import (
    DataSource,
)
from app.market_cap.schemas import (
    FxRateCreate,
    SharesOutstandingCreate,
)
from app.market_data.service import (
    get_or_create_data_source,
)


SHARES_PROVIDER = "manual"
SHARES_DATASET = "SHARES_OUTSTANDING"

FX_PROVIDER = "manual"
FX_DATASET = "FX_RATE"


def upsert_shares_outstanding(
    database: Session,
    payload: SharesOutstandingCreate,
) -> SharesOutstandingObservation:
    company = database.get(
        Company,
        payload.company_id,
    )

    if company is None:
        raise LookupError(
            "Company does not exist."
        )

    if payload.security_id is not None:
        security = database.get(
            Security,
            payload.security_id,
        )

        if security is None:
            raise LookupError(
                "Security does not exist."
            )

        if (
            security.company_id
            != company.id
        ):
            raise ValueError(
                "The supplied security does "
                "not belong to the supplied "
                "company."
            )

    source = get_or_create_data_source(
        database=database,
        provider_name=SHARES_PROVIDER,
        dataset_name=SHARES_DATASET,
    )

    statement = select(
        SharesOutstandingObservation
    ).where(
        SharesOutstandingObservation.company_id
        == company.id,

        SharesOutstandingObservation.source_id
        == source.id,

        SharesOutstandingObservation.observation_date
        == payload.observation_date,

        SharesOutstandingObservation.known_date
        == payload.known_date,
    )

    if payload.security_id is None:
        statement = statement.where(
            SharesOutstandingObservation
            .security_id
            .is_(None)
        )

    else:
        statement = statement.where(
            SharesOutstandingObservation
            .security_id
            == payload.security_id
        )

    existing = database.scalar(
        statement
    )

    if existing is None:
        observation = (
            SharesOutstandingObservation(
                company_id=company.id,

                security_id=
                    payload.security_id,

                source_id=source.id,

                observation_date=
                    payload.observation_date,

                known_date=
                    payload.known_date,

                shares_outstanding=
                    payload.shares_outstanding,
            )
        )

        database.add(
            observation
        )

    else:
        observation = existing

        observation.shares_outstanding = (
            payload.shares_outstanding
        )

    database.commit()
    database.refresh(
        observation
    )

    return observation


def get_shares_outstanding_history(
    database: Session,
    company_id: uuid.UUID,
) -> list[
    SharesOutstandingObservation
]:
    statement = (
        select(
            SharesOutstandingObservation
        )
        .where(
            SharesOutstandingObservation
            .company_id
            == company_id
        )
        .order_by(
            SharesOutstandingObservation
            .observation_date,

            SharesOutstandingObservation
            .known_date,
        )
    )

    return list(
        database.scalars(
            statement
        ).all()
    )


def upsert_fx_rate(
    database: Session,
    payload: FxRateCreate,
) -> FxRate:
    source = get_or_create_data_source(
        database=database,
        provider_name=FX_PROVIDER,
        dataset_name=FX_DATASET,
    )

    statement = select(
        FxRate
    ).where(
        FxRate.source_id
        == source.id,

        FxRate.rate_date
        == payload.rate_date,

        FxRate.base_currency
        == payload.base_currency,

        FxRate.quote_currency
        == payload.quote_currency,
    )

    existing = database.scalar(
        statement
    )

    if existing is None:
        fx_rate = FxRate(
            source_id=source.id,

            rate_date=
                payload.rate_date,

            base_currency=
                payload.base_currency,

            quote_currency=
                payload.quote_currency,

            rate=payload.rate,
        )

        database.add(
            fx_rate
        )

    else:
        fx_rate = existing

        fx_rate.rate = payload.rate

    database.commit()
    database.refresh(
        fx_rate
    )

    return fx_rate


def get_fx_rates(
    database: Session,
    base_currency: str | None = None,
    quote_currency: str | None = None,
) -> list[FxRate]:
    statement = select(
        FxRate
    )

    if base_currency is not None:
        statement = statement.where(
            FxRate.base_currency
            == base_currency.upper()
        )

    if quote_currency is not None:
        statement = statement.where(
            FxRate.quote_currency
            == quote_currency.upper()
        )

    statement = statement.order_by(
        FxRate.rate_date,
        FxRate.base_currency,
        FxRate.quote_currency,
    )

    return list(
        database.scalars(
            statement
        ).all()
    )