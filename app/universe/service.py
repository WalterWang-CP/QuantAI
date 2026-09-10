import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.identity import Company
from app.db.models.universe import (
    CompanyRanking,
    RankingSnapshot,
)
from app.policy.service import get_active_policy
from app.universe.schemas import (
    CompanyRankingCreate,
    RankingSnapshotCreate,
)


def create_ranking_snapshot(
    database: Session,
    snapshot_data: RankingSnapshotCreate,
) -> RankingSnapshot:
    snapshot = RankingSnapshot(
        ranking_date=snapshot_data.ranking_date,
        effective_date=snapshot_data.effective_date,
        ranking_metric=snapshot_data.ranking_metric,
        base_currency=snapshot_data.base_currency.upper(),
    )

    database.add(snapshot)
    database.commit()
    database.refresh(snapshot)

    return snapshot


def get_ranking_snapshots(
    database: Session,
) -> list[RankingSnapshot]:
    statement = select(
        RankingSnapshot
    ).order_by(
        RankingSnapshot.ranking_date.desc()
    )

    return list(
        database.scalars(statement).all()
    )


def add_company_ranking(
    database: Session,
    snapshot_id: uuid.UUID,
    ranking_data: CompanyRankingCreate,
) -> CompanyRanking:
    snapshot = database.get(
        RankingSnapshot,
        snapshot_id,
    )

    if snapshot is None:
        raise LookupError(
            "Ranking snapshot does not exist."
        )

    company = database.get(
        Company,
        ranking_data.company_id,
    )

    if company is None:
        raise LookupError(
            "Company does not exist."
        )

    ranking = CompanyRanking(
        snapshot_id=snapshot_id,
        company_id=ranking_data.company_id,
        rank=ranking_data.rank,
        market_cap_usd=ranking_data.market_cap_usd,
    )

    database.add(ranking)

    try:
        database.commit()

    except IntegrityError:
        database.rollback()

        raise ValueError(
            "This company or rank already exists "
            "in the ranking snapshot."
        )

    database.refresh(ranking)

    return ranking


def build_universe_preview(
    database: Session,
    snapshot_id: uuid.UUID,
) -> dict:
    snapshot = database.get(
        RankingSnapshot,
        snapshot_id,
    )

    if snapshot is None:
        raise LookupError(
            "Ranking snapshot does not exist."
        )

    policy = get_active_policy()

    statement = (
        select(
            CompanyRanking,
            Company,
        )
        .join(
            Company,
            CompanyRanking.company_id == Company.id,
        )
        .where(
            CompanyRanking.snapshot_id == snapshot_id,
            CompanyRanking.rank
            <= policy.universe.main_universe_size,
        )
        .order_by(
            CompanyRanking.rank
        )
    )

    rows = database.execute(
        statement
    ).all()

    members = []

    for ranking, company in rows:
        elite_trigger = (
            policy.elite_tracking.enabled
            and ranking.rank
            <= policy.elite_tracking.threshold
        )

        tracking_reason = (
            f"Global rank {ranking.rank} "
            f"is within main universe size "
            f"{policy.universe.main_universe_size}."
        )

        members.append(
            {
                "company_id": company.id,
                "legal_name": company.legal_name,
                "rank": ranking.rank,
                "market_cap_usd": ranking.market_cap_usd,
                "main_universe": True,
                "elite_trigger": elite_trigger,
                "tracking_reason": tracking_reason,
            }
        )

    return {
        "snapshot_id": snapshot.id,
        "ranking_date": snapshot.ranking_date,
        "effective_date": snapshot.effective_date,
        "policy_name": policy.name,
        "main_universe_size":
            policy.universe.main_universe_size,
        "elite_threshold":
            policy.elite_tracking.threshold,
        "member_count": len(members),
        "members": members,
    }