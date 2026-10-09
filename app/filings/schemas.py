import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RawFactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    taxonomy: str = Field(min_length=1, max_length=100)
    tag: str = Field(min_length=1, max_length=255)
    unit: str = Field(min_length=1, max_length=100)
    period_start: date | None = None
    period_end: date
    value: Decimal = Field(max_digits=60, decimal_places=20, allow_inf_nan=False)
    context: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_start is not None and self.period_start > self.period_end:
            raise ValueError("period_start cannot be later than period_end")
        return self


class FilingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company_id: uuid.UUID
    source_id: uuid.UUID
    cik: str
    accession_number: str = Field(min_length=1, max_length=80)
    form_type: str = Field(min_length=1, max_length=30)
    report_period: date | None = None
    filed_date: date | None = None
    accepted_at: datetime | None = None
    document_url: str | None = Field(default=None, max_length=2000)
    facts: list[RawFactCreate] = Field(default_factory=list)

    @field_validator("cik")
    @classmethod
    def normalize_cik(cls, value):
        if not value.isascii() or not value.isdigit() or not 1 <= len(value) <= 10 or int(value) == 0:
            raise ValueError("cik must contain 1-10 digits and be nonzero")
        return value.zfill(10)

    @field_validator("accepted_at")
    @classmethod
    def normalize_accepted_at(cls, value):
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("accepted_at must include a timezone")
            return value.astimezone(timezone.utc)
        return value

    @model_validator(mode="after")
    def validate_dates(self):
        if self.report_period and self.filed_date and self.report_period > self.filed_date:
            raise ValueError("report_period cannot be later than filed_date")
        if self.accepted_at and self.filed_date and self.accepted_at.date() < self.filed_date:
            raise ValueError("accepted_at cannot be earlier than filed_date")
        availability_date = self.filed_date or (self.accepted_at.date() if self.accepted_at else None)
        if availability_date and any(fact.period_end > availability_date for fact in self.facts):
            raise ValueError("fact period_end cannot be later than filing availability")
        return self


class SECImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    cik: str
    start_date: date | None = None
    end_date: date | None = None
    include_history: bool = True
    # Start with share facts; other statement tags can be requested explicitly.
    tags: list[str] = Field(default_factory=lambda: [
        "EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding",
    ], min_length=1, max_length=100)
    forms: list[str] = Field(default_factory=lambda: [
        "10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A",
    ], min_length=1, max_length=30)

    @field_validator("cik")
    @classmethod
    def normalize_requested_cik(cls, value):
        return FilingCreate.normalize_cik(value)

    @field_validator("tags", "forms")
    @classmethod
    def validate_selection(cls, values):
        values = list(dict.fromkeys(value.strip() for value in values))
        if any(not value or len(value) > 255 for value in values):
            raise ValueError("Selections must contain nonempty names up to 255 characters")
        return values

    @model_validator(mode="after")
    def validate_range(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date cannot be later than end_date")
        return self


class SECImportResult(BaseModel):
    company_id: uuid.UUID
    cik: str
    status: str
    filings_seen: int
    filings_inserted: int
    facts_received: int
    facts_inserted: int
    facts_existing: int
    facts_rejected: int
    artifacts_inserted: int
    metadata_history_complete: bool
    warnings: list[str]


class FilingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    company_id: uuid.UUID
    source_id: uuid.UUID
    cik: str
    accession_number: str
    form_type: str
    report_period: date | None
    filed_date: date | None
    accepted_at: datetime | None
    document_url: str | None
    first_artifact_id: uuid.UUID
    metadata_artifact_id: uuid.UUID
    ingested_at: datetime


class RawFactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    filing_id: uuid.UUID
    artifact_id: uuid.UUID
    taxonomy: str
    tag: str
    unit: str
    period_start: date | None
    period_end: date
    value_text: str
    context_json: str
    normalization_status: str
