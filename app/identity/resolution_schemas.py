import uuid
from datetime import date, datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class ValidityMixin(BaseModel):
    valid_from: date | None = None
    valid_to: date | None = None

    @model_validator(
        mode="after"
    )
    def validate_validity(self):
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to
            < self.valid_from
        ):
            raise ValueError(
                "valid_to cannot be earlier "
                "than valid_from."
            )

        return self


class CompanyIdentifierCreate(
    ValidityMixin
):
    company_id: uuid.UUID

    scheme: str = Field(
        min_length=1,
        max_length=40,
    )

    value: str = Field(
        min_length=1,
        max_length=255,
    )

    is_primary: bool = True

    @field_validator("scheme")
    @classmethod
    def normalize_scheme(
        cls,
        value: str,
    ) -> str:
        return (
            value
            .strip()
            .upper()
        )

    @field_validator("value")
    @classmethod
    def normalize_value(
        cls,
        value: str,
    ) -> str:
        return value.strip()


class CompanyIdentifierRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    company_id: uuid.UUID

    scheme: str
    value: str

    valid_from: date | None
    valid_to: date | None

    is_primary: bool

    created_at: datetime


class SecurityIdentifierCreate(
    ValidityMixin
):
    security_id: uuid.UUID

    scheme: str = Field(
        min_length=1,
        max_length=40,
    )

    value: str = Field(
        min_length=1,
        max_length=255,
    )

    is_primary: bool = True

    @field_validator("scheme")
    @classmethod
    def normalize_scheme(
        cls,
        value: str,
    ) -> str:
        return (
            value
            .strip()
            .upper()
        )

    @field_validator("value")
    @classmethod
    def normalize_value(
        cls,
        value: str,
    ) -> str:
        return value.strip()


class SecurityIdentifierRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    security_id: uuid.UUID

    scheme: str
    value: str

    valid_from: date | None
    valid_to: date | None

    is_primary: bool

    created_at: datetime


class CompanyAliasCreate(
    ValidityMixin
):
    company_id: uuid.UUID

    alias: str = Field(
        min_length=1,
        max_length=255,
    )

    alias_type: str = Field(
        default="name",
        min_length=1,
        max_length=40,
    )


class CompanyAliasRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    company_id: uuid.UUID

    alias: str
    alias_type: str

    valid_from: date | None
    valid_to: date | None

    created_at: datetime


class ListingProviderSymbolCreate(
    ValidityMixin
):
    listing_id: uuid.UUID

    provider_name: str = Field(
        min_length=1,
        max_length=80,
    )

    symbol: str = Field(
        min_length=1,
        max_length=80,
    )

    @field_validator(
        "provider_name"
    )
    @classmethod
    def normalize_provider(
        cls,
        value: str,
    ) -> str:
        return (
            value
            .strip()
            .lower()
        )

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(
        cls,
        value: str,
    ) -> str:
        return value.strip()


class ListingProviderSymbolRead(
    BaseModel
):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    listing_id: uuid.UUID

    provider_name: str
    symbol: str

    valid_from: date | None
    valid_to: date | None

    created_at: datetime

class CompanyRelationshipCreate(
    BaseModel
):
    source_company_id: uuid.UUID
    target_company_id: uuid.UUID

    relationship_type: str = Field(
        min_length=1,
        max_length=40,
    )

    effective_date: date
    known_date: date

    note: str | None = None

    @field_validator(
        "relationship_type"
    )
    @classmethod
    def normalize_relationship_type(
        cls,
        value: str,
    ) -> str:
        return (
            value
            .strip()
            .lower()
        )

    @model_validator(
        mode="after"
    )
    def validate_companies(self):
        if (
            self.source_company_id
            == self.target_company_id
        ):
            raise ValueError(
                "A company cannot have "
                "a lifecycle relationship "
                "with itself."
            )

        return self


class CompanyRelationshipRead(
    BaseModel
):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID

    source_company_id: uuid.UUID
    target_company_id: uuid.UUID

    source_id: uuid.UUID

    relationship_type: str

    effective_date: date
    known_date: date

    note: str | None

    created_at: datetime


class ListingLifecycleEventCreate(
    BaseModel
):
    listing_id: uuid.UUID

    successor_listing_id: uuid.UUID | None = None

    event_type: str = Field(
        min_length=1,
        max_length=40,
    )

    effective_date: date
    known_date: date

    note: str | None = None

    @field_validator(
        "event_type"
    )
    @classmethod
    def normalize_event_type(
        cls,
        value: str,
    ) -> str:
        return (
            value
            .strip()
            .lower()
        )

    @model_validator(
        mode="after"
    )
    def validate_successor(self):
        if (
            self.successor_listing_id
            == self.listing_id
        ):
            raise ValueError(
                "successor_listing_id "
                "cannot equal listing_id."
            )

        transition_types = {
            "ticker_change",
            "exchange_change",
            "relisting",
        }

        if (
            self.event_type
            in transition_types
            and self.successor_listing_id
            is None
        ):
            raise ValueError(
                f"{self.event_type} requires "
                "a successor_listing_id."
            )

        return self


class ListingLifecycleEventRead(
    BaseModel
):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID

    listing_id: uuid.UUID

    successor_listing_id: uuid.UUID | None

    source_id: uuid.UUID

    event_type: str

    effective_date: date
    known_date: date

    note: str | None

    created_at: datetime


class ProviderSymbolSegmentRead(
    BaseModel
):
    start_date: date
    end_date: date

    symbol: str