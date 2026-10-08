from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.tracking.service as tracking
from app.db.database import Base
from app.db.models.identity import Company
from app.db.models.tracking import CompanyTrackingDecision, TrackingRun
from app.db.models.universe import CompanyRanking, RankingSnapshot
from app.policy.models import ResearchPolicy
from app.tracking.routes import build_tracking
from app.universe.constants import RECONSTRUCTED_MARKET_CAP_METRIC as METRIC


@pytest.fixture
def case(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    database = Session(engine, autoflush=False)
    policy = ResearchPolicy.model_validate({
        "name": "Approval Test",
        "universe": {"main_universe_size": 1000, "ranking_frequency": "yearly"},
        "elite_tracking": {
            "enabled": True, "threshold": 100, "historical_backfill_years": 20,
        },
        "dropout_tracking": {"enabled": True, "tracking_years": 5},
    })
    monkeypatch.setattr(tracking, "get_active_policy", lambda: policy)
    company = Company(legal_name="Approval Test Company", country_code="US")
    database.add(company)
    database.flush()

    def snapshot(year, rank, status="approved", metric=METRIC):
        item = RankingSnapshot(
            ranking_date=date(year, 12, 31),
            effective_date=date(year + 1, 1, 3),
            ranking_metric=metric, base_currency="USD", status=status,
        )
        database.add(item)
        database.flush()
        if rank is not None:
            database.add(CompanyRanking(
                snapshot_id=item.id, company_id=company.id,
                rank=rank, market_cap_usd=100,
            ))
        database.commit()
        return item

    yield database, company, policy, snapshot
    database.close()
    engine.dispose()


def decision(database, run, company):
    return database.scalar(select(CompanyTrackingDecision).where(
        CompanyTrackingDecision.run_id == run.id,
        CompanyTrackingDecision.company_id == company.id,
    ))


@pytest.mark.parametrize("status", ["draft", "rejected", "legacy"])
def test_unapproved_reconstructed_history_cannot_trigger_elite(case, status):
    database, company, _, snapshot = case
    snapshot(2020, 50, status=status)
    target = snapshot(2021, 900)
    run = tracking.build_tracking_run(database, target.id)
    result = decision(database, run, company)
    assert result.main_universe is True
    assert result.elite_tracking is False
    assert result.first_elite_date is None
    assert result.historical_backfill_start is None


@pytest.mark.parametrize("status", ["draft", "rejected", "legacy"])
def test_unapproved_reconstructed_history_cannot_trigger_dropout(case, status):
    database, company, _, snapshot = case
    snapshot(2020, 900, status=status)
    target = snapshot(2021, None)
    run = tracking.build_tracking_run(database, target.id)
    assert decision(database, run, company) is None


def test_approved_history_still_triggers_elite(case):
    database, company, _, snapshot = case
    history = snapshot(2020, 50)
    target = snapshot(2021, 900)
    result = decision(database, tracking.build_tracking_run(database, target.id), company)
    assert result.elite_tracking is True
    assert result.first_elite_date == history.effective_date
    assert result.historical_backfill_start == date(2001, 1, 3)


def test_manual_legacy_history_remains_supported(case):
    database, company, _, snapshot = case
    snapshot(2020, 50, status="legacy", metric="market_cap_usd")
    target = snapshot(2021, 900, status="legacy", metric="market_cap_usd")
    result = decision(database, tracking.build_tracking_run(database, target.id), company)
    assert result.elite_tracking is True


@pytest.mark.parametrize("status", ["draft", "rejected", "legacy"])
def test_unapproved_reconstructed_target_is_rejected(case, status):
    database, _, _, snapshot = case
    target = snapshot(2021, 900, status=status)
    with pytest.raises(ValueError, match="approved"):
        tracking.build_tracking_run(database, target.id)
    assert database.scalar(select(func.count(TrackingRun.id))) == 0


def test_old_engine_cached_run_is_not_reused(case):
    database, _, policy, snapshot = case
    target = snapshot(2021, 900)
    policy_json = policy.model_dump(mode="json")
    old = TrackingRun(
        snapshot_id=target.id, policy_name=policy.name, policy_json=policy_json,
        policy_hash=tracking.create_policy_hash(policy_json), engine_version="1.0",
    )
    database.add(old)
    database.commit()
    rebuilt = tracking.build_tracking_run(database, target.id)
    assert rebuilt.id != old.id
    assert rebuilt.engine_version == "1.1"
    assert len(rebuilt.input_hash) == 64
    assert database.get(TrackingRun, old.id) is not None


def test_approving_history_creates_new_run_and_preserves_old_decision(case):
    database, company, _, snapshot = case
    history = snapshot(2020, 50, status="draft")
    target = snapshot(2021, 900)
    first = tracking.build_tracking_run(database, target.id)
    assert decision(database, first, company).elite_tracking is False
    history.status = "approved"
    database.commit()
    second = tracking.build_tracking_run(database, target.id)
    assert second.id != first.id
    assert second.input_hash != first.input_hash
    assert decision(database, second, company).elite_tracking is True
    assert decision(database, first, company).elite_tracking is False
    assert tracking.build_tracking_run(database, target.id).id == second.id


def test_rejecting_history_cannot_reuse_contaminated_cache(case):
    database, company, _, snapshot = case
    history = snapshot(2020, 50)
    target = snapshot(2021, 900)
    first = tracking.build_tracking_run(database, target.id)
    history.status = "rejected"
    database.commit()
    second = tracking.build_tracking_run(database, target.id)
    assert second.id != first.id
    assert decision(database, first, company).elite_tracking is True
    assert decision(database, second, company).elite_tracking is False


def test_changed_approved_rank_creates_new_run(case):
    database, company, _, snapshot = case
    history = snapshot(2020, 50)
    target = snapshot(2021, 900)
    first = tracking.build_tracking_run(database, target.id)
    rank = database.scalar(select(CompanyRanking).where(
        CompanyRanking.snapshot_id == history.id,
    ))
    rank.rank = 900
    database.commit()
    second = tracking.build_tracking_run(database, target.id)
    assert second.id != first.id
    assert decision(database, second, company).elite_tracking is False
    assert decision(database, first, company).elite_tracking is True


def test_unchanged_inputs_and_ignored_draft_changes_reuse_cache(case):
    database, _, _, snapshot = case
    ignored = snapshot(2020, 50, status="draft")
    target = snapshot(2021, 900)
    first = tracking.build_tracking_run(database, target.id)
    assert tracking.build_tracking_run(database, target.id).id == first.id
    rank = database.scalar(select(CompanyRanking).where(
        CompanyRanking.snapshot_id == ignored.id,
    ))
    rank.rank = 60
    database.commit()
    assert tracking.build_tracking_run(database, target.id).id == first.id
    assert database.scalar(select(func.count(TrackingRun.id))) == 1


def test_future_approved_history_does_not_leak_or_invalidate_cache(case):
    database, company, _, snapshot = case
    target = snapshot(2021, 900)
    first = tracking.build_tracking_run(database, target.id)
    snapshot(2025, 50)
    second = tracking.build_tracking_run(database, target.id)
    assert second.id == first.id
    assert decision(database, second, company).elite_tracking is False


def test_unapproved_target_returns_http_400(case):
    database, _, _, snapshot = case
    target = snapshot(2021, 900, status="draft")
    with pytest.raises(HTTPException) as error:
        build_tracking(target.id, database)
    assert error.value.status_code == 400


def test_target_approval_is_checked_before_cached_run_reuse(case):
    database, _, _, snapshot = case
    target = snapshot(2021, 900)
    first = tracking.build_tracking_run(database, target.id)
    target.status = "draft"
    database.commit()
    with pytest.raises(ValueError, match="approved"):
        tracking.build_tracking_run(database, target.id)
    assert database.get(TrackingRun, first.id) is not None
    assert database.scalar(select(func.count(TrackingRun.id))) == 1
