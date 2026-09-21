import uuid
from datetime import date

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)


class HistoricalUniverseWorkflowRequest(
    BaseModel
):
    ranking_date: date
    effective_date: date

    listing_ids: list[
        uuid.UUID
    ] | None = None

    primary_only: bool = True

    market_cap_limit: int = Field(
        default=5000,
        ge=1,
        le=10000,
    )

    minimum_candidates: int = Field(
        default=1,
        ge=1,
        le=100000,
    )

    auto_approve: bool = False

    create_retrieval_plan: bool = True

    @model_validator(
        mode="after"
    )
    def validate_dates(self):
        if (
            self.effective_date
            < self.ranking_date
        ):
            raise ValueError(
                "effective_date cannot be "
                "earlier than ranking_date."
            )

        return self


class HistoricalUniverseWorkflowResult(
    BaseModel
):
    status: str

    ranking_date: date
    effective_date: date

    market_cap_target_count: int

    market_cap_completed: int
    market_cap_failed: int

    snapshot_id: uuid.UUID

    snapshot_status: str

    companies_ranked: int

    tracking_run_id: uuid.UUID | None = None

    retrieval_jobs_created: int | None = None

    retrieval_jobs_already_exist: int | None = None

    retrieval_already_covered: int | None = None

    retrieval_companies_without_listing: int | None = None