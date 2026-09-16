import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.retrieval.executor import (
    ProviderBatchPaused,
    create_retrieval_batch,
    execute_retrieval_job,
    get_retrieval_batch,
    get_retrieval_progress,
    resume_retrieval_batch,
)
from app.retrieval.schemas import (
    RetrievalBatchRead,
    RetrievalJobRead,
    RetrievalPlanResult,
    RetrievalProgressRead,
)
from app.retrieval.service import (
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
            tracking_run_id=
                tracking_run_id,
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
        tracking_run_id=
            tracking_run_id,
    )


@router.post(
    "/jobs/{job_id}/execute",
    response_model=RetrievalJobRead,
)
def execute_job(
    job_id: uuid.UUID,
    database: DatabaseSession,
    force: bool = False,
):
    try:
        return execute_retrieval_job(
            database=database,
            job_id=job_id,
            force=force,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except ProviderBatchPaused as error:
        raise HTTPException(
            status_code=429,
            detail=(
                f"{error} "
                f"Resume after "
                f"{error.blocked_until}."
            ),
        )


@router.post(
    "/tracking-runs/{tracking_run_id}/batches",
    response_model=RetrievalBatchRead,
)
def run_batch(
    tracking_run_id: uuid.UUID,
    database: DatabaseSession,
    limit: int | None = Query(
        default=None,
        ge=1,
        le=100,
    ),
):
    actual_limit = (
        limit
        if limit is not None
        else settings.retrieval_default_batch_limit
    )

    try:
        return create_retrieval_batch(
            database=database,
            tracking_run_id=
                tracking_run_id,
            limit=actual_limit,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )


@router.get(
    "/batches/{batch_id}",
    response_model=RetrievalBatchRead,
)
def read_batch(
    batch_id: uuid.UUID,
    database: DatabaseSession,
):
    try:
        return get_retrieval_batch(
            database=database,
            batch_id=batch_id,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )


@router.post(
    "/batches/{batch_id}/resume",
    response_model=RetrievalBatchRead,
)
def resume_batch(
    batch_id: uuid.UUID,
    database: DatabaseSession,
):
    try:
        return resume_retrieval_batch(
            database=database,
            batch_id=batch_id,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except ProviderBatchPaused as error:
        raise HTTPException(
            status_code=429,
            detail=(
                f"{error} "
                f"Resume after "
                f"{error.blocked_until}."
            ),
        )


@router.get(
    "/tracking-runs/{tracking_run_id}/progress",
    response_model=RetrievalProgressRead,
)
def read_progress(
    tracking_run_id: uuid.UUID,
    database: DatabaseSession,
):
    try:
        return get_retrieval_progress(
            database=database,
            tracking_run_id=
                tracking_run_id,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )