"""Run on SQLite and, when configured, PostgreSQL in a private test schema.

Set QUANTAI_TEST_DATABASE_URL to enable the PostgreSQL cases.
"""
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

import app.retrieval.executor as executor
from app.db.database import Base
from app.db.models.market_data import DataSource, IngestionRun
from app.db.models.retrieval import (
    ProviderThrottleState, RetrievalBatchRun, RetrievalJob, RetrievalJobAttempt,
)
from test_retrieval_batch import create_tracking_run_with_jobs


@pytest.fixture(params=["sqlite", "postgresql"])
def concurrent_case(request, tmp_path, monkeypatch):
    monkeypatch.setattr(executor.settings, "alpha_vantage_batch_daily_budget", 20)
    monkeypatch.setattr(executor.settings, "alpha_vantage_full_history_enabled", True)
    schema = None
    if request.param == "postgresql":
        url = os.getenv("QUANTAI_TEST_DATABASE_URL")
        if not url:
            pytest.skip("Set QUANTAI_TEST_DATABASE_URL to run PostgreSQL concurrency checks")
        parsed = make_url(url)
        if parsed.get_backend_name() != "postgresql":
            pytest.fail("QUANTAI_TEST_DATABASE_URL must use PostgreSQL")
        root_engine = create_engine(parsed.set(drivername="postgresql+psycopg"))
        schema = "quantai_test_" + uuid.uuid4().hex
        with root_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = root_engine.execution_options(schema_translate_map={None: schema})
    else:
        root_engine = create_engine(
            f"sqlite+pysqlite:///{tmp_path / 'concurrency.sqlite'}",
            connect_args={"check_same_thread": False, "timeout": 15},
        )
        @event.listens_for(root_engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        engine = root_engine
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as database:
            run, jobs = create_tracking_run_with_jobs(database, job_count=2)
            source = DataSource(provider_name="alpha_vantage", dataset_name="TIME_SERIES_DAILY")
            database.add(source)
            database.commit()
            yield engine, run.id, [job.id for job in jobs], source.id
    finally:
        if schema is not None:
            with root_engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root_engine.dispose()


def completed_result(database, source_id, listing_id):
    ingestion = IngestionRun(
        source_id=source_id, listing_id=listing_id, requested_symbol="TEST",
        full_history=False, status="completed",
    )
    database.add(ingestion)
    database.commit()
    return {"ingestion_run_id": ingestion.id, "status": "completed"}


def execute(engine, job_id, batch_id=None, force=False):
    with Session(engine, autoflush=False) as database:
        job = executor.execute_retrieval_job(database, job_id, batch_run_id=batch_id, force=force)
        return job.status


def synchronized_validation(monkeypatch, participants=2):
    original = executor.validate_provider_capability
    barrier = threading.Barrier(participants)

    def validate(job):
        original(job)
        barrier.wait(timeout=5)

    monkeypatch.setattr(executor, "validate_provider_capability", validate)


def test_two_workers_claim_same_pending_job_once(concurrent_case, monkeypatch):
    engine, _, jobs, source_id = concurrent_case
    synchronized_validation(monkeypatch)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def importer(database, listing_id, **kwargs):
        calls.append(listing_id)
        entered.set()
        assert release.wait(timeout=5)
        return completed_result(database, source_id, listing_id)

    monkeypatch.setattr(executor, "execute_registered_retrieval", importer)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(execute, engine, jobs[0]) for _ in range(2)]
        try:
            assert entered.wait(timeout=5)
        finally:
            release.set()
        statuses = [future.result(timeout=10) for future in futures]
    assert "completed" in statuses
    assert len(calls) == 1
    with Session(engine) as database:
        assert database.get(RetrievalJob, jobs[0]).attempt_count == 1
        assert database.scalar(select(func.count(RetrievalJobAttempt.id))) == 1
        assert database.get(ProviderThrottleState, "alpha_vantage").requests_today == 1


