from sqlalchemy.orm import Session

from app.market_cap.service import (
    reconstruct_market_caps_batch,
)
from app.retrieval.service import (
    plan_retrieval_jobs,
)
from app.tracking.service import (
    build_tracking_run,
)
from app.universe.market_cap_ranking import (
    approve_market_cap_ranking_snapshot,
    build_market_cap_ranking_snapshot,
)
from app.workflows.schemas import (
    HistoricalUniverseWorkflowRequest,
)


def read_result_value(
    result,
    name: str,
    default=None,
):
    if isinstance(
        result,
        dict,
    ):
        return result.get(
            name,
            default,
        )

    return getattr(
        result,
        name,
        default,
    )


def run_historical_universe_workflow(
    database: Session,
    payload:
        HistoricalUniverseWorkflowRequest,
) -> dict:
    market_cap_result = (
        reconstruct_market_caps_batch(
            database=database,

            valuation_date=
                payload.ranking_date,

            listing_ids=
                payload.listing_ids,

            primary_only=
                payload.primary_only,

            limit=
                payload.market_cap_limit,
        )
    )

    ranking_result = (
        build_market_cap_ranking_snapshot(
            database=database,

            ranking_date=
                payload.ranking_date,

            effective_date=
                payload.effective_date,

            primary_only=
                payload.primary_only,

            minimum_candidates=
                payload.minimum_candidates,
        )
    )

    snapshot_id = read_result_value(
        ranking_result,
        "snapshot_id",
    )

    snapshot_status = (
        read_result_value(
            ranking_result,
            "snapshot_status",
        )
    )

    if (
        payload.auto_approve
        and snapshot_status
        != "approved"
    ):
        approved_snapshot = (
            approve_market_cap_ranking_snapshot(
                database=database,

                snapshot_id=
                    snapshot_id,

                note=(
                    "Automatically approved "
                    "by historical-universe "
                    "workflow."
                ),
            )
        )

        snapshot_status = (
            approved_snapshot.status
        )

    if snapshot_status != "approved":
        return {
            "status":
                "awaiting_snapshot_approval",

            "ranking_date":
                payload.ranking_date,

            "effective_date":
                payload.effective_date,

            "market_cap_target_count":
                market_cap_result[
                    "target_count"
                ],

            "market_cap_completed":
                market_cap_result[
                    "completed"
                ],

            "market_cap_failed":
                market_cap_result[
                    "failed"
                ],

            "snapshot_id":
                snapshot_id,

            "snapshot_status":
                snapshot_status,

            "companies_ranked":
                read_result_value(
                    ranking_result,
                    "companies_ranked",
                ),

            "tracking_run_id":
                None,

            "retrieval_jobs_created":
                None,

            "retrieval_jobs_already_exist":
                None,

            "retrieval_already_covered":
                None,

            "retrieval_companies_without_listing":
                None,
        }

    tracking_run = build_tracking_run(
        database=database,
        snapshot_id=snapshot_id,
    )

    retrieval_result = None

    if payload.create_retrieval_plan:
        retrieval_result = (
            plan_retrieval_jobs(
                database=database,
                tracking_run_id=
                    tracking_run.id,
            )
        )

    return {
        "status":
            "completed",

        "ranking_date":
            payload.ranking_date,

        "effective_date":
            payload.effective_date,

        "market_cap_target_count":
            market_cap_result[
                "target_count"
            ],

        "market_cap_completed":
            market_cap_result[
                "completed"
            ],

        "market_cap_failed":
            market_cap_result[
                "failed"
            ],

        "snapshot_id":
            snapshot_id,

        "snapshot_status":
            snapshot_status,

        "companies_ranked":
            read_result_value(
                ranking_result,
                "companies_ranked",
            ),

        "tracking_run_id":
            tracking_run.id,

        "retrieval_jobs_created":
            (
                read_result_value(
                    retrieval_result,
                    "jobs_created",
                )
                if retrieval_result
                is not None
                else None
            ),

        "retrieval_jobs_already_exist":
            (
                read_result_value(
                    retrieval_result,
                    "jobs_already_exist",
                )
                if retrieval_result
                is not None
                else None
            ),

        "retrieval_already_covered":
            (
                read_result_value(
                    retrieval_result,
                    "already_covered",
                )
                if retrieval_result
                is not None
                else None
            ),

        "retrieval_companies_without_listing":
            (
                read_result_value(
                    retrieval_result,
                    "companies_without_listing",
                )
                if retrieval_result
                is not None
                else None
            ),
    }