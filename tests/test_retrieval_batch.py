import uuid
from datetime import (
    date,
    timedelta,
)

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.retrieval.executor as executor

from app.db.database import Base
from app.db.models.identity import (
    Company,
    Listing,
    Security,
)
from app.db.models.retrieval import (
    ProviderThrottleState,
    RetrievalJob,
)
from app.db.models.tracking import (
    TrackingRun,
)
from app.db.models.universe import (
    RankingSnapshot,
)
from app.providers.errors import (
    ProviderRateLimitError,
    ProviderTemporaryError,
)


def create_database():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )

    Base.metadata.create_all(
        engine
    )

    return Session(engine)


def create_tracking_run_with_jobs(
    database: Session,
    job_count: int,
):
    snapshot = RankingSnapshot(
        ranking_date=date(
            2020,
            12,
            31,
        ),
        effective_date=date(
            2021,
            1,
            4,
        ),
        ranking_metric="test_metric",
        base_currency="USD",
    )

    database.add(snapshot)
    database.flush()

    tracking_run = TrackingRun(
        snapshot_id=snapshot.id,
        policy_name="Test Policy",
        policy_hash="a" * 64,
        policy_json={
            "name": "Test Policy"
        },
        engine_version="1.0",
    )

    database.add(tracking_run)
    database.flush()

    jobs = []

    for index in range(
        job_count
    ):
        company = Company(
            legal_name=(
                f"Company {index}"
            ),
            country_code="US",
        )

        database.add(company)
        database.flush()

        security = Security(
            company_id=company.id,
            name=(
                f"Security {index}"
            ),
            security_type=
                "common_stock",
            start_date=date(
                2000,
                1,
                1,
            ),
        )

        database.add(security)
        database.flush()

        listing = Listing(
            security_id=security.id,
            ticker=f"T{index}",
            exchange_code="TEST",
            currency_code="USD",
            start_date=date(
                2000,
                1,
                1,
            ),
            is_primary=True,
        )

        database.add(listing)
        database.flush()

        job = RetrievalJob(
            tracking_run_id=
                tracking_run.id,
            company_id=company.id,
            listing_id=listing.id,
            provider_name=
                "alpha_vantage",
            dataset_name=
                "TIME_SERIES_DAILY",
            required_start_date=date(
                2020,
                1,
                1,
            ),
            required_end_date=date(
                2020,
                12,
                31,
            ),
            full_history=True,
            status="pending",
            reason="Test job.",
        )

        database.add(job)
        jobs.append(job)

    database.commit()

    return tracking_run, jobs


def successful_import(
    database,
    listing_id,
    full_history,
    start_date=None,
    end_date=None,
):
    return {
        "ingestion_run_id":
            uuid.uuid4(),
        "status":
            "completed",
    }


def test_batch_completes_multiple_jobs(
    monkeypatch,
):
    database = create_database()

    tracking_run, jobs = (
        create_tracking_run_with_jobs(
            database,
            job_count=2,
        )
    )

    monkeypatch.setattr(
        executor,
        "import_alpha_vantage_daily_prices",
        successful_import,
    )

    batch = (
        executor.create_retrieval_batch(
            database=database,
            tracking_run_id=
                tracking_run.id,
            limit=2,
        )
    )

    assert batch.status == "completed"

    assert batch.attempts_started == 2

    assert batch.jobs_completed == 2

    for job in jobs:
        refreshed_job = database.get(
            RetrievalJob,
            job.id,
        )

        assert (
            refreshed_job.status
            == "completed"
        )

        assert (
            refreshed_job.attempt_count
            == 1
        )


def test_rate_limit_pauses_and_resumes_batch(
    monkeypatch,
):
    database = create_database()

    tracking_run, jobs = (
        create_tracking_run_with_jobs(
            database,
            job_count=2,
        )
    )

    def rate_limited_import(
        database,
        listing_id,
        full_history,
        start_date=None,
        end_date=None,
    ):
        raise ProviderRateLimitError(
            "Daily API limit reached."
        )

    monkeypatch.setattr(
        executor,
        "import_alpha_vantage_daily_prices",
        rate_limited_import,
    )

    batch = (
        executor.create_retrieval_batch(
            database=database,
            tracking_run_id=
                tracking_run.id,
            limit=3,
        )
    )

    assert (
        batch.status
        == "paused_rate_limit"
    )

    refreshed_jobs = [
        database.get(
            RetrievalJob,
            job.id,
        )
        for job in jobs
    ]

    retry_jobs = [
        job
        for job in refreshed_jobs
        if job.status == "retry_wait"
    ]

    pending_jobs = [
        job
        for job in refreshed_jobs
        if job.status == "pending"
    ]

    assert len(retry_jobs) == 1
    assert len(pending_jobs) == 1

    rate_limited_job = retry_jobs[0]

    assert (
        rate_limited_job.last_error_type
        == "provider_rate_limit"
    )

    throttle = database.get(
        ProviderThrottleState,
        "alpha_vantage",
    )

    throttle.blocked_until = (
        executor.utc_now()
        - timedelta(
            seconds=1
        )
    )

    throttle.block_reason = None

    throttle.requests_today = 0

    rate_limited_job.next_retry_at = (
        executor.utc_now()
        - timedelta(
            seconds=1
        )
    )

    database.commit()

    monkeypatch.setattr(
        executor,
        "import_alpha_vantage_daily_prices",
        successful_import,
    )

    batch = (
        executor.resume_retrieval_batch(
            database=database,
            batch_id=batch.id,
        )
    )

    assert batch.status == "completed"

    assert (
        database.get(
            RetrievalJob,
            jobs[0].id,
        ).status
        == "completed"
    )

    assert (
        database.get(
            RetrievalJob,
            jobs[1].id,
        ).status
        == "completed"
    )


def test_temporary_failure_retries(
    monkeypatch,
):
    database = create_database()

    tracking_run, jobs = (
        create_tracking_run_with_jobs(
            database,
            job_count=1,
        )
    )

    def temporary_failure(
        database,
        listing_id,
        full_history,
        start_date=None,
        end_date=None,
    ):
        raise ProviderTemporaryError(
            "Temporary provider failure."
        )

    monkeypatch.setattr(
        executor,
        "import_alpha_vantage_daily_prices",
        temporary_failure,
    )

    job = (
        executor.execute_retrieval_job(
            database=database,
            job_id=jobs[0].id,
        )
    )

    assert job.status == "retry_wait"

    assert job.attempt_count == 1

    assert job.next_retry_at is not None

    job.next_retry_at = (
        executor.utc_now()
        - timedelta(
            seconds=1
        )
    )

    database.commit()

    monkeypatch.setattr(
        executor,
        "import_alpha_vantage_daily_prices",
        successful_import,
    )

    job = (
        executor.execute_retrieval_job(
            database=database,
            job_id=job.id,
        )
    )

    assert job.status == "completed"

    assert job.attempt_count == 2


def test_stale_running_job_is_recovered():
    database = create_database()

    tracking_run, jobs = (
        create_tracking_run_with_jobs(
            database,
            job_count=1,
        )
    )

    job = jobs[0]

    job.status = "running"

    job.last_attempt_at = (
        executor.utc_now()
        - timedelta(
            minutes=30
        )
    )

    database.commit()

    recovered = (
        executor.recover_stale_running_jobs(
            database=database,
            tracking_run_id=
                tracking_run.id,
        )
    )

    assert recovered == 1

    job = database.get(
        RetrievalJob,
        job.id,
    )

    assert job.status == "retry_wait"

    assert (
        job.last_error_type
        == "stale_running_recovered"
    )