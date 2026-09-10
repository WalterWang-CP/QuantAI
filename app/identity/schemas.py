import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class CompanyCreate(BaseModel):
    legal_name: str = Field(
        min_length=1,
        max_length=255,
    )

    country_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
    )

    website: str | None = None


class CompanyRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    legal_name: str
    country_code: str | None
    website: str | None
    is_active: bool


class SecurityCreate(BaseModel):
    company_id: uuid.UUID

    name: str = Field(
        min_length=1,
        max_length=255,
    )

    security_type: str = Field(
        min_length=1,
        max_length=50,
    )

    isin: str | None = Field(
        default=None,
        max_length=12,
    )

    start_date: date | None = None
    end_date: date | None = None


class SecurityRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    security_type: str
    isin: str | None
    start_date: date | None
    end_date: date | None


class ListingCreate(BaseModel):
    security_id: uuid.UUID

    ticker: str = Field(
        min_length=1,
        max_length=32,
    )

    exchange_code: str = Field(
        min_length=1,
        max_length=32,
    )

    currency_code: str = Field(
        min_length=3,
        max_length=3,
    )

    start_date: date
    end_date: date | None = None

    is_primary: bool = True


class ListingRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    security_id: uuid.UUID
    ticker: str
    exchange_code: str
    currency_code: str
    start_date: date
    end_date: date | None
    is_primary: bool