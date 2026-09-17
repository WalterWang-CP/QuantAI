import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
)


class StockSplitRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID

    listing_id: uuid.UUID
    source_id: uuid.UUID

    effective_date: date

    split_factor: Decimal


class DividendRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID

    listing_id: uuid.UUID
    source_id: uuid.UUID

    ex_dividend_date: date

    declaration_date: date | None
    record_date: date | None
    payment_date: date | None

    amount: Decimal

    currency_code: str | None


class CorporateActionImportResult(BaseModel):
    ingestion_run_id: uuid.UUID

    raw_artifact_id: uuid.UUID

    provider: str
    dataset: str
    symbol: str

    status: str

    rows_received: int
    rows_inserted: int
    rows_updated: int

    started_at: datetime
    completed_at: datetime | None


class SplitAdjustedPriceBarRead(BaseModel):
    trading_date: date

    raw_open: Decimal
    raw_high: Decimal
    raw_low: Decimal
    raw_close: Decimal
    raw_volume: int

    split_adjustment_factor: Decimal

    adjusted_open: Decimal
    adjusted_high: Decimal
    adjusted_low: Decimal
    adjusted_close: Decimal

    adjusted_volume: Decimal