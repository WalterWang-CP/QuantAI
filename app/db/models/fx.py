import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.db.database import Base


class FxRate(Base):
    __tablename__ = "fx_rates"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id"),
        nullable=False,
        index=True,
    )

    rate_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    base_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    quote_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    rate: Mapped[Decimal] = mapped_column(
        Numeric(24, 12),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "rate > 0",
            name="ck_fx_rate_positive",
        ),
        CheckConstraint(
            (
                "base_currency "
                "<> quote_currency"
            ),
            name="ck_fx_different_currencies",
        ),
        UniqueConstraint(
            "source_id",
            "rate_date",
            "base_currency",
            "quote_currency",
            name="uq_fx_rate",
        ),
    )