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
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.db.database import Base


class CompanyIdentifier(Base):
    __tablename__ = "company_identifiers"

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

    scheme: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )

    value: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    valid_from: Mapped[
        date | None
    ] = mapped_column(
        Date,
        nullable=True,
    )

    valid_to: Mapped[
        date | None
    ] = mapped_column(
        Date,
        nullable=True,
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            (
                "valid_to IS NULL "
                "OR valid_from IS NULL "
                "OR valid_to >= valid_from"
            ),
            name=(
                "ck_company_identifier_dates"
            ),
        ),
        UniqueConstraint(
            "scheme",
            "value",
            "valid_from",
            name=(
                "uq_company_identifier_value"
            ),
        ),
    )


class SecurityIdentifier(Base):
    __tablename__ = "security_identifiers"

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

    scheme: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )

    value: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    valid_from: Mapped[
        date | None
    ] = mapped_column(
        Date,
        nullable=True,
    )

    valid_to: Mapped[
        date | None
    ] = mapped_column(
        Date,
        nullable=True,
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            (
                "valid_to IS NULL "
                "OR valid_from IS NULL "
                "OR valid_to >= valid_from"
            ),
            name=(
                "ck_security_identifier_dates"
            ),
        ),
        UniqueConstraint(
            "scheme",
            "value",
            "valid_from",
            name=(
                "uq_security_identifier_value"
            ),
        ),
    )


class CompanyAlias(Base):
    __tablename__ = "company_aliases"

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

    alias: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    alias_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="name",
    )

    valid_from: Mapped[
        date | None
    ] = mapped_column(
        Date,
        nullable=True,
    )

    valid_to: Mapped[
        date | None
    ] = mapped_column(
        Date,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            (
                "valid_to IS NULL "
                "OR valid_from IS NULL "
                "OR valid_to >= valid_from"
            ),
            name="ck_company_alias_dates",
        ),
        UniqueConstraint(
            "company_id",
            "alias",
            "valid_from",
            name="uq_company_alias",
        ),
    )


class ListingProviderSymbol(Base):
    __tablename__ = (
        "listing_provider_symbols"
    )

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

    provider_name: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        index=True,
    )

    symbol: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        index=True,
    )

    valid_from: Mapped[
        date | None
    ] = mapped_column(
        Date,
        nullable=True,
    )

    valid_to: Mapped[
        date | None
    ] = mapped_column(
        Date,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            (
                "valid_to IS NULL "
                "OR valid_from IS NULL "
                "OR valid_to >= valid_from"
            ),
            name=(
                "ck_provider_symbol_dates"
            ),
        ),
        UniqueConstraint(
            "listing_id",
            "provider_name",
            "symbol",
            "valid_from",
            name=(
                "uq_listing_provider_symbol"
            ),
        ),
    )