@pytest.mark.parametrize("old_quota", [False, True])
def test_quota_reservations_cannot_exceed_budget(concurrent_case, monkeypatch, old_quota):
    engine, _, _, _ = concurrent_case
    monkeypatch.setattr(executor.settings, "alpha_vantage_batch_daily_budget", 2)
    if old_quota:
        with Session(engine) as database:
            database.add(ProviderThrottleState(
                provider_name="alpha_vantage", quota_date=executor.utc_now().date() - timedelta(days=1),
                requests_today=99,
            ))
            database.commit()
    barrier = threading.Barrier(6)

    def reserve():
        with Session(engine, autoflush=False) as database:
            barrier.wait(timeout=5)
            try:
                executor.reserve_provider_request(database, "alpha_vantage")
                return True
            except executor.ProviderBatchPaused:
                return False

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(reserve) for _ in range(6)]
        accepted = [future.result(timeout=15) for future in futures]
    assert sum(accepted) == 2
    with Session(engine) as database:
        state = database.get(ProviderThrottleState, "alpha_vantage")
        assert state.requests_today == 2
        assert state.quota_date == executor.utc_now().date()
        assert database.scalar(select(func.count(ProviderThrottleState.provider_name))) == 1


def test_different_jobs_compete_for_last_quota_slot(concurrent_case, monkeypatch):
    engine, _, jobs, source_id = concurrent_case
    monkeypatch.setattr(executor.settings, "alpha_vantage_batch_daily_budget", 1)
    synchronized_validation(monkeypatch)
    calls = []

    def importer(database, listing_id, **kwargs):
        calls.append(listing_id)
        return completed_result(database, source_id, listing_id)

    def worker(job_id):
        try:
            return execute(engine, job_id)
        except executor.ProviderBatchPaused:
            return "paused"

    monkeypatch.setattr(executor, "execute_registered_retrieval", importer)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, job_id) for job_id in jobs]
        assert sorted(future.result(timeout=10) for future in futures) == ["completed", "paused"]
    assert len(calls) == 1
    with Session(engine) as database:
        assert database.scalar(select(func.count(RetrievalJobAttempt.id))) == 1
        states = [database.get(RetrievalJob, job_id) for job_id in jobs]
        assert sorted(job.status for job in states) == ["completed", "pending"]
        assert sum(job.attempt_count for job in states) == 1
        assert database.get(ProviderThrottleState, "alpha_vantage").requests_today == 1


def test_late_response_cannot_replace_recovered_attempt_result(concurrent_case, monkeypatch):
    engine, tracking_run_id, jobs, source_id = concurrent_case
    entered, release = threading.Event(), threading.Event()
    count = 0
    mutex = threading.Lock()

    def importer(database, listing_id, **kwargs):
        nonlocal count
        with mutex:
            count += 1
            this_call = count
        if this_call == 1:
            entered.set()
            assert release.wait(timeout=10)
        return completed_result(database, source_id, listing_id)

    monkeypatch.setattr(executor, "execute_registered_retrieval", importer)
    with ThreadPoolExecutor(max_workers=1) as pool:
        old_worker = pool.submit(execute, engine, jobs[0])
        try:
            assert entered.wait(timeout=5)
            with Session(engine, autoflush=False) as database:
                job = database.get(RetrievalJob, jobs[0])
                job.last_attempt_at = executor.utc_now() - timedelta(days=1)
                database.commit()
                assert executor.recover_stale_running_jobs(database, tracking_run_id) == 1
                assert executor.execute_retrieval_job(database, jobs[0]).status == "completed"
                newest_ingestion_id = database.get(RetrievalJob, jobs[0]).ingestion_run_id
        finally:
            release.set()
        assert old_worker.result(timeout=10) == "completed"
    with Session(engine) as database:
        job = database.get(RetrievalJob, jobs[0])
        assert job.attempt_count == 2
        assert job.ingestion_run_id == newest_ingestion_id
        attempts = database.scalars(select(RetrievalJobAttempt).order_by(RetrievalJobAttempt.attempt_number)).all()
        assert [attempt.status for attempt in attempts] == ["failed", "completed"]
        assert attempts[0].error_type == "stale_running_recovered"
        assert all(attempt.completed_at is not None for attempt in attempts)


