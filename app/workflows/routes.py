from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.workflows.schemas import (
    HistoricalUniverseWorkflowRequest,
    HistoricalUniverseWorkflowResult,
)
from app.workflows.service import (
    run_historical_universe_workflow,
)


router = APIRouter(
    prefix="/workflows",
    tags=["Workflows"],
)


DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]


@router.post(
    "/historical-universe/run",
    response_model=
        HistoricalUniverseWorkflowResult,
)
def run_historical_universe(
    payload:
        HistoricalUniverseWorkflowRequest,
    database: DatabaseSession,
):
    try:
        return (
            run_historical_universe_workflow(
                database=database,
                payload=payload,
            )
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        )