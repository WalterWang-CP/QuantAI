import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    provider_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    dataset_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "provider_name",
            "dataset_name",
            name="uq_data_source_provider_dataset",
        ),
    )


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

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

    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id"),
        nullable=False,
        index=True,
    )

    requested_symbol: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    full_history: Mapped[bool]

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    rows_received: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    rows_inserted: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    rows_updated: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class DailyPriceBar(Base):
    __tablename__ = "daily_price_bars"

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

    trading_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    open_price: Mapped[Decimal] = mapped_column(
        Numeric(24, 8),
        nullable=False,
    )

    high_price: Mapped[Decimal] = mapped_column(
        Numeric(24, 8),
        nullable=False,
    )

    low_price: Mapped[Decimal] = mapped_column(
        Numeric(24, 8),
        nullable=False,
    )

    close_price: Mapped[Decimal] = mapped_column(
        Numeric(24, 8),
        nullable=False,
    )

    volume: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "listing_id",
            "source_id",
            "trading_date",
            name="uq_daily_price_listing_source_date",
        ),
    )


class RawDataArtifact(Base):
    __tablename__ = "raw_data_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_runs.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id"),
        nullable=False,
    )

    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id"),
        nullable=False,
    )

    storage_path: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    content_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    byte_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_runs.id"),
        nullable=False,
        index=True,
    )

    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id"),
        nullable=False,
        index=True,
    )

    trading_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    rule_code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )