import json
from datetime import date, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import Base
from app.db.models.identity import Company, Listing, Security
from app.db.models.market_data import (
    DailyPriceBar,
    DataQualityIssue,
    IngestionRun,
    RawDataArtifact,
)
from app.db.models.retrieval import RetrievalJob
from app.db.models.tracking import CompanyTrackingDecision, TrackingRun
from app.db.models.universe import RankingSnapshot
from app.market_data.coverage import assess_daily_coverage
from app.providers.alpha_vantage import AlphaVantageProvider
from app.providers.base import RawProviderResponse
from app.retrieval.executor import execute_retrieval_job, utc_now
from app.retrieval.service import plan_retrieval_jobs


REQUEST_START = date(2024, 12, 30)
REQUEST_END = date(2025, 1, 3)
EXPECTED_SESSIONS = [
    date(2024, 12, 30),
    date(2024, 12, 31),
    date(2025, 1, 2),
    date(2025, 1, 3),
]


def provider_response(session_dates):
    body = json.dumps({
        "Time Series (Daily)": {
            trading_date.isoformat(): {
                "1. open": "100",
                "2. high": "102",
                "3. low": "99",
                "4. close": "101",
                "5. volume": "1000",
            }
            for trading_date in session_dates
        }
    }).encode("utf-8")
    return RawProviderResponse(body=body, content_type="application/json")


