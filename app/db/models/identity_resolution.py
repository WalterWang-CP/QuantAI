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
    Text,
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


class CompanyRelationship(Base):
    __tablename__ = "company_relationships"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    source_company_id: Mapped[
        uuid.UUID
    ] = mapped_column(
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    target_company_id: Mapped[
        uuid.UUID
    ] = mapped_column(
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    source_id: Mapped[
        uuid.UUID
    ] = mapped_column(
        ForeignKey("data_sources.id"),
        nullable=False,
        index=True,
    )

    relationship_type: Mapped[
        str
    ] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )

    effective_date: Mapped[
        date
    ] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    known_date: Mapped[
        date
    ] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    note: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "source_company_id "
            "<> target_company_id",
            name=(
                "ck_company_relationship_"
                "different_companies"
            ),
        ),
        CheckConstraint(
            "relationship_type IN "
            "("
            "'merged_into', "
            "'acquired_by', "
            "'spun_off_into', "
            "'successor_of'"
            ")",
            name=(
                "ck_company_relationship_type"
            ),
        ),
        UniqueConstraint(
            "source_company_id",
            "target_company_id",
            "source_id",
            "relationship_type",
            "effective_date",
            name="uq_company_relationship",
        ),
    )


class ListingLifecycleEvent(Base):
    __tablename__ = (
        "listing_lifecycle_events"
    )

    id: Mapped[
        uuid.UUID
    ] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    listing_id: Mapped[
        uuid.UUID
    ] = mapped_column(
        ForeignKey("listings.id"),
        nullable=False,
        index=True,
    )

    successor_listing_id: Mapped[
        uuid.UUID | None
    ] = mapped_column(
        ForeignKey("listings.id"),
        nullable=True,
        index=True,
    )

    source_id: Mapped[
        uuid.UUID
    ] = mapped_column(
        ForeignKey("data_sources.id"),
        nullable=False,
        index=True,
    )

    event_type: Mapped[
        str
    ] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )

    effective_date: Mapped[
        date
    ] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    known_date: Mapped[
        date
    ] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    note: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            (
                "successor_listing_id "
                "IS NULL "
                "OR successor_listing_id "
                "<> listing_id"
            ),
            name=(
                "ck_listing_event_"
                "different_successor"
            ),
        ),
        CheckConstraint(
            "event_type IN "
            "("
            "'ticker_change', "
            "'exchange_change', "
            "'delisting', "
            "'relisting'"
            ")",
            name=(
                "ck_listing_lifecycle_"
                "event_type"
            ),
        ),
        UniqueConstraint(
            "listing_id",
            "source_id",
            "event_type",
            "effective_date",
            name=(
                "uq_listing_lifecycle_event"
            ),
        ),
    )

    