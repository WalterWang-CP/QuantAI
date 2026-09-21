import uuid
from datetime import date, datetime
from decimal import Decimal
from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    model_validator,
)
class RankingSnapshotCreate(BaseModel):
    ranking_date: date
    effective_date: date

    ranking_metric: str = Field(
        default="market_cap_usd",
        min_length=1,
        max_length=50,
    )

    base_currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
    )


class RankingSnapshotRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    ranking_date: date
    effective_date: date
    ranking_metric: str
    base_currency: str


class CompanyRankingCreate(BaseModel):
    company_id: uuid.UUID

    rank: int = Field(
        gt=0,
    )

    market_cap_usd: Decimal | None = Field(
        default=None,
        ge=0,
    )


class CompanyRankingRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    snapshot_id: uuid.UUID
    company_id: uuid.UUID
    rank: int
    market_cap_usd: Decimal | None


class UniversePreviewMember(BaseModel):
    company_id: uuid.UUID
    legal_name: str

    rank: int
    market_cap_usd: Decimal | None

    main_universe: bool
    elite_trigger: bool

    tracking_reason: str


class UniversePreview(BaseModel):
    snapshot_id: uuid.UUID

    ranking_date: date
    effective_date: date

    policy_name: str

    main_universe_size: int
    elite_threshold: int

    member_count: int

    members: list[UniversePreviewMember]

class MarketCapRankingBuildRequest(BaseModel):
    ranking_date: date

    effective_date: date

    primary_only: bool = True

    minimum_candidates: int = Field(
        default=1,
        ge=1,
        le=100000,
    )

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


class MarketCapRankingMemberRead(BaseModel):
    company_id: uuid.UUID

    listing_id: uuid.UUID

    ticker: str

    rank: int

    market_cap_usd: Decimal


class MarketCapRankingBuildResult(BaseModel):
    snapshot_id: uuid.UUID

    ranking_date: date
    effective_date: date

    ranking_metric: str
    base_currency: str

    snapshot_status: str

    candidates_found: int

    companies_ranked: int

    duplicate_company_observations: int

    reused_existing_snapshot: bool

    top_members: list[
        MarketCapRankingMemberRead
    ]

class RankingSnapshotApprovalRequest(
    BaseModel
):
    note: str | None = None


class RankingSnapshotApprovalRead(
    BaseModel
):
    snapshot_id: uuid.UUID

    status: str

    candidate_count: int | None

    ranked_company_count: int | None

    minimum_required_candidates: int | None

    approved_at: datetime | None

    approval_note: str | None