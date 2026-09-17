import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class SharesOutstandingCreate(BaseModel):
    company_id: uuid.UUID

    security_id: uuid.UUID | None = None

    observation_date: date
    known_date: date

    shares_outstanding: Decimal = Field(
        gt=0,
    )

    @model_validator(
        mode="after"
    )
    def validate_dates(self):
        if (
            self.known_date
            < self.observation_date
        ):
            raise ValueError(
                "known_date cannot be "
                "earlier than observation_date."
            )

        return self


class SharesOutstandingRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID

    company_id: uuid.UUID
    security_id: uuid.UUID | None

    source_id: uuid.UUID

    observation_date: date
    known_date: date

    shares_outstanding: Decimal

    created_at: datetime


class FxRateCreate(BaseModel):
    rate_date: date

    base_currency: str = Field(
        min_length=3,
        max_length=3,
    )

    quote_currency: str = Field(
        min_length=3,
        max_length=3,
    )

    rate: Decimal = Field(
        gt=0,
    )

    @field_validator(
        "base_currency",
        "quote_currency",
    )
    @classmethod
    def normalize_currency(
        cls,
        value: str,
    ) -> str:
        return (
            value
            .strip()
            .upper()
        )

    @model_validator(
        mode="after"
    )
    def validate_pair(self):
        if (
            self.base_currency
            == self.quote_currency
        ):
            raise ValueError(
                "FX base and quote "
                "currencies must differ."
            )

        return self


class FxRateRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    source_id: uuid.UUID

    rate_date: date

    base_currency: str
    quote_currency: str

    rate: Decimal

    created_at: datetime


class MarketCapObservationRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID

    company_id: uuid.UUID
    listing_id: uuid.UUID

    valuation_date: date
    price_date: date

    shares_observation_id: uuid.UUID

    fx_rate_id: uuid.UUID | None

    local_currency: str

    price: Decimal
    shares_outstanding: Decimal

    local_market_cap: Decimal
    market_cap_usd: Decimal

    created_at: datetime


class MarketCapBatchRequest(BaseModel):
    valuation_date: date

    listing_ids: list[
        uuid.UUID
    ] | None = Field(
        default=None,
        max_length=5000,
    )

    primary_only: bool = True

    limit: int = Field(
        default=1000,
        ge=1,
        le=5000,
    )


class MarketCapBatchItemRead(BaseModel):
    listing_id: uuid.UUID

    ticker: str

    status: str

    observation: MarketCapObservationRead | None = None

    error_type: str | None = None
    error_message: str | None = None


class MarketCapBatchResult(BaseModel):
    valuation_date: date

    target_count: int

    completed: int
    failed: int

    items: list[
        MarketCapBatchItemRead
    ]