import uuid
from datetime import date, datetime

from pydantic import (
    BaseModel,
    ConfigDict,
)


class RetrievalJobRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID

    tracking_run_id: uuid.UUID
    company_id: uuid.UUID
    listing_id: uuid.UUID

    provider_name: str
    dataset_name: str

    required_start_date: date
    required_end_date: date

    full_history: bool

    status: str
    reason: str

    attempt_count: int

    ingestion_run_id: uuid.UUID | None

    error_message: str | None
    last_error_type: str | None

    last_attempt_at: datetime | None
    next_retry_at: datetime | None

    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class RetrievalPlanResult(BaseModel):
    tracking_run_id: uuid.UUID

    tracked_companies: int

    jobs_created: int
    jobs_already_exist: int

    already_covered: int
    companies_without_listing: int


class RetrievalBatchRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID

    tracking_run_id: uuid.UUID
    provider_name: str

    requested_limit: int

    status: str

    attempts_started: int
    jobs_completed: int
    retry_scheduled: int
    jobs_failed: int

    paused_until: datetime | None
    stop_reason: str | None

    started_at: datetime
    completed_at: datetime | None


class RetrievalProgressRead(BaseModel):
    tracking_run_id: uuid.UUID

    total_jobs: int

    pending: int
    running: int
    completed: int
    retry_wait: int
    failed: int

    completion_percent: float
    terminal_percent: float

    next_retry_at: datetime | None

    provider_name: str

    provider_requests_today: int
    provider_daily_budget: int | None

    provider_blocked_until: datetime | None
    provider_block_reason: str | None