import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.db.database import Base


class SharesOutstandingObservation(Base):
    __tablename__ = (
        "shares_outstanding_observations"
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    security_id: Mapped[
        uuid.UUID | None
    ] = mapped_column(
        ForeignKey("securities.id"),
        nullable=True,
        index=True,
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id"),
        nullable=False,
        index=True,
    )

    observation_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    known_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    shares_outstanding: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(30, 4),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "shares_outstanding > 0",
            name=(
                "ck_shares_outstanding_positive"
            ),
        ),
        CheckConstraint(
            "known_date >= observation_date",
            name=(
                "ck_shares_known_after_observation"
            ),
        ),
        UniqueConstraint(
            "company_id",
            "security_id",
            "source_id",
            "observation_date",
            "known_date",
            name=(
                "uq_shares_observation"
            ),
        ),
    )