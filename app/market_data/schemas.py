import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class DailyPriceBarRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID

    listing_id: uuid.UUID
    source_id: uuid.UUID

    trading_date: date

    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal

    volume: int


class MarketDataImportResult(BaseModel):
    ingestion_run_id: uuid.UUID

    provider: str
    dataset: str
    symbol: str

    status: str

    rows_received: int
    rows_inserted: int
    rows_updated: int

    first_date: date | None
    last_date: date | None

    started_at: datetime
    completed_at: datetime | None