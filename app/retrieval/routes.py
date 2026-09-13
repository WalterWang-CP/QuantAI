import uuid
from typing import Annotated

import httpx

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.retrieval.schemas import (
    RetrievalJobRead,
    RetrievalPlanResult,
)
from app.retrieval.service import (
    execute_retrieval_job,
    get_retrieval_jobs,
    plan_retrieval_jobs,
)


router = APIRouter(
    prefix="/retrieval",
    tags=["Retrieval"],
)


DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]


@router.post(
    "/tracking-runs/{tracking_run_id}/plan",
    response_model=RetrievalPlanResult,
)
def create_retrieval_plan(
    tracking_run_id: uuid.UUID,
    database: DatabaseSession,
):
    try:
        return plan_retrieval_jobs(
            database=database,
            tracking_run_id=tracking_run_id,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )


@router.get(
    "/tracking-runs/{tracking_run_id}/jobs",
    response_model=list[RetrievalJobRead],
)
def read_retrieval_jobs(
    tracking_run_id: uuid.UUID,
    database: DatabaseSession,
):
    return get_retrieval_jobs(
        database=database,
        tracking_run_id=tracking_run_id,
    )


@router.post(
    "/jobs/{job_id}/execute",
    response_model=RetrievalJobRead,
)
def execute_job(
    job_id: uuid.UUID,
    database: DatabaseSession,
):
    try:
        return execute_retrieval_job(
            database=database,
            job_id=job_id,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        )

    except httpx.HTTPError:
        raise HTTPException(
            status_code=502,
            detail=(
                "Unable to communicate "
                "with data provider."
            ),
        )