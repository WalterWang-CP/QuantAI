import hashlib
import json
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.tracking import (
    CompanyTrackingDecision,
    TrackingRun,
)
from app.db.models.universe import (
    CompanyRanking,
    RankingSnapshot,
)
from app.policy.service import get_active_policy
from app.universe.constants import (
    RECONSTRUCTED_MARKET_CAP_METRIC,
)

TRACKING_ENGINE_VERSION = "1.1"


def subtract_years(
    value: date,
    years: int,
) -> date:
    try:
        return value.replace(
            year=value.year - years
        )

    except ValueError:
        return value.replace(
            year=value.year - years,
            day=28,
        )


def add_years(
    value: date,
    years: int,
) -> date:
    try:
        return value.replace(
            year=value.year + years
        )

    except ValueError:
        return value.replace(
            year=value.year + years,
            day=28,
        )


def create_policy_hash(
    policy_json: dict,
) -> str:
    normalized_policy = json.dumps(
        policy_json,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        normalized_policy.encode("utf-8")
    ).hexdigest()


def get_tracking_decisions(
    database: Session,
    run_id: uuid.UUID,
) -> list[CompanyTrackingDecision]:
    statement = (
        select(CompanyTrackingDecision)
        .where(
            CompanyTrackingDecision.run_id
            == run_id
        )
        .order_by(
            CompanyTrackingDecision.rank.asc().nulls_last()
        )
    )

    return list(
        database.scalars(statement).all()
    )


def create_tracking_input_hash(
    snapshots: list[RankingSnapshot],
    rankings_by_snapshot: dict[uuid.UUID, list[CompanyRanking]],
) -> str:
    """Fingerprint the eligible snapshots and ranks used for this replay."""
    inputs = {
        "snapshots": [
            {
                "id": str(snapshot.id),
                "ranking_date": snapshot.ranking_date.isoformat(),
                "effective_date": snapshot.effective_date.isoformat(),
                "ranking_metric": snapshot.ranking_metric,
                "base_currency": snapshot.base_currency,
                "status": snapshot.status,
                "rankings": [
                    {"company_id": str(ranking.company_id), "rank": ranking.rank}
                    for ranking in rankings_by_snapshot[snapshot.id]
                ],
            }
            for snapshot in snapshots
        ]
    }
    return create_policy_hash(inputs)


