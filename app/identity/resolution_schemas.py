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