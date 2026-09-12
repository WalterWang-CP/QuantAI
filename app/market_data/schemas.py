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

    raw_artifact_id: uuid.UUID | None
    quality_issue_count: int

    first_date: date | None
    last_date: date | None

    started_at: datetime
    completed_at: datetime | None


class RawDataArtifactRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    ingestion_run_id: uuid.UUID

    storage_path: str
    sha256: str
    content_type: str | None

    byte_count: int
    created_at: datetime


class DataQualityIssueRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    ingestion_run_id: uuid.UUID
    listing_id: uuid.UUID

    trading_date: date | None

    severity: str
    rule_code: str
    message: str

    created_at: datetime