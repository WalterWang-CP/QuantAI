import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendars.service import (
    get_expected_sessions,
)
from app.db.models.identity import (
    Listing,
)
from app.db.models.market_data import (
    DailyPriceBar,
    DataSource,
)


@dataclass(frozen=True)
class CoverageGap:
    start_date: date
    end_date: date
    missing_session_count: int


@dataclass(frozen=True)
class DailyCoverageAssessment:
    listing_id: uuid.UUID

    exchange_code: str

    provider_name: str
    dataset_name: str

    coverage_start_date: date
    coverage_end_date: date

    expected_session_count: int
    stored_session_count: int

    missing_session_count: int
    unexpected_session_count: int

    coverage_percent: float

    first_stored_date: date | None
    last_stored_date: date | None

    gaps: list[CoverageGap]


def group_missing_sessions(
    expected_sessions: list[date],
    missing_sessions: list[date],
) -> list[CoverageGap]:
    if not missing_sessions:
        return []

    position = {
        session_date: index
        for index, session_date
        in enumerate(
            expected_sessions
        )
    }

    gaps = []

    gap_start = (
        missing_sessions[0]
    )

    previous_date = (
        missing_sessions[0]
    )

    count = 1

    for session_date in (
        missing_sessions[1:]
    ):
        previous_position = (
            position[previous_date]
        )

        current_position = (
            position[session_date]
        )

        if (
            current_position
            == previous_position + 1
        ):
            count += 1

        else:
            gaps.append(
                CoverageGap(
                    start_date=gap_start,
                    end_date=previous_date,
                    missing_session_count=
                        count,
                )
            )

            gap_start = session_date
            count = 1

        previous_date = session_date

    gaps.append(
        CoverageGap(
            start_date=gap_start,
            end_date=previous_date,
            missing_session_count=count,
        )
    )

    return gaps


def get_data_source(
    database: Session,
    provider_name: str,
    dataset_name: str,
) -> DataSource | None:
    statement = select(
        DataSource
    ).where(
        DataSource.provider_name
        == provider_name,

        DataSource.dataset_name
        == dataset_name,
    )

    return database.scalar(
        statement
    )


def assess_daily_coverage(
    database: Session,
    listing_id: uuid.UUID,
    provider_name: str,
    dataset_name: str,
    start_date: date,
    end_date: date,
) -> DailyCoverageAssessment:
    listing = database.get(
        Listing,
        listing_id,
    )

    if listing is None:
        raise LookupError(
            "Listing does not exist."
        )

    coverage_start = max(
        start_date,
        listing.start_date,
    )

    coverage_end = end_date

    if (
        listing.end_date is not None
        and listing.end_date
        < coverage_end
    ):
        coverage_end = (
            listing.end_date
        )

    if coverage_start > coverage_end:
        return DailyCoverageAssessment(
            listing_id=listing.id,
            exchange_code=
                listing.exchange_code,
            provider_name=
                provider_name,
            dataset_name=
                dataset_name,
            coverage_start_date=
                coverage_start,
            coverage_end_date=
                coverage_end,
            expected_session_count=0,
            stored_session_count=0,
            missing_session_count=0,
            unexpected_session_count=0,
            coverage_percent=100.0,
            first_stored_date=None,
            last_stored_date=None,
            gaps=[],
        )

    expected_sessions = (
        get_expected_sessions(
            exchange_code=
                listing.exchange_code,
            start_date=
                coverage_start,
            end_date=
                coverage_end,
        )
    )

    expected_set = set(
        expected_sessions
    )

    source = get_data_source(
        database=database,
        provider_name=
            provider_name,
        dataset_name=
            dataset_name,
    )

    if source is None:
        stored_dates = []

    else:
        statement = (
            select(
                DailyPriceBar.trading_date
            )
            .where(
                DailyPriceBar.listing_id
                == listing.id,

                DailyPriceBar.source_id
                == source.id,

                DailyPriceBar.trading_date
                >= coverage_start,

                DailyPriceBar.trading_date
                <= coverage_end,
            )
            .order_by(
                DailyPriceBar.trading_date
            )
        )

        stored_dates = list(
            database.scalars(
                statement
            ).all()
        )

    stored_set = set(
        stored_dates
    )

    stored_expected = (
        stored_set
        & expected_set
    )

    unexpected_dates = (
        stored_set
        - expected_set
    )

    missing_sessions = [
        session_date
        for session_date
        in expected_sessions
        if session_date
        not in stored_set
    ]

    gaps = group_missing_sessions(
        expected_sessions=
            expected_sessions,
        missing_sessions=
            missing_sessions,
    )

    expected_count = len(
        expected_sessions
    )

    stored_count = len(
        stored_expected
    )

    if expected_count == 0:
        coverage_percent = 100.0

    else:
        coverage_percent = round(
            (
                stored_count
                / expected_count
            )
            * 100,
            2,
        )

    return DailyCoverageAssessment(
        listing_id=listing.id,

        exchange_code=
            listing.exchange_code,

        provider_name=
            provider_name,

        dataset_name=
            dataset_name,

        coverage_start_date=
            coverage_start,

        coverage_end_date=
            coverage_end,

        expected_session_count=
            expected_count,

        stored_session_count=
            stored_count,

        missing_session_count=
            len(
                missing_sessions
            ),

        unexpected_session_count=
            len(
                unexpected_dates
            ),

        coverage_percent=
            coverage_percent,

        first_stored_date=(
            min(stored_dates)
            if stored_dates
            else None
        ),

        last_stored_date=(
            max(stored_dates)
            if stored_dates
            else None
        ),

        gaps=gaps,
    )