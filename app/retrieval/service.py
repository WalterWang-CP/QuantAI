import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.calendars.service import (
    get_recent_sessions,
)
from app.core.config import settings
from app.db.models.identity import (
    Listing,
    Security,
)
from app.db.models.market_data import (
    DailyPriceBar,
    DataSource,
)
from app.db.models.retrieval import (
    RetrievalJob,
)
from app.db.models.tracking import (
    CompanyTrackingDecision,
    TrackingRun,
)
from app.db.models.universe import (
    RankingSnapshot,
)
from app.market_data.coverage import (
    assess_daily_coverage,
)


PROVIDER_NAME = "alpha_vantage"
DATASET_NAME = "TIME_SERIES_DAILY"


def find_best_listing(
    database: Session,
    company_id: uuid.UUID,
    as_of_date: date,
) -> Listing | None:
    statement = (
        select(Listing)
        .join(
            Security,
            Listing.security_id == Security.id,
        )
        .where(
            Security.company_id == company_id,
            Listing.is_primary.is_(True),
            Listing.start_date <= as_of_date,
        )
        .order_by(
            Listing.start_date.desc()
        )
    )

    listings = list(
        database.scalars(
            statement
        ).all()
    )

    if not listings:
        return None

    # Prefer a listing that was active on the
    # requested historical date.
    for listing in listings:
        if (
            listing.end_date is None
            or listing.end_date >= as_of_date
        ):
            return listing

    # Otherwise use the most recent historical
    # primary listing. This matters for delisted
    # dropout companies.
    return listings[0]


def get_existing_coverage(
    database: Session,
    listing_id: uuid.UUID,
) -> tuple[date | None, date | None]:
    source_statement = select(
        DataSource
    ).where(
        DataSource.provider_name
        == PROVIDER_NAME,
        DataSource.dataset_name
        == DATASET_NAME,
    )

    source = database.scalar(
        source_statement
    )

    if source is None:
        return None, None

    statement = select(
        func.min(
            DailyPriceBar.trading_date
        ),
        func.max(
            DailyPriceBar.trading_date
        ),
    ).where(
        DailyPriceBar.listing_id
        == listing_id,
        DailyPriceBar.source_id
        == source.id,
    )

    result = database.execute(
        statement
    ).one()

    return result[0], result[1]

