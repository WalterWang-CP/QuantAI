import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
from app.market_data.service import (
    import_alpha_vantage_daily_prices,
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
            required_start = listing.start_date

            reason = (
                "Tracked company historical "
                "price coverage."
            )

        # Never request data before this particular
        # listing actually existed.
        if required_start < listing.start_date:
            required_start = listing.start_date

        required_end = snapshot.effective_date

        if (
            listing.end_date is not None
            and listing.end_date < required_end
        ):
            required_end = listing.end_date

        if required_start > required_end:
            without_listing += 1
            continue

        existing_start, existing_end = (
            get_existing_coverage(
                database=database,
                listing_id=listing.id,
            )
        )

        coverage_complete = (
            existing_start is not None
            and existing_end is not None
            and existing_start <= required_start
            and existing_end >= required_end
        )

        if coverage_complete:
            already_covered += 1
            continue

        # Initial/backfill retrieval requires full
        # history. Compact mode is only safe for
        # recent tail updates.
        full_history = (
            existing_start is None
            or existing_start > required_start
            or (
                date.today() - required_end
            ).days > 180
        )

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
            == required_start,
            RetrievalJob.required_end_date
            == required_end,
        )

        existing_job = database.scalar(
            existing_job_statement
        )

        if existing_job is not None:
            jobs_existing += 1
            continue

        job = RetrievalJob(
            tracking_run_id=tracking_run_id,
            company_id=decision.company_id,
            listing_id=listing.id,
            provider_name=PROVIDER_NAME,
            dataset_name=DATASET_NAME,
            required_start_date=required_start,
            required_end_date=required_end,
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

def execute_retrieval_job(
    database: Session,
    job_id: uuid.UUID,
) -> RetrievalJob:
    job = database.get(
        RetrievalJob,
        job_id,
    )

    if job is None:
        raise LookupError(
            "Retrieval job does not exist."
        )

    if job.status == "completed":
        return job

    if job.provider_name != PROVIDER_NAME:
        raise ValueError(
            "Unsupported provider."
        )

    job.status = "running"
    job.attempt_count += 1

    job.started_at = datetime.now(
        timezone.utc
    )

    job.error_message = None

    database.commit()

    try:
        result = (
            import_alpha_vantage_daily_prices(
                database=database,
                listing_id=job.listing_id,
                full_history=job.full_history,
                start_date=
                    job.required_start_date,
                end_date=
                    job.required_end_date,
            )
        )

        job = database.get(
            RetrievalJob,
            job_id,
        )

        job.ingestion_run_id = (
            result["ingestion_run_id"]
        )

        if result["status"] == "completed":
            job.status = "completed"
        else:
            job.status = "failed"

            job.error_message = (
                "Ingestion did not pass "
                "data validation."
            )

        job.completed_at = datetime.now(
            timezone.utc
        )

        database.commit()
        database.refresh(job)

        return job

    except Exception as error:
        database.rollback()

        job = database.get(
            RetrievalJob,
            job_id,
        )

        if job is not None:
            job.status = "failed"

            job.error_message = str(
                error
            )

            job.completed_at = datetime.now(
                timezone.utc
            )

            database.commit()

        raise