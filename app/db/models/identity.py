import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    legal_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    country_code: Mapped[str | None] = mapped_column(
        String(2),
        nullable=True,
    )

    website: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    securities: Mapped[list["Security"]] = relationship(
        back_populates="company",
    )


class Security(Base):
    __tablename__ = "securities"

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

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    security_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    isin: Mapped[str | None] = mapped_column(
        String(12),
        nullable=True,
        unique=True,
    )

    start_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    company: Mapped["Company"] = relationship(
        back_populates="securities",
    )

    listings: Mapped[list["Listing"]] = relationship(
        back_populates="security",
    )

    __table_args__ = (
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_security_date_range",
        ),
    )


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    security_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("securities.id"),
        nullable=False,
        index=True,
    )

    ticker: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )

    exchange_code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    currency_code: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    security: Mapped["Security"] = relationship(
        back_populates="listings",
    )

    __table_args__ = (
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_listing_date_range",
        ),
        UniqueConstraint(
            "security_id",
            "exchange_code",
            "ticker",
            "start_date",
            name="uq_listing_period",
        ),
    )