def build_tracking_run(
    database: Session,
    snapshot_id: uuid.UUID,
) -> TrackingRun:
    database.flush()
    target_snapshot = database.get(
        RankingSnapshot,
        snapshot_id,
    )

    if target_snapshot is None:
        raise LookupError(
            "Ranking snapshot does not exist."
        )

    allowed_statuses = (
        ("approved",)
        if target_snapshot.ranking_metric == RECONSTRUCTED_MARKET_CAP_METRIC
        else ("legacy", "approved")
    )
    if target_snapshot.status not in allowed_statuses:
        raise ValueError(
            "Ranking snapshots must be approved before tracking decisions "
            "can be built. Legacy snapshots are supported only for "
            "non-reconstructed ranking metrics."
        )

    policy = get_active_policy()

    policy_json = policy.model_dump(
        mode="json"
    )

    policy_hash = create_policy_hash(
        policy_json
    )

    snapshots_statement = (
        select(RankingSnapshot)
        .where(
            RankingSnapshot.ranking_metric == target_snapshot.ranking_metric,
            RankingSnapshot.base_currency == target_snapshot.base_currency,
            RankingSnapshot.effective_date <= target_snapshot.effective_date,
            RankingSnapshot.status.in_(allowed_statuses),
        )
        .order_by(
            RankingSnapshot.effective_date,
            RankingSnapshot.ranking_date,
            RankingSnapshot.id,
        )
    )
    snapshots = list(database.scalars(snapshots_statement).all())
    rankings_by_snapshot: dict[uuid.UUID, list[CompanyRanking]] = {
        snapshot.id: [] for snapshot in snapshots
    }
    rankings_statement = (
        select(CompanyRanking)
        .where(CompanyRanking.snapshot_id.in_(rankings_by_snapshot))
        .order_by(CompanyRanking.snapshot_id, CompanyRanking.company_id)
    )
    for ranking in database.scalars(rankings_statement):
        rankings_by_snapshot[ranking.snapshot_id].append(ranking)

    input_hash = create_tracking_input_hash(snapshots, rankings_by_snapshot)
    existing_statement = select(TrackingRun).where(
        TrackingRun.snapshot_id == snapshot_id,
        TrackingRun.policy_hash == policy_hash,
        TrackingRun.engine_version == TRACKING_ENGINE_VERSION,
        TrackingRun.input_hash == input_hash,
    )
    existing_run = database.scalar(existing_statement)
    if existing_run is not None:
        return existing_run

    company_states: dict[
        uuid.UUID,
        dict,
    ] = {}

    target_decisions = []

    for snapshot in snapshots:
        rankings = rankings_by_snapshot[snapshot.id]

        current_rankings = {
            ranking.company_id: ranking
            for ranking in rankings
        }

        company_ids = (
            set(company_states.keys())
            | set(current_rankings.keys())
        )

        for company_id in company_ids:
            state = company_states.setdefault(
                company_id,
                {
                    "was_main": False,
                    "ever_elite": False,
                    "first_elite_date": None,
                    "historical_backfill_start": None,
                    "dropout_until": None,
                },
            )

            ranking = current_rankings.get(
                company_id
            )

            current_rank = (
                ranking.rank
                if ranking is not None
                else None
            )

            is_main = (
                current_rank is not None
                and current_rank
                <= policy.universe.main_universe_size
            )

            elite_hit = (
                policy.elite_tracking.enabled
                and current_rank is not None
                and current_rank
                <= policy.elite_tracking.threshold
            )

            elite_triggered_now = False

            if (
                elite_hit
                and not state["ever_elite"]
            ):
                elite_triggered_now = True

                state["ever_elite"] = True

                state["first_elite_date"] = (
                    snapshot.effective_date
                )

                state[
                    "historical_backfill_start"
                ] = subtract_years(
                    snapshot.effective_date,
                    policy.elite_tracking
                    .historical_backfill_years,
                )

            dropout_triggered_now = False

            if (
                state["was_main"]
                and not is_main
                and policy.dropout_tracking.enabled
            ):
                dropout_triggered_now = True

                state["dropout_until"] = add_years(
                    snapshot.effective_date,
                    policy.dropout_tracking
                    .tracking_years,
                )

            if is_main:
                state["dropout_until"] = None

            dropout_tracking = (
                policy.dropout_tracking.enabled
                and not is_main
                and state["dropout_until"]
                is not None
                and snapshot.effective_date
                <= state["dropout_until"]
            )

            elite_tracking = (
                policy.elite_tracking.enabled
                and state["ever_elite"]
            )

            should_track = (
                is_main
                or elite_tracking
                or dropout_tracking
            )

            if (
                snapshot.id
                == target_snapshot.id
                and should_track
            ):
                reasons = []

                if is_main:
                    reasons.append(
                        f"Main universe: rank "
                        f"{current_rank} <= "
                        f"{policy.universe.main_universe_size}."
                    )

                if elite_triggered_now:
                    reasons.append(
                        f"Elite tracking triggered: rank "
                        f"{current_rank} <= "
                        f"{policy.elite_tracking.threshold}."
                    )

                elif elite_tracking:
                    reasons.append(
                        "Elite tracking continues from "
                        f"{state['first_elite_date']}."
                    )

                if dropout_triggered_now:
                    reasons.append(
                        "Dropout tracking triggered after "
                        "leaving the main universe."
                    )

                elif dropout_tracking:
                    reasons.append(
                        "Dropout tracking remains active."
                    )

                if dropout_tracking:
                    reasons.append(
                        "Dropout tracking scheduled until "
                        f"{state['dropout_until']}."
                    )

                if elite_tracking:
                    reasons.append(
                        "Historical backfill starts at "
                        f"{state['historical_backfill_start']}."
                    )

                target_decisions.append(
                    {
                        "company_id": company_id,
                        "rank": current_rank,
                        "main_universe": is_main,
                        "elite_tracking":
                            elite_tracking,
                        "elite_triggered_now":
                            elite_triggered_now,
                        "first_elite_date":
                            state["first_elite_date"],
                        "historical_backfill_start":
                            state[
                                "historical_backfill_start"
                            ],
                        "dropout_tracking":
                            dropout_tracking,
                        "dropout_triggered_now":
                            dropout_triggered_now,
                        "dropout_until":
                            state["dropout_until"],
                        "reason": " ".join(reasons),
                    }
                )

            state["was_main"] = is_main

    tracking_run = TrackingRun(
        snapshot_id=snapshot_id,
        policy_name=policy.name,
        policy_hash=policy_hash,
        policy_json=policy_json,
        engine_version=TRACKING_ENGINE_VERSION,
        input_hash=input_hash,
    )

    database.add(tracking_run)
    database.flush()

    for decision_data in target_decisions:
        decision = CompanyTrackingDecision(
            run_id=tracking_run.id,
            **decision_data,
        )

        database.add(decision)

    database.commit()
    database.refresh(tracking_run)

    return tracking_run