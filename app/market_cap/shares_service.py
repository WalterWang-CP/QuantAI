import uuid
from datetime import date

from sqlalchemy import (
    desc,
    select,
)
from sqlalchemy.orm import Session

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