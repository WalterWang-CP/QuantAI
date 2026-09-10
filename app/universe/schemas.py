import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


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