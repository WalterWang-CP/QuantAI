import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


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