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


class MarketCapObservation(Base):
    __tablename__ = (
        "market_cap_observations"
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

    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id"),
        nullable=False,
        index=True,
    )

    valuation_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    price_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    shares_observation_id: Mapped[
        uuid.UUID
    ] = mapped_column(
        ForeignKey(
            "shares_outstanding_observations.id"
        ),
        nullable=False,
    )

    fx_rate_id: Mapped[
        uuid.UUID | None
    ] = mapped_column(
        ForeignKey("fx_rates.id"),
        nullable=True,
    )

    local_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    price: Mapped[Decimal] = mapped_column(
        Numeric(24, 8),
        nullable=False,
    )

    shares_outstanding: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(30, 4),
        nullable=False,
    )

    local_market_cap: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(38, 4),
        nullable=False,
    )

    market_cap_usd: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(38, 4),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "price > 0",
            name="ck_market_cap_price_positive",
        ),
        CheckConstraint(
            "shares_outstanding > 0",
            name="ck_market_cap_shares_positive",
        ),
        CheckConstraint(
            "local_market_cap > 0",
            name="ck_local_market_cap_positive",
        ),
        CheckConstraint(
            "market_cap_usd > 0",
            name="ck_market_cap_usd_positive",
        ),
        UniqueConstraint(
            "company_id",
            "listing_id",
            "valuation_date",
            name="uq_market_cap_valuation",
        ),
    )