def plan_retrieval_jobs(
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

    snapshot = database.get(
        RankingSnapshot,
        tracking_run.snapshot_id,
    )

    if snapshot is None:
        raise LookupError(
            "Ranking snapshot does not exist."
        )

    decisions_statement = select(
        CompanyTrackingDecision
    ).where(
        CompanyTrackingDecision.run_id
        == tracking_run_id
    )

    decisions = list(
        database.scalars(
            decisions_statement
        ).all()
    )

    jobs_created = 0
    jobs_existing = 0
    already_covered = 0
    without_listing = 0

    for decision in decisions:
        listing = find_best_listing(
            database=database,
            company_id=decision.company_id,
            as_of_date=snapshot.effective_date,
        )

        if listing is None:
            without_listing += 1
            continue

        # ---------------------------------
        # Determine required research range
        # ---------------------------------

        if (
            decision.elite_tracking
            and decision.historical_backfill_start
            is not None
        ):
            required_start = (
                decision.historical_backfill_start
            )

            reason = (
                "Elite historical price backfill."
            )

        else:
            required_start = (
                listing.start_date
            )

            reason = (
                "Tracked company historical "
                "price coverage."
            )

        # Never request data before this
        # specific listing existed.
        if (
            required_start
            < listing.start_date
        ):
            required_start = (
                listing.start_date
            )

        required_end = (
            snapshot.effective_date
        )

        # If the listing ended before the
        # snapshot date, stop at the listing end.
        if (
            listing.end_date is not None
            and listing.end_date
            < required_end
        ):
            required_end = (
                listing.end_date
            )

        if (
            required_start
            > required_end
        ):
            without_listing += 1
            continue

        # ---------------------------------
        # Calendar-aware coverage analysis
        # ---------------------------------

        coverage = assess_daily_coverage(
            database=database,
            listing_id=listing.id,
            provider_name=PROVIDER_NAME,
            dataset_name=DATASET_NAME,
            start_date=required_start,
            end_date=required_end,
        )

        # Every expected exchange session
        # is already present.
        if (
            coverage.missing_session_count
            == 0
        ):
            already_covered += 1
            continue

        # ---------------------------------
        # Determine actual missing range
        # ---------------------------------

        first_gap = coverage.gaps[0]

        last_gap = coverage.gaps[-1]

        job_start_date = (
            first_gap.start_date
        )

        job_end_date = (
            last_gap.end_date
        )

        # ---------------------------------
        # Decide compact vs full-history
        # ---------------------------------

        full_history = requires_full_history(
            exchange_code=
                listing.exchange_code,

            missing_start_date=
                job_start_date,
        )

        # Add useful audit information.
        reason = (
            f"{reason} "
            f"Missing "
            f"{coverage.missing_session_count} "
            f"expected trading sessions "
            f"across "
            f"{len(coverage.gaps)} "
            f"gap(s)."
        )

        if full_history:
            reason += (
                " Missing coverage extends "
                "beyond the provider's "
                "compact recent-data window."
            )

        else:
            reason += (
                " Missing coverage is within "
                "the provider's compact "
                "recent-data window."
            )

        # ---------------------------------
        # Avoid duplicate retrieval jobs
        # ---------------------------------

        existing_job_statement = select(
            RetrievalJob
        ).where(
            RetrievalJob.tracking_run_id
            == tracking_run_id,

            RetrievalJob.listing_id
            == listing.id,

            RetrievalJob.provider_name
            == PROVIDER_NAME,

            RetrievalJob.dataset_name
            == DATASET_NAME,

            RetrievalJob.required_start_date
            == job_start_date,

            RetrievalJob.required_end_date
            == job_end_date,
        )

        existing_job = database.scalar(
            existing_job_statement
        )

        if existing_job is not None:
            jobs_existing += 1
            continue

        # ---------------------------------
        # Create retrieval job
        # ---------------------------------

        job = RetrievalJob(
            tracking_run_id=tracking_run_id,
            company_id=decision.company_id,
            listing_id=listing.id,

            provider_name=PROVIDER_NAME,
            dataset_name=DATASET_NAME,

            required_start_date=job_start_date,
            required_end_date=job_end_date,

            full_history=full_history,

            status="pending",

            reason=reason,
        )

        database.add(job)

        jobs_created += 1

    database.commit()

    return {
        "tracking_run_id":
            tracking_run_id,

        "tracked_companies":
            len(decisions),

        "jobs_created":
            jobs_created,

        "jobs_already_exist":
            jobs_existing,

        "already_covered":
            already_covered,

        "companies_without_listing":
            without_listing,
    }

def requires_full_history(
    exchange_code: str,
    missing_start_date: date,
    as_of_date: date | None = None,
) -> bool:
    if as_of_date is None:
        as_of_date = date.today()

    recent_sessions = (
        get_recent_sessions(
            exchange_code=
                exchange_code,
            end_date=as_of_date,
            count=(
                settings
                .alpha_vantage_compact_points
            ),
        )
    )

    if not recent_sessions:
        return True

    compact_start_date = (
        recent_sessions[0]
    )

    return (
        missing_start_date
        < compact_start_date
    )

def get_retrieval_jobs(
    database: Session,
    tracking_run_id: uuid.UUID,
) -> list[RetrievalJob]:
    statement = (
        select(RetrievalJob)
        .where(
            RetrievalJob.tracking_run_id
            == tracking_run_id
        )
        .order_by(
            RetrievalJob.created_at,
            RetrievalJob.id,
        )
    )

    return list(
        database.scalars(
            statement
        ).all()
    )

