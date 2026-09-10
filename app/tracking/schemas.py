import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class TrackingRunRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    snapshot_id: uuid.UUID
    policy_name: str
    policy_hash: str
    engine_version: str
    created_at: datetime


class TrackingDecisionRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    run_id: uuid.UUID
    company_id: uuid.UUID

    rank: int | None

    main_universe: bool

    elite_tracking: bool
    elite_triggered_now: bool

    first_elite_date: date | None
    historical_backfill_start: date | None

    dropout_tracking: bool
    dropout_triggered_now: bool
    dropout_until: date | None

    reason: str