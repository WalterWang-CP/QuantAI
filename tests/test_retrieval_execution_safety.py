from datetime import timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select

import app.retrieval.executor as executor
from app.db.models.retrieval import ProviderThrottleState, RetrievalJobAttempt, RetrievalBatchRun
from test_retrieval_batch import create_database, create_tracking_run_with_jobs


@pytest.mark.parametrize("force", [False, True])
def test_running_job_cannot_start_another_attempt(monkeypatch, force):
    database = create_database()
    _, jobs = create_tracking_run_with_jobs(database, job_count=1)
    job = jobs[0]
    job.status = "running"
    job.attempt_count = 1
    job.last_attempt_at = executor.utc_now()
    attempt = RetrievalJobAttempt(
        job_id=job.id, attempt_number=1, status="running", started_at=executor.utc_now(),
    )
    database.add(attempt)
    database.commit()
    importer = Mock(side_effect=AssertionError("Running job must not call provider"))
    monkeypatch.setattr(executor, "execute_registered_retrieval", importer)
    result = executor.execute_retrieval_job(database, job.id, force=force)
    assert result.status == "running"
    assert result.attempt_count == 1
    assert database.scalar(select(func.count(RetrievalJobAttempt.id))) == 1
    assert database.scalar(select(func.count(ProviderThrottleState.provider_name))) == 0
    importer.assert_not_called()
    database.close()


def test_stale_recovery_closes_abandoned_attempt_and_is_idempotent():
    database = create_database()
    tracking_run, jobs = create_tracking_run_with_jobs(database, job_count=1)
    job = jobs[0]
    job.status = "running"
    job.attempt_count = 1
    job.last_attempt_at = executor.utc_now() - timedelta(days=1)
    attempt = RetrievalJobAttempt(
        job_id=job.id, attempt_number=1, status="running", started_at=job.last_attempt_at,
    )
    database.add(attempt)
    database.commit()
    assert executor.recover_stale_running_jobs(database, tracking_run.id) == 1
    assert executor.recover_stale_running_jobs(database, tracking_run.id) == 0
    database.refresh(attempt)
    assert attempt.status == "failed"
    assert attempt.error_type == "stale_running_recovered"
    assert attempt.completed_at is not None
    database.close()


def test_abandoned_attempt_cannot_overwrite_newer_attempt():
    database = create_database()
    _, jobs = create_tracking_run_with_jobs(database, job_count=1)
    job = jobs[0]
    job.status = "running"
    job.attempt_count = 2
    old = RetrievalJobAttempt(
        job_id=job.id, attempt_number=1, status="failed", started_at=executor.utc_now(),
        error_type="stale_running_recovered", completed_at=executor.utc_now(),
    )
    current = RetrievalJobAttempt(
        job_id=job.id, attempt_number=2, status="running", started_at=executor.utc_now(),
    )
    database.add_all([old, current])
    database.commit()
    result = executor.finish_failed_attempt(
        database, job.id, old.id, "failed", "failed", "late_failure", "Late worker",
    )
    assert result.status == "running"
    assert result.attempt_count == 2
    database.refresh(current)
    database.refresh(old)
    assert current.status == "running"
    assert old.error_type == "stale_running_recovered"
    database.close()


def test_quota_denial_rolls_back_job_claim_and_batch_slot(monkeypatch):
    database = create_database()
    tracking_run, jobs = create_tracking_run_with_jobs(database, job_count=1)
    batch = RetrievalBatchRun(
        tracking_run_id=tracking_run.id, provider_name="alpha_vantage",
        requested_limit=1, status="running",
    )
    database.add(batch)
    database.commit()
    monkeypatch.setattr(executor.settings, "alpha_vantage_batch_daily_budget", 1)
    executor.reserve_provider_request(database, "alpha_vantage")
    with pytest.raises(executor.ProviderBatchPaused):
        executor.execute_retrieval_job(database, jobs[0].id, batch_run_id=batch.id)
    database.refresh(jobs[0])
    database.refresh(batch)
    assert jobs[0].status == "pending"
    assert jobs[0].attempt_count == 0
    assert batch.attempts_started == 0
    assert database.scalar(select(func.count(RetrievalJobAttempt.id))) == 0
    database.close()


def test_batch_does_not_finish_while_another_worker_owns_job():
    database = create_database()
    tracking_run, jobs = create_tracking_run_with_jobs(database, job_count=1)
    jobs[0].status = "running"
    jobs[0].last_attempt_at = executor.utc_now()
    database.commit()
    batch = executor.create_retrieval_batch(database, tracking_run.id, limit=1)
    assert batch.status == "waiting_running"
    assert batch.completed_at is None
    assert batch.attempts_started == 0
    database.close()