def test_workers_cannot_exceed_batch_attempt_limit(concurrent_case, monkeypatch):
    engine, run_id, jobs, source_id = concurrent_case
    with Session(engine) as database:
        batch = RetrievalBatchRun(
            tracking_run_id=run_id, provider_name="alpha_vantage", requested_limit=1, status="running",
        )
        database.add(batch)
        database.commit()
        batch_id = batch.id
    synchronized_validation(monkeypatch)
    calls = []

    def importer(database, listing_id, **kwargs):
        calls.append(listing_id)
        return completed_result(database, source_id, listing_id)

    monkeypatch.setattr(executor, "execute_registered_retrieval", importer)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(execute, engine, job_id, batch_id) for job_id in jobs]
        assert sorted(future.result(timeout=10) for future in futures) == ["completed", "pending"]
    assert len(calls) == 1
    with Session(engine) as database:
        assert database.get(RetrievalBatchRun, batch_id).attempts_started == 1
        assert database.scalar(select(func.count(RetrievalJobAttempt.id))) == 1
        assert database.get(ProviderThrottleState, "alpha_vantage").requests_today == 1


def test_concurrent_recovery_claims_stale_job_once(concurrent_case):
    engine, run_id, jobs, _ = concurrent_case
    with Session(engine) as database:
        job = database.get(RetrievalJob, jobs[0])
        job.status = "running"
        job.attempt_count = 1
        job.last_attempt_at = executor.utc_now() - timedelta(days=1)
        database.add(RetrievalJobAttempt(
            job_id=job.id, attempt_number=1, status="running", started_at=job.last_attempt_at,
        ))
        database.commit()
    barrier = threading.Barrier(2)

    def recover():
        with Session(engine, autoflush=False) as database:
            barrier.wait(timeout=5)
            return executor.recover_stale_running_jobs(database, run_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(recover) for _ in range(2)]
        assert sum(future.result(timeout=10) for future in futures) == 1
    with Session(engine) as database:
        assert database.get(RetrievalJob, jobs[0]).status == "retry_wait"
        attempt = database.scalar(select(RetrievalJobAttempt))
        assert attempt.status == "failed"
        assert attempt.completed_at is not None


def test_concurrent_batch_loops_do_not_double_count_completion(concurrent_case, monkeypatch):
    engine, run_id, jobs, source_id = concurrent_case
    with Session(engine) as database:
        # Only one job is eligible; both loops initially select that job.
        database.get(RetrievalJob, jobs[1]).status = "completed"
        batch = RetrievalBatchRun(
            tracking_run_id=run_id, provider_name="alpha_vantage", requested_limit=1, status="running",
        )
        database.add(batch)
        database.commit()
        batch_id = batch.id
    synchronized_validation(monkeypatch)
    calls = []

    def importer(database, listing_id, **kwargs):
        calls.append(listing_id)
        return completed_result(database, source_id, listing_id)

    def run():
        with Session(engine, autoflush=False) as database:
            batch = database.get(RetrievalBatchRun, batch_id)
            return executor.run_batch_loop(database, batch).status

    monkeypatch.setattr(executor, "execute_registered_retrieval", importer)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        for future in futures:
            future.result(timeout=10)
    assert len(calls) == 1
    with Session(engine) as database:
        batch = database.get(RetrievalBatchRun, batch_id)
        assert batch.attempts_started == 1
        assert batch.jobs_completed == 1
        assert database.scalar(select(func.count(RetrievalJobAttempt.id))) == 1
