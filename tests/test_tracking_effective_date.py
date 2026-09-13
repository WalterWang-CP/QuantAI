from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.tracking.service as tracking_service

from app.db.database import Base
from app.db.models.identity import Company
from app.db.models.tracking import CompanyTrackingDecision
from app.db.models.universe import (
    CompanyRanking,
    RankingSnapshot,
)
from app.policy.models import ResearchPolicy


def test_future_effective_snapshot_does_not_leak_backward(
    monkeypatch,
):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )

    Base.metadata.create_all(engine)

    database = Session(engine)

    policy = ResearchPolicy.model_validate(
        {
            "name": "Tracking Test",
            "universe": {
                "main_universe_size": 1000,
                "ranking_frequency": "yearly",
            },
            "elite_tracking": {
                "enabled": True,
                "threshold": 100,
                "historical_backfill_years": 20,
            },
            "dropout_tracking": {
                "enabled": True,
                "tracking_years": 5,
            },
        }
    )

    monkeypatch.setattr(
        tracking_service,
        "get_active_policy",
        lambda: policy,
    )

    company = Company(
        legal_name="Synthetic Company",
        country_code="US",
    )

    database.add(company)
    database.flush()

    future_snapshot = RankingSnapshot(
        ranking_date=date(2020, 12, 31),
        effective_date=date(2030, 1, 1),
        ranking_metric="test_metric",
        base_currency="USD",
    )

    target_snapshot = RankingSnapshot(
        ranking_date=date(2021, 12, 31),
        effective_date=date(2022, 1, 3),
        ranking_metric="test_metric",
        base_currency="USD",
    )

    database.add_all(
        [
            future_snapshot,
            target_snapshot,
        ]
    )

    database.flush()

    database.add(
        CompanyRanking(
            snapshot_id=future_snapshot.id,
            company_id=company.id,
            rank=50,
            market_cap_usd=100,
        )
    )

    database.add(
        CompanyRanking(
            snapshot_id=target_snapshot.id,
            company_id=company.id,
            rank=900,
            market_cap_usd=100,
        )
    )

    database.commit()

    run = tracking_service.build_tracking_run(
        database=database,
        snapshot_id=target_snapshot.id,
    )

    statement = select(
        CompanyTrackingDecision
    ).where(
        CompanyTrackingDecision.run_id
        == run.id,
        CompanyTrackingDecision.company_id
        == company.id,
    )

    decision = database.scalar(statement)

    assert decision is not None

    assert decision.main_universe is True

    # Rank 50 exists only in the future-effective
    # snapshot. It must not leak into 2022.
    assert decision.elite_tracking is False
    assert decision.first_elite_date is None