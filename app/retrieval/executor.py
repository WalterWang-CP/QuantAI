import uuid
from datetime import (
    datetime,
    timedelta,
    timezone,
)

from sqlalchemy import (
    and_,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.config import settings
from app.db.models.retrieval import (
    ProviderThrottleState,
    RetrievalBatchRun,
    RetrievalJob,
    RetrievalJobAttempt,
)
from app.db.models.tracking import TrackingRun
from app.providers.errors import (
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTemporaryError,
    ProviderCapabilityError,
)
from app.providers.registry import (
    execute_registered_retrieval,
    get_provider_daily_budget,
    get_provider_registration,
    validate_retrieval_capability,
)

DEFAULT_PROVIDER_NAME = (
    "alpha_vantage"
)


class ProviderBatchPaused(RuntimeError):
    def __init__(
        self,
        message: str,
        blocked_until: datetime,
    ):
        super().__init__(message)

        self.blocked_until = blocked_until


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(
    value: datetime | None,
) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def next_utc_midnight() -> datetime:
    now = utc_now()

    tomorrow = (
        now.date()
        + timedelta(days=1)
    )

    return datetime.combine(
        tomorrow,
        datetime.min.time(),
        tzinfo=timezone.utc,
    )


def provider_daily_budget(
    provider_name: str,
) -> int | None:
    return (
        get_provider_daily_budget(
            provider_name
        )
    )


def _locked_throttle_state(
    database: Session,
    provider_name: str,
) -> ProviderThrottleState:
    provider_name = get_provider_registration(provider_name).provider_name
    dialect = database.get_bind().dialect.name
    if dialect == "postgresql":
        insert = postgres_insert
    elif dialect == "sqlite":
        insert = sqlite_insert
    else:
        raise ValueError("Retrieval coordination supports PostgreSQL and SQLite.")
    today = utc_now().date()
    database.execute(
        insert(ProviderThrottleState)
        .values(provider_name=provider_name, quota_date=today, requests_today=0)
        .on_conflict_do_nothing(index_elements=["provider_name"])
    )
    state = database.scalar(
        select(ProviderThrottleState)
        .where(ProviderThrottleState.provider_name == provider_name)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if state.quota_date != today:
        state.quota_date = today
        state.requests_today = 0
        state.blocked_until = None
        state.block_reason = None
    blocked_until = ensure_utc(state.blocked_until)
    if blocked_until is not None and blocked_until <= utc_now():
        state.blocked_until = None
        state.block_reason = None
    return state


def get_or_create_throttle_state(
    database: Session,
    provider_name: str,
) -> ProviderThrottleState:
    state = _locked_throttle_state(database, provider_name)
    database.commit()
    database.refresh(state)
    return state


def validate_provider_capability(job: RetrievalJob) -> None:
    validate_retrieval_capability(
        provider_name=job.provider_name,
        dataset_name=job.dataset_name,
        full_history=job.full_history,
    )


def _pause_for_state(state: ProviderThrottleState) -> tuple[datetime | None, str | None]:
    blocked_until = ensure_utc(state.blocked_until)
    if blocked_until is not None and blocked_until > utc_now():
        return blocked_until, state.block_reason
    budget = provider_daily_budget(state.provider_name)
    if budget is not None and state.requests_today >= budget:
        state.blocked_until = next_utc_midnight()
        state.block_reason = "Local daily provider safety budget reached."
        return state.blocked_until, state.block_reason
    return None, None


def get_provider_pause(
    database: Session,
    provider_name: str,
) -> tuple[datetime | None, str | None]:
    state = _locked_throttle_state(database, provider_name)
    pause = _pause_for_state(state)
    database.commit()
    return pause


def reserve_provider_request(
    database: Session,
    provider_name: str,
    *,
    commit: bool = True,
) -> None:
    state = _locked_throttle_state(database, provider_name)
    blocked_until, reason = _pause_for_state(state)
    if blocked_until is not None:
        if commit:
            database.commit()
        raise ProviderBatchPaused(reason or "Provider is temporarily paused.", blocked_until)
    state.requests_today += 1
    state.last_request_at = utc_now()
    database.flush()
    if commit:
        database.commit()


def block_provider_after_rate_limit(
    database: Session,
    provider_name: str,
    reason: str,
) -> datetime:
    state = _locked_throttle_state(database, provider_name)
    blocked_until = next_utc_midnight()
    state.blocked_until = blocked_until
    state.block_reason = reason
    database.commit()
    return blocked_until


def retry_delay_seconds(
    attempt_number: int,
) -> int:
    base = (
        settings
        .retrieval_retry_base_seconds
    )

    delay = (
        base
        * (2 ** (attempt_number - 1))
    )

    return min(
        delay,
        3600,
    )


def _lock_active_attempt(database: Session, job_id: uuid.UUID, attempt_id: uuid.UUID):
    job = database.scalar(
        select(RetrievalJob).where(RetrievalJob.id == job_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    attempt = database.get(RetrievalJobAttempt, attempt_id, populate_existing=True)
    active = (
        job is not None and attempt is not None
        and job.status == "running" and attempt.status == "running"
        and attempt.job_id == job.id and attempt.attempt_number == job.attempt_count
    )
    return job, attempt, active


def finish_failed_attempt(
    database: Session,
    job_id: uuid.UUID,
    attempt_id: uuid.UUID,
    job_status: str,
    attempt_status: str,
    error_type: str,
    error_message: str,
    next_retry_at: datetime | None = None,
    ingestion_run_id: uuid.UUID | None = None,
) -> RetrievalJob:
    now = utc_now()

    job, attempt, active = _lock_active_attempt(database, job_id, attempt_id)
    if not active:
        database.rollback()
        return job
    if ingestion_run_id is not None:
        job.ingestion_run_id = ingestion_run_id

    job.status = job_status

    job.last_error_type = error_type

    job.error_message = error_message

    job.next_retry_at = next_retry_at

    if job_status == "failed":
        job.completed_at = now

    attempt.status = attempt_status

    attempt.error_type = error_type

    attempt.error_message = error_message

    attempt.completed_at = now

    database.commit()
    database.refresh(job)

    return job


def execute_retrieval_job(
    database: Session,
    job_id: uuid.UUID,
    batch_run_id: uuid.UUID | None = None,
    force: bool = False,
) -> RetrievalJob:
    job = database.get(RetrievalJob, job_id, populate_existing=True)
    if job is None:
        raise LookupError("Retrieval job does not exist.")
    now = utc_now()
    eligible = or_(
        RetrievalJob.status == "pending",
        and_(
            RetrievalJob.status == "retry_wait",
            or_(
                RetrievalJob.next_retry_at.is_(None),
                RetrievalJob.next_retry_at <= now,
                force,
            ),
        ),
        and_(RetrievalJob.status == "failed", force),
    )
    if job.status in {"completed", "running"}:
        return job
    if job.status == "failed" and not force:
        return job
    retry_at = ensure_utc(job.next_retry_at)
    if job.status == "retry_wait" and retry_at is not None and retry_at > now and not force:
        return job
    try:
        validate_provider_capability(job)
    except ProviderCapabilityError as error:
        database.execute(
            update(RetrievalJob).where(RetrievalJob.id == job_id, eligible)
            .values(status="failed", last_error_type="provider_capability",
                    error_message=str(error), completed_at=now)
            .execution_options(synchronize_session=False)
        )
        database.commit()
        database.refresh(job)
        return job

    try:
        claimed = database.execute(
            update(RetrievalJob).where(RetrievalJob.id == job_id, eligible)
            .values(
                status="running", attempt_count=RetrievalJob.attempt_count + 1,
                last_attempt_at=now, next_retry_at=None, error_message=None,
                last_error_type=None, completed_at=None,
                started_at=func.coalesce(RetrievalJob.started_at, now),
            ).execution_options(synchronize_session=False)
        ).rowcount
        if claimed != 1:
            database.rollback()
            database.refresh(job)
            return job
        if batch_run_id is not None:
            reserved_slot = database.execute(
                update(RetrievalBatchRun).where(
                    RetrievalBatchRun.id == batch_run_id,
                    RetrievalBatchRun.attempts_started < RetrievalBatchRun.requested_limit,
                ).values(attempts_started=RetrievalBatchRun.attempts_started + 1)
                .execution_options(synchronize_session=False)
            ).rowcount
            if reserved_slot != 1:
                database.rollback()
                database.refresh(job)
                return job
        database.refresh(job)
        reserve_provider_request(database, job.provider_name, commit=False)
        attempt = RetrievalJobAttempt(
            job_id=job.id, batch_run_id=batch_run_id,
            attempt_number=job.attempt_count, status="running", started_at=now,
        )
        database.add(attempt)
        database.commit()
        database.refresh(attempt)
    except Exception:
        database.rollback()
        raise

    try:
        result = (
            execute_registered_retrieval(
                database=database,

                provider_name=
                    job.provider_name,

                dataset_name=
                    job.dataset_name,

                listing_id=
                    job.listing_id,

                full_history=
                    job.full_history,

                start_date=
                    job.required_start_date,

                end_date=
                    job.required_end_date,
            )
        )

        job, attempt, active = _lock_active_attempt(database, job_id, attempt.id)
        if not active:
            database.rollback()
            return job

        if result["status"] == "incomplete":
            should_retry = (
                job.attempt_count < settings.retrieval_max_attempts
            )
            retry_at = None

            if should_retry:
                retry_at = utc_now() + timedelta(
                    seconds=retry_delay_seconds(job.attempt_count)
                )

            return finish_failed_attempt(
                database=database,
                job_id=job.id,
                attempt_id=attempt.id,
                ingestion_run_id=result["ingestion_run_id"],
                job_status="retry_wait" if should_retry else "failed",
                attempt_status="retry_wait" if should_retry else "failed",
                error_type="incomplete_coverage",
                error_message=(
                    result.get("error_message")
                    or "Requested trading-session coverage is incomplete."
                ),
                next_retry_at=retry_at,
            )

        if result["status"] != "completed":
            return finish_failed_attempt(
                database=database,
                job_id=job.id,
                attempt_id=attempt.id,
                ingestion_run_id=result["ingestion_run_id"],
                job_status="failed",
                attempt_status="failed",
                error_type="validation_failed",
                error_message=(
                    "Ingestion failed "
                    "data validation."
                ),
            )

        completed_at = utc_now()

        job.ingestion_run_id = result["ingestion_run_id"]
        job.status = "completed"

        job.error_message = None

        job.last_error_type = None

        job.next_retry_at = None

        job.completed_at = completed_at

        attempt.status = "completed"

        attempt.completed_at = completed_at

        database.commit()
        database.refresh(job)

        return job

    except ProviderRateLimitError as error:
        blocked_until = (
            block_provider_after_rate_limit(
                database=database,
                provider_name=
                    job.provider_name,
                reason=str(error),
            )
        )

        return finish_failed_attempt(
            database=database,
            job_id=job.id,
            attempt_id=attempt.id,
            job_status="retry_wait",
            attempt_status="rate_limited",
            error_type="provider_rate_limit",
            error_message=str(error),
            next_retry_at=blocked_until,
        )

    except ProviderTemporaryError as error:
        job = database.get(
            RetrievalJob,
            job_id,
        )

        if (
            job.attempt_count
            < settings.retrieval_max_attempts
        ):
            delay = retry_delay_seconds(
                job.attempt_count
            )

            retry_at = (
                utc_now()
                + timedelta(
                    seconds=delay
                )
            )

            return finish_failed_attempt(
                database=database,
                job_id=job.id,
                attempt_id=attempt.id,
                job_status="retry_wait",
                attempt_status="retry_wait",
                error_type=
                    "temporary_provider_error",
                error_message=str(error),
                next_retry_at=retry_at,
            )

        return finish_failed_attempt(
            database=database,
            job_id=job.id,
            attempt_id=attempt.id,
            job_status="failed",
            attempt_status="failed",
            error_type=
                "temporary_error_max_attempts",
            error_message=str(error),
        )

    except ProviderRequestError as error:
        return finish_failed_attempt(
            database=database,
            job_id=job.id,
            attempt_id=attempt.id,
            job_status="failed",
            attempt_status="failed",
            error_type=
                "permanent_provider_error",
            error_message=str(error),
        )

    except Exception as error:
        database.rollback()
        finish_failed_attempt(
            database=database,
            job_id=job.id,
            attempt_id=attempt.id,
            job_status="failed",
            attempt_status="failed",
            error_type="internal_error",
            error_message=str(error),
        )

        raise


def recover_stale_running_jobs(
    database: Session,
    tracking_run_id: uuid.UUID,
    provider_name: str = DEFAULT_PROVIDER_NAME,
) -> int:
    now = utc_now()
    cutoff = now - timedelta(minutes=settings.retrieval_stale_running_minutes)
    recovered = database.execute(
        update(RetrievalJob).where(
            RetrievalJob.tracking_run_id == tracking_run_id,
            RetrievalJob.provider_name == provider_name,
            RetrievalJob.status == "running",
            or_(RetrievalJob.last_attempt_at.is_(None), RetrievalJob.last_attempt_at <= cutoff),
        ).values(
            status="retry_wait", next_retry_at=now, completed_at=None,
            last_error_type="stale_running_recovered",
            error_message="An abandoned execution was recovered for retry.",
        ).returning(RetrievalJob.id, RetrievalJob.attempt_count)
        .execution_options(synchronize_session=False)
    ).all()
    for job_id, attempt_number in recovered:
        database.execute(
            update(RetrievalJobAttempt).where(
                RetrievalJobAttempt.job_id == job_id,
                RetrievalJobAttempt.attempt_number <= attempt_number,
                RetrievalJobAttempt.status == "running",
            ).values(
                status="failed", error_type="stale_running_recovered",
                error_message="Attempt abandoned during stale-job recovery.", completed_at=now,
            ).execution_options(synchronize_session=False)
        )
    database.commit()
    return len(recovered)


def get_next_eligible_job(
    database: Session,
    tracking_run_id: uuid.UUID,
    provider_name: str,
) -> RetrievalJob | None:
    now = utc_now()

    statement = (
        select(RetrievalJob)
        .where(
            RetrievalJob.tracking_run_id
            == tracking_run_id,

            RetrievalJob.provider_name
            == provider_name,

            or_(
                RetrievalJob.status
                == "pending",

                and_(
                    RetrievalJob.status
                    == "retry_wait",

                    or_(
                        RetrievalJob.next_retry_at
                        .is_(None),

                        RetrievalJob.next_retry_at
                        <= now,
                    ),
                ),
            ),
        )
        .order_by(
            RetrievalJob.created_at,
            RetrievalJob.id,
        )
        .limit(1)
        .execution_options(populate_existing=True)
    )

    return database.scalar(
        statement
    )


def get_next_retry_time(
    database: Session,
    tracking_run_id: uuid.UUID,
    provider_name: str,
) -> datetime | None:
    statement = select(
        func.min(
            RetrievalJob.next_retry_at
        )
    ).where(
        RetrievalJob.tracking_run_id
        == tracking_run_id,

        RetrievalJob.provider_name
        == provider_name,

        RetrievalJob.status
        == "retry_wait",

        RetrievalJob.next_retry_at
        .is_not(None),
    )

    return ensure_utc(
        database.scalar(statement)
    )


def get_job_status_counts(
    database: Session,
    tracking_run_id: uuid.UUID,
    provider_name: str = DEFAULT_PROVIDER_NAME,
) -> dict[str, int]:
    statement = (
        select(
            RetrievalJob.status,
            func.count(
                RetrievalJob.id
            ),
        )
        .where(
            RetrievalJob.tracking_run_id
            == tracking_run_id,
            RetrievalJob.provider_name == provider_name,
        )
        .group_by(
            RetrievalJob.status
        )
    )

    rows = database.execute(
        statement
    ).all()

    counts = {
        "pending": 0,
        "running": 0,
        "completed": 0,
        "retry_wait": 0,
        "failed": 0,
    }

    for status, count in rows:
        counts[status] = count

    return counts


def _synchronize_batch_counters(database: Session, batch: RetrievalBatchRun) -> None:
    database.scalar(
        select(RetrievalBatchRun).where(RetrievalBatchRun.id == batch.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    counts = dict(database.execute(
        select(RetrievalJobAttempt.status, func.count(RetrievalJobAttempt.id))
        .where(RetrievalJobAttempt.batch_run_id == batch.id)
        .group_by(RetrievalJobAttempt.status)
    ).all())
    batch.jobs_completed = counts.get("completed", 0)
    batch.retry_scheduled = counts.get("retry_wait", 0) + counts.get("rate_limited", 0)
    batch.jobs_failed = counts.get("failed", 0)


def run_batch_loop(
    database: Session,
    batch: RetrievalBatchRun,
) -> RetrievalBatchRun:
    batch.status = "running"

    batch.paused_until = None

    batch.stop_reason = None

    batch.completed_at = None

    database.commit()

    recover_stale_running_jobs(
        database=database,
        tracking_run_id=
            batch.tracking_run_id,
        provider_name=batch.provider_name,
    )

    while (
        batch.attempts_started
        < batch.requested_limit
    ):
        blocked_until, reason = (
            get_provider_pause(
                database=database,
                provider_name=
                    batch.provider_name,
            )
        )

        if blocked_until is not None:
            batch.status = (
                "paused_rate_limit"
            )

            batch.paused_until = (
                blocked_until
            )

            batch.stop_reason = reason

            database.commit()
            database.refresh(batch)

            return batch

        job = get_next_eligible_job(
            database=database,
            tracking_run_id=
                batch.tracking_run_id,
            provider_name=
                batch.provider_name,
        )

        if job is None:
            next_retry_at = (
                get_next_retry_time(
                    database=database,
                    tracking_run_id=
                        batch.tracking_run_id,
                    provider_name=
                        batch.provider_name,
                )
            )

            if next_retry_at is not None:
                batch.status = (
                    "waiting_retry"
                )

                batch.paused_until = (
                    next_retry_at
                )

                batch.stop_reason = (
                    "No job is currently "
                    "eligible. Waiting for "
                    "scheduled retry."
                )

                database.commit()
                database.refresh(batch)

                return batch

            counts = get_job_status_counts(
                database=database,
                tracking_run_id=
                    batch.tracking_run_id,
                provider_name=batch.provider_name,
            )

            if counts["running"] > 0 or counts["pending"] > 0:
                batch.status = "waiting_running"
                batch.stop_reason = "Waiting for jobs owned by other workers."
                batch.completed_at = None
                database.commit()
                database.refresh(batch)
                return batch

            if counts["failed"] > 0:
                batch.status = (
                    "completed_with_failures"
                )
            else:
                batch.status = "completed"

            batch.completed_at = utc_now()

            database.commit()
            database.refresh(batch)

            return batch

        attempts_before = (
            job.attempt_count
        )

        try:
            job = execute_retrieval_job(
                database=database,
                job_id=job.id,
                batch_run_id=batch.id,
            )

        except ProviderBatchPaused as error:
            batch.status = (
                "paused_rate_limit"
            )

            batch.paused_until = (
                error.blocked_until
            )

            batch.stop_reason = str(
                error
            )

            database.commit()
            database.refresh(batch)

            return batch

        except Exception as error:
            batch.status = "failed"

            batch.stop_reason = (
                f"Unexpected batch error: "
                f"{error}"
            )

            batch.completed_at = utc_now()

            database.commit()

            raise

        batch = database.get(
            RetrievalBatchRun,
            batch.id,
        )

        job = database.get(
            RetrievalJob,
            job.id,
        )

        database.refresh(batch)
        latest_attempt = database.scalar(select(RetrievalJobAttempt).where(
            RetrievalJobAttempt.job_id == job.id,
            RetrievalJobAttempt.attempt_number == job.attempt_count,
        ))
        if (
            job.attempt_count <= attempts_before or latest_attempt is None
            or latest_attempt.batch_run_id != batch.id
        ):
            continue

        _synchronize_batch_counters(database, batch)

        if job.status == "retry_wait":

            if job.last_error_type == (
                "provider_rate_limit"
            ):
                state = (
                    get_or_create_throttle_state(
                        database,
                        job.provider_name,
                    )
                )

                batch.status = (
                    "paused_rate_limit"
                )

                batch.paused_until = (
                    state.blocked_until
                )

                batch.stop_reason = (
                    job.error_message
                )

                database.commit()
                database.refresh(batch)

                return batch

        database.commit()

    counts = get_job_status_counts(
        database=database,
        tracking_run_id=
            batch.tracking_run_id,
        provider_name=batch.provider_name,
    )

    unfinished = (
        counts["pending"]
        + counts["running"]
        + counts["retry_wait"]
    )

    if unfinished > 0:
        batch.status = "limit_reached"

    elif counts["failed"] > 0:
        batch.status = (
            "completed_with_failures"
        )

    else:
        batch.status = "completed"

    batch.completed_at = utc_now()

    database.commit()
    database.refresh(batch)

    return batch


def create_retrieval_batch(
    database: Session,
    tracking_run_id: uuid.UUID,
    limit: int,
    provider_name: str = (
        DEFAULT_PROVIDER_NAME
    ),
) -> RetrievalBatchRun:
    tracking_run = database.get(
        TrackingRun,
        tracking_run_id,
    )

    if tracking_run is None:
        raise LookupError(
            "Tracking run does not exist."
        )

    provider_name = get_provider_registration(provider_name).provider_name

    batch = RetrievalBatchRun(
        tracking_run_id=tracking_run_id,
        provider_name=provider_name,
        requested_limit=limit,
        status="running",
    )

    database.add(batch)
    database.commit()
    database.refresh(batch)

    return run_batch_loop(
        database=database,
        batch=batch,
    )


def get_retrieval_batch(
    database: Session,
    batch_id: uuid.UUID,
) -> RetrievalBatchRun:
    batch = database.get(
        RetrievalBatchRun,
        batch_id,
    )

    if batch is None:
        raise LookupError(
            "Retrieval batch does not exist."
        )

    return batch


def resume_retrieval_batch(
    database: Session,
    batch_id: uuid.UUID,
) -> RetrievalBatchRun:
    batch = get_retrieval_batch(
        database,
        batch_id,
    )

    if batch.status in {
        "completed",
        "completed_with_failures",
    }:
        return batch

    if (
        batch.status == "limit_reached"
        and batch.attempts_started
        >= batch.requested_limit
    ):
        return batch

    return run_batch_loop(
        database=database,
        batch=batch,
    )


def get_retrieval_progress(
    database: Session,
    tracking_run_id: uuid.UUID,
    provider_name: str = DEFAULT_PROVIDER_NAME,
) -> dict:
    tracking_run = database.get(
        TrackingRun,
        tracking_run_id,
    )

    if tracking_run is None:
        raise LookupError(
            "Tracking run does not exist."
        )

    provider_name = get_provider_registration(provider_name).provider_name

    counts = get_job_status_counts(
        database,
        tracking_run_id,
        provider_name=provider_name,
    )

    total = sum(
        counts.values()
    )

    if total == 0:
        completion_percent = 100.0
        terminal_percent = 100.0

    else:
        completion_percent = round(
            (
                counts["completed"]
                / total
            )
            * 100,
            2,
        )

        terminal_percent = round(
            (
                (
                    counts["completed"]
                    + counts["failed"]
                )
                / total
            )
            * 100,
            2,
        )

    next_retry_at = (
        get_next_retry_time(
            database=database,
            tracking_run_id=
                tracking_run_id,
            provider_name=
                provider_name,
        )
    )

    state = get_or_create_throttle_state(
        database,
        provider_name,
    )

    return {
        "tracking_run_id":
            tracking_run_id,

        "total_jobs":
            total,

        "pending":
            counts["pending"],

        "running":
            counts["running"],

        "completed":
            counts["completed"],

        "retry_wait":
            counts["retry_wait"],

        "failed":
            counts["failed"],

        "completion_percent":
            completion_percent,

        "terminal_percent":
            terminal_percent,

        "next_retry_at":
            next_retry_at,

        "provider_name":
            provider_name,

        "provider_requests_today":
            state.requests_today,

        "provider_daily_budget":
            provider_daily_budget(
                provider_name
            ),

        "provider_blocked_until":
            state.blocked_until,

        "provider_block_reason":
            state.block_reason,
    }