@pytest.fixture
def retrieval_case(monkeypatch, tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    database = Session(engine, autoflush=False)

    monkeypatch.setattr(settings, "alpha_vantage_full_history_enabled", True)
    monkeypatch.setattr(settings, "retrieval_max_attempts", 3)
    monkeypatch.setattr(settings, "retrieval_retry_base_seconds", 60)
    monkeypatch.setattr(settings, "alpha_vantage_batch_daily_budget", 20)
    monkeypatch.setattr("app.market_data.raw_archive.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        "app.market_data.raw_archive.RAW_DATA_ROOT", tmp_path / "data" / "raw"
    )

    company = Company(legal_name="Coverage Test Company", country_code="US")
    database.add(company)
    database.flush()
    security = Security(
        company_id=company.id,
        name="Coverage Test Stock",
        security_type="common_stock",
        start_date=REQUEST_START,
    )
    database.add(security)
    database.flush()
    listing = Listing(
        security_id=security.id,
        ticker="COVERAGE",
        exchange_code="NASDAQ",
        currency_code="USD",
        start_date=REQUEST_START,
        is_primary=True,
    )
    snapshot = RankingSnapshot(
        ranking_date=date(2024, 12, 27),
        effective_date=REQUEST_END,
        ranking_metric="coverage_test",
        base_currency="USD",
    )
    database.add_all([listing, snapshot])
    database.flush()
    tracking_run = TrackingRun(
        snapshot_id=snapshot.id,
        policy_name="Coverage Test",
        policy_hash="c" * 64,
        policy_json={},
        engine_version="1.0",
    )
    database.add(tracking_run)
    database.flush()
    decision = CompanyTrackingDecision(
        run_id=tracking_run.id,
        company_id=company.id,
        rank=900,
        main_universe=True,
        elite_tracking=False,
        dropout_tracking=False,
        reason="Coverage regression test.",
    )
    job = RetrievalJob(
        tracking_run_id=tracking_run.id,
        company_id=company.id,
        listing_id=listing.id,
        provider_name="alpha_vantage",
        dataset_name="TIME_SERIES_DAILY",
        required_start_date=REQUEST_START,
        required_end_date=REQUEST_END,
        full_history=True,
        status="pending",
        reason="Coverage regression test.",
    )
    database.add_all([decision, job])
    database.commit()

    try:
        yield database, tracking_run, listing, job
    finally:
        database.close()
        engine.dispose()


def mock_provider(monkeypatch, responses):
    fetch = Mock(side_effect=[provider_response(dates) for dates in responses])
    monkeypatch.setattr(AlphaVantageProvider, "fetch_daily_response", fetch)
    return fetch


def coverage_for(database, listing):
    return assess_daily_coverage(
        database=database,
        listing_id=listing.id,
        provider_name="alpha_vantage",
        dataset_name="TIME_SERIES_DAILY",
        start_date=REQUEST_START,
        end_date=REQUEST_END,
    )


def make_retry_due(database, job):
    job.next_retry_at = utc_now() - timedelta(seconds=1)
    database.commit()


def test_partial_retrieval_preserves_rows_and_waits_for_retry(
    retrieval_case, monkeypatch
):
    database, _, listing, job = retrieval_case
    mock_provider(monkeypatch, [[date(2024, 12, 31)]])

    result = execute_retrieval_job(database, job.id)
    ingestion = database.get(IngestionRun, result.ingestion_run_id)
    issue = database.scalar(select(DataQualityIssue).where(
        DataQualityIssue.ingestion_run_id == ingestion.id
    ))

    assert result.status == "retry_wait"
    assert result.last_error_type == "incomplete_coverage"
    assert "3 of 4" in result.error_message
    assert result.next_retry_at is not None
    assert result.completed_at is None
    assert ingestion.status == "incomplete"
    assert ingestion.rows_inserted == 1
    assert "3 of 4" in ingestion.error_message
    assert issue.rule_code == "INCOMPLETE_COVERAGE"
    assert issue.severity == "warning"
    assert coverage_for(database, listing).missing_session_count == 3
    assert database.scalar(select(func.count(RawDataArtifact.id))) == 1


def test_incomplete_retrieval_stops_at_attempt_limit(retrieval_case, monkeypatch):
    database, _, _, job = retrieval_case
    monkeypatch.setattr(settings, "retrieval_max_attempts", 2)
    fetch = mock_provider(monkeypatch, [
        [date(2024, 12, 31)],
        [date(2024, 12, 31)],
    ])

    execute_retrieval_job(database, job.id)
    make_retry_due(database, job)
    result = execute_retrieval_job(database, job.id)

    assert result.status == "failed"
    assert result.last_error_type == "incomplete_coverage"
    assert result.attempt_count == 2
    assert result.next_retry_at is None
    assert result.completed_at is not None
    assert fetch.call_count == 2
    assert database.scalar(select(func.count(DailyPriceBar.id))) == 1


def test_retry_completes_using_previously_stored_sessions(
    retrieval_case, monkeypatch
):
    database, _, listing, job = retrieval_case
    fetch = mock_provider(monkeypatch, [
        [date(2024, 12, 31)],
        [date(2024, 12, 30), date(2025, 1, 2), date(2025, 1, 3)],
    ])

    execute_retrieval_job(database, job.id)
    make_retry_due(database, job)
    result = execute_retrieval_job(database, job.id)

    assert result.status == "completed"
    assert result.attempt_count == 2
    assert result.error_message is None
    assert result.next_retry_at is None
    assert fetch.call_count == 2
    assert coverage_for(database, listing).missing_session_count == 0
    assert database.scalar(select(func.count(DailyPriceBar.id))) == 4


def test_replanning_reopens_legacy_completed_job(retrieval_case, monkeypatch):
    database, tracking_run, _, job = retrieval_case
    mock_provider(monkeypatch, [[date(2024, 12, 31)]])
    execute_retrieval_job(database, job.id)

    # Simulate a partial job marked completed by the older implementation.
    job.status = "completed"
    job.completed_at = utc_now()
    job.next_retry_at = None
    database.commit()
    old_ingestion_run_id = job.ingestion_run_id

    plan = plan_retrieval_jobs(database, tracking_run.id)

    assert plan["jobs_created"] == 0
    assert plan["jobs_already_exist"] == 1
    assert job.status == "pending"
    assert job.completed_at is None
    assert job.last_error_type == "incomplete_coverage"
    assert job.attempt_count == 1
    assert job.ingestion_run_id == old_ingestion_run_id
    assert database.scalar(select(func.count(RetrievalJob.id))) == 1


def test_complete_retrieval_excludes_market_holiday(retrieval_case, monkeypatch):
    database, _, listing, job = retrieval_case
    mock_provider(monkeypatch, [EXPECTED_SESSIONS])

    result = execute_retrieval_job(database, job.id)
    coverage = coverage_for(database, listing)

    assert result.status == "completed"
    assert coverage.expected_session_count == 4
    assert coverage.missing_session_count == 0
    assert database.scalar(select(func.count(DataQualityIssue.id))) == 0


def test_replanning_keeps_complete_job_completed(retrieval_case, monkeypatch):
    database, tracking_run, _, job = retrieval_case
    mock_provider(monkeypatch, [EXPECTED_SESSIONS])
    execute_retrieval_job(database, job.id)

    plan = plan_retrieval_jobs(database, tracking_run.id)

    assert plan["already_covered"] == 1
    assert plan["jobs_created"] == 0
    assert job.status == "completed"
