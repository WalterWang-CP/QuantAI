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
)
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.retrieval import (
    ProviderThrottleState,
    RetrievalBatchRun,
    RetrievalJob,
    RetrievalJobAttempt,
)
from app.db.models.tracking import TrackingRun
from app.market_data.service import (
    import_alpha_vantage_daily_prices,
)
from app.providers.errors import (
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTemporaryError,
)


PROVIDER_NAME = "alpha_vantage"


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
    if provider_name == "alpha_vantage":
        return (
            settings
            .alpha_vantage_batch_daily_budget
        )

    return None


def get_or_create_throttle_state(
    database: Session,
    provider_name: str,
) -> ProviderThrottleState:
    state = database.get(
        ProviderThrottleState,
        provider_name,
    )

    today = utc_now().date()

    if state is None:
        state = ProviderThrottleState(
            provider_name=provider_name,
            quota_date=today,
            requests_today=0,
        )

        database.add(state)
        database.commit()
        database.refresh(state)

        return state

    if state.quota_date != today:
        state.quota_date = today
        state.requests_today = 0
        state.blocked_until = None
        state.block_reason = None

        database.commit()
        database.refresh(state)

    blocked_until = ensure_utc(
        state.blocked_until
    )

    if (
        blocked_until is not None
        and blocked_until <= utc_now()
    ):
        state.blocked_until = None
        state.block_reason = None

        database.commit()
        database.refresh(state)

    return state


def get_provider_pause(
    database: Session,
    provider_name: str,
) -> tuple[
    datetime | None,
    str | None,
]:
    state = get_or_create_throttle_state(
        database,
        provider_name,
    )

    blocked_until = ensure_utc(
        state.blocked_until
    )

    if (
        blocked_until is not None
        and blocked_until > utc_now()
    ):
        return (
            blocked_until,
            state.block_reason,
        )

    budget = provider_daily_budget(
        provider_name
    )

    if (
        budget is not None
        and state.requests_today >= budget
    ):
        blocked_until = next_utc_midnight()

        state.blocked_until = blocked_until

        state.block_reason = (
            "Local daily provider safety "
            "budget reached."
        )

        database.commit()

        return (
            blocked_until,
            state.block_reason,
        )

    return None, None


def reserve_provider_request(
    database: Session,
    provider_name: str,
) -> None:
    blocked_until, reason = (
        get_provider_pause(
            database,
            provider_name,
        )
    )

    if blocked_until is not None:
        raise ProviderBatchPaused(
            reason
            or "Provider is temporarily paused.",
            blocked_until,
        )

    state = get_or_create_throttle_state(
        database,
        provider_name,
    )

    state.requests_today += 1

    state.last_request_at = utc_now()

    database.commit()


def block_provider_after_rate_limit(
    database: Session,
    provider_name: str,
    reason: str,
) -> datetime:
    state = get_or_create_throttle_state(
        database,
        provider_name,
    )

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


