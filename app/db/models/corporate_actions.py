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


class StockSplit(Base):
    __tablename__ = "stock_splits"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id"),
        nullable=False,
        index=True,
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id"),
        nullable=False,
        index=True,
    )

    last_ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_runs.id"),
        nullable=False,
    )

    effective_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    split_factor: Mapped[Decimal] = mapped_column(
        Numeric(24, 10),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "split_factor > 0",
            name="ck_stock_split_positive_factor",
        ),
        UniqueConstraint(
            "listing_id",
            "source_id",
            "effective_date",
            name="uq_split_listing_source_date",
        ),
    )


class Dividend(Base):
    __tablename__ = "dividends"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id"),
        nullable=False,
        index=True,
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id"),
        nullable=False,
        index=True,
    )

    last_ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_runs.id"),
        nullable=False,
    )

    ex_dividend_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    declaration_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    record_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    payment_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(24, 10),
        nullable=False,
    )

    currency_code: Mapped[str | None] = mapped_column(
        String(3),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "amount >= 0",
            name="ck_dividend_non_negative_amount",
        ),
        UniqueConstraint(
            "listing_id",
            "source_id",
            "ex_dividend_date",
            "amount",
            name="uq_dividend_listing_source_event",
        ),
    )