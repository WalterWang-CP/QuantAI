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
from app.identity.resolution_service import (
    get_company_primary_listings,
    get_provider_symbol_segments,
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

    # =====================================
    # Process each tracked company
    # =====================================

    for decision in decisions:
        required_end = (
            snapshot.effective_date
        )

        # ---------------------------------
        # Find ALL historical primary
        # listings for this company.
        # ---------------------------------

        primary_listings = (
            get_company_primary_listings(
                database=database,

                company_id=
                    decision.company_id,

                as_of_date=
                    required_end,
            )
        )

        if not primary_listings:
            without_listing += 1
            continue

        # ---------------------------------
        # Determine the company's requested
        # historical start date.
        # ---------------------------------

        if (
            decision.elite_tracking
            and decision.historical_backfill_start
            is not None
        ):
            required_start = (
                decision
                .historical_backfill_start
            )

            base_reason = (
                "Elite historical price "
                "backfill."
            )

        else:
            required_start = min(
                listing.start_date
                for listing
                in primary_listings
            )

            base_reason = (
                "Tracked company historical "
                "price coverage."
            )

        # =================================
        # Process every historical listing
        # =================================

        for listing in primary_listings:
            # Clamp the company-level range
            # to this listing's lifetime.

            listing_start = max(
                required_start,
                listing.start_date,
            )

            if listing.end_date is None:
                listing_end = (
                    required_end
                )

            else:
                listing_end = min(
                    required_end,
                    listing.end_date,
                )

            # This listing does not overlap
            # the requested research period.
            if (
                listing_start
                > listing_end
            ):
                continue

            # -----------------------------
            # Calendar-aware coverage
            # -----------------------------

            coverage = (
                assess_daily_coverage(
                    database=database,

                    listing_id=
                        listing.id,

                    provider_name=
                        PROVIDER_NAME,

                    dataset_name=
                        DATASET_NAME,

                    start_date=
                        listing_start,

                    end_date=
                        listing_end,
                )
            )

            # Every expected exchange
            # session already exists.
            if (
                coverage
                .missing_session_count
                == 0
            ):
                already_covered += 1
                continue

            # Defensive check. Normally
            # missing_session_count > 0
            # means gaps is non-empty.
            if not coverage.gaps:
                continue

            # -----------------------------
            # Missing-data envelope
            # -----------------------------

            first_gap = (
                coverage.gaps[0]
            )

            last_gap = (
                coverage.gaps[-1]
            )

            missing_start = (
                first_gap.start_date
            )

            missing_end = (
                last_gap.end_date
            )

            # -----------------------------
            # Split the missing range by
            # historical provider symbol.
            # -----------------------------

            symbol_segments = (
                get_provider_symbol_segments(
                    database=database,

                    listing_id=
                        listing.id,

                    provider_name=
                        PROVIDER_NAME,

                    start_date=
                        missing_start,

                    end_date=
                        missing_end,
                )
            )

            # =============================
            # One job per symbol segment
            # =============================

            for segment in symbol_segments:
                full_history = (
                    requires_full_history(
                        exchange_code=
                            listing
                            .exchange_code,

                        missing_start_date=
                            segment
                            .start_date,
                    )
                )

                # -------------------------
                # Human-readable audit
                # reason.
                # -------------------------

                reason = (
                    f"{base_reason} "
                    f"Missing "
                    f"{coverage.missing_session_count} "
                    f"expected trading sessions "
                    f"across "
                    f"{len(coverage.gaps)} "
                    f"gap(s). "
                    f"Provider symbol: "
                    f"{segment.symbol}. "
                    f"Segment: "
                    f"{segment.start_date} "
                    f"through "
                    f"{segment.end_date}."
                )

                if full_history:
                    reason += (
                        " Missing coverage "
                        "extends beyond the "
                        "provider's compact "
                        "recent-data window."
                    )

                else:
                    reason += (
                        " Missing coverage is "
                        "within the provider's "
                        "compact recent-data "
                        "window."
                    )

                # -------------------------
                # Avoid duplicate jobs
                # -------------------------

                existing_job_statement = (
                    select(
                        RetrievalJob
                    )
                    .where(
                        RetrievalJob
                        .tracking_run_id
                        == tracking_run_id,

                        RetrievalJob
                        .listing_id
                        == listing.id,

                        RetrievalJob
                        .provider_name
                        == PROVIDER_NAME,

                        RetrievalJob
                        .dataset_name
                        == DATASET_NAME,

                        RetrievalJob
                        .required_start_date
                        == segment.start_date,

                        RetrievalJob
                        .required_end_date
                        == segment.end_date,
                    )
                )

                existing_job = (
                    database.scalar(
                        existing_job_statement
                    )
                )

                if (
                    existing_job
                    is not None
                ):
                    jobs_existing += 1
                    continue

                # -------------------------
                # Create retrieval job
                # -------------------------

                job = RetrievalJob(
                    tracking_run_id=
                        tracking_run_id,

                    company_id=
                        decision.company_id,

                    listing_id=
                        listing.id,

                    provider_name=
                        PROVIDER_NAME,

                    dataset_name=
                        DATASET_NAME,

                    required_start_date=
                        segment.start_date,

                    required_end_date=
                        segment.end_date,

                    full_history=
                        full_history,

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