def finish_failed_attempt(
    database: Session,
    job_id: uuid.UUID,
    attempt_id: uuid.UUID,
    job_status: str,
    attempt_status: str,
    error_type: str,
    error_message: str,
    next_retry_at: datetime | None = None,
) -> RetrievalJob:
    now = utc_now()

    job = database.get(
        RetrievalJob,
        job_id,
    )

    attempt = database.get(
        RetrievalJobAttempt,
        attempt_id,
    )

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
    job = database.get(
        RetrievalJob,
        job_id,
    )

    if job is None:
        raise LookupError(
            "Retrieval job does not exist."
        )

    if job.status == "completed":
        return job

    if (
        job.status == "failed"
        and not force
    ):
        return job

    now = utc_now()

    next_retry_at = ensure_utc(
        job.next_retry_at
    )

    if (
        job.status == "retry_wait"
        and next_retry_at is not None
        and next_retry_at > now
        and not force
    ):
        return job

    reserve_provider_request(
        database=database,
        provider_name=job.provider_name,
    )

    job = database.get(
        RetrievalJob,
        job_id,
    )

    job.status = "running"

    job.attempt_count += 1

    job.last_attempt_at = now

    job.next_retry_at = None

    job.error_message = None

    job.last_error_type = None

    job.completed_at = None

    if job.started_at is None:
        job.started_at = now

    attempt = RetrievalJobAttempt(
        job_id=job.id,
        batch_run_id=batch_run_id,
        attempt_number=job.attempt_count,
        status="running",
        started_at=now,
    )

    database.add(attempt)

    database.commit()
    database.refresh(attempt)

    try:
        result = (
            import_alpha_vantage_daily_prices(
                database=database,
                listing_id=job.listing_id,
                full_history=job.full_history,
                start_date=
                    job.required_start_date,
                end_date=
                    job.required_end_date,
            )
        )

        job = database.get(
            RetrievalJob,
            job_id,
        )

        attempt = database.get(
            RetrievalJobAttempt,
            attempt.id,
        )

        job.ingestion_run_id = (
            result["ingestion_run_id"]
        )

        if result["status"] != "completed":
            return finish_failed_attempt(
                database=database,
                job_id=job.id,
                attempt_id=attempt.id,
                job_status="failed",
                attempt_status="failed",
                error_type="validation_failed",
                error_message=(
                    "Ingestion failed "
                    "data validation."
                ),
            )

        completed_at = utc_now()

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
) -> int:
    cutoff = (
        utc_now()
        - timedelta(
            minutes=(
                settings
                .retrieval_stale_running_minutes
            )
        )
    )

    statement = select(
        RetrievalJob
    ).where(
        RetrievalJob.tracking_run_id
        == tracking_run_id,
        RetrievalJob.status
        == "running",
        or_(
            RetrievalJob.last_attempt_at
            .is_(None),

            RetrievalJob.last_attempt_at
            <= cutoff,
        ),
    )

    jobs = list(
        database.scalars(
            statement
        ).all()
    )

    now = utc_now()

    for job in jobs:
        job.status = "retry_wait"

        job.next_retry_at = now

        job.last_error_type = (
            "stale_running_recovered"
        )

        job.error_message = (
            "A previous execution stopped "
            "while this job was running. "
            "The job was recovered for retry."
        )

    if jobs:
        database.commit()

    return len(jobs)


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
            == tracking_run_id
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
            )

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

        if (
            job.attempt_count
            > attempts_before
        ):
            batch.attempts_started += 1

        if job.status == "completed":
            batch.jobs_completed += 1

        elif job.status == "retry_wait":
            batch.retry_scheduled += 1

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

        elif job.status == "failed":
            batch.jobs_failed += 1

        database.commit()

    counts = get_job_status_counts(
        database=database,
        tracking_run_id=
            batch.tracking_run_id,
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
) -> RetrievalBatchRun:
    tracking_run = database.get(
        TrackingRun,
        tracking_run_id,
    )

    if tracking_run is None:
        raise LookupError(
            "Tracking run does not exist."
        )

    batch = RetrievalBatchRun(
        tracking_run_id=tracking_run_id,
        provider_name=PROVIDER_NAME,
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
) -> dict:
    tracking_run = database.get(
        TrackingRun,
        tracking_run_id,
    )

    if tracking_run is None:
        raise LookupError(
            "Tracking run does not exist."
        )

    counts = get_job_status_counts(
        database,
        tracking_run_id,
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
                PROVIDER_NAME,
        )
    )

    state = get_or_create_throttle_state(
        database,
        PROVIDER_NAME,
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
            PROVIDER_NAME,

        "provider_requests_today":
            state.requests_today,

        "provider_daily_budget":
            provider_daily_budget(
                PROVIDER_NAME
            ),

        "provider_blocked_until":
            state.blocked_until,

        "provider_block_reason":
            state.block_reason,
    }