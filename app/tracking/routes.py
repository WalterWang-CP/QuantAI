import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.tracking.schemas import (
    TrackingDecisionRead,
    TrackingRunRead,
)
from app.tracking.service import (
    build_tracking_run,
    get_tracking_decisions,
)


router = APIRouter(
    prefix="/tracking",
    tags=["Tracking"],
)


DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]


@router.post(
    "/snapshots/{snapshot_id}/build",
    response_model=TrackingRunRead,
    status_code=201,
)
def build_tracking(
    snapshot_id: uuid.UUID,
    database: DatabaseSession,
):
    try:
        return build_tracking_run(
            database,
            snapshot_id,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )


@router.get(
    "/runs/{run_id}/decisions",
    response_model=list[TrackingDecisionRead],
)
def read_tracking_decisions(
    run_id: uuid.UUID,
    database: DatabaseSession,
):
    return get_tracking_decisions(
        database,
        run_id,
    )