from datetime import (
    date,
    datetime,
    timezone,
)
from decimal import Decimal

from sqlalchemy import (
    func,
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.db.models.identity import (
    Listing,
)
from app.db.models.market_cap import (
    MarketCapObservation,
)
from app.db.models.universe import (
    CompanyRanking,
    RankingSnapshot,
)
from app.universe.constants import (
    RECONSTRUCTED_MARKET_CAP_METRIC,
)

RANKING_METRIC = (
    RECONSTRUCTED_MARKET_CAP_METRIC
)

BASE_CURRENCY = "USD"

TOP_PREVIEW_SIZE = 20


def get_existing_snapshot(
    database: Session,
    ranking_date: date,
    effective_date: date,
) -> RankingSnapshot | None:
    statement = select(
        RankingSnapshot
    ).where(
        RankingSnapshot.ranking_date
        == ranking_date,

        RankingSnapshot.effective_date
        == effective_date,

        RankingSnapshot.ranking_metric
        == RANKING_METRIC,

        RankingSnapshot.base_currency
        == BASE_CURRENCY,
    )

    return database.scalar(
        statement
    )


def get_snapshot_preview(
    database: Session,
    snapshot: RankingSnapshot,
) -> list[dict]:
    statement = (
        select(
            CompanyRanking,
            MarketCapObservation,
            Listing,
        )
        .join(
            MarketCapObservation,
            (
                MarketCapObservation.company_id
                == CompanyRanking.company_id
            )
            & (
                MarketCapObservation.valuation_date
                == snapshot.ranking_date
            ),
        )
        .join(
            Listing,
            Listing.id
            == MarketCapObservation.listing_id,
        )
        .where(
            CompanyRanking.snapshot_id
            == snapshot.id,
        )
        .order_by(
            CompanyRanking.rank
        )
    )

    rows = database.execute(
        statement
    ).all()

    members = []

    seen_companies = set()

    for (
        ranking,
        observation,
        listing,
    ) in rows:
        if (
            ranking.company_id
            in seen_companies
        ):
            continue

        seen_companies.add(
            ranking.company_id
        )

        members.append(
            {
                "company_id":
                    ranking.company_id,

                "listing_id":
                    listing.id,

                "ticker":
                    listing.ticker,

                "rank":
                    ranking.rank,

                "market_cap_usd":
                    ranking.market_cap_usd,
            }
        )

        if (
            len(members)
            >= TOP_PREVIEW_SIZE
        ):
            break

    return members


def build_market_cap_ranking_snapshot(
    database: Session,
    ranking_date: date,
    effective_date: date,
    primary_only: bool = True,
    minimum_candidates: int = 1,
) -> dict:
    if effective_date < ranking_date:
        raise ValueError(
            "effective_date cannot be "
            "earlier than ranking_date."
        )

    existing_snapshot = (
        get_existing_snapshot(
            database=database,
            ranking_date=ranking_date,
            effective_date=effective_date,
        )
    )

    if existing_snapshot is not None:
        ranking_count = (
            database.scalar(
                select(
                    func.count(
                        CompanyRanking.id
                    )
                ).where(
                    CompanyRanking.snapshot_id
                    == existing_snapshot.id
                )
            )
            or 0
        )

        return {
            "snapshot_id":
                existing_snapshot.id,

            "ranking_date":
                existing_snapshot.ranking_date,

            "effective_date":
                existing_snapshot.effective_date,

            "ranking_metric":
                existing_snapshot.ranking_metric,

            "base_currency":
                existing_snapshot.base_currency,

            "candidates_found":
                ranking_count,

            "companies_ranked":
                ranking_count,

            "snapshot_status":
                existing_snapshot.status,

            "duplicate_company_observations":
                0,

            "reused_existing_snapshot":
                True,

            "top_members":
                get_snapshot_preview(
                    database=database,
                    snapshot=
                        existing_snapshot,
                ),
        }

    statement = (
        select(
            MarketCapObservation,
            Listing,
        )
        .join(
            Listing,
            Listing.id
            == MarketCapObservation.listing_id,
        )
        .where(
            MarketCapObservation.valuation_date
            == ranking_date,

            Listing.start_date
            <= ranking_date,

            or_(
                Listing.end_date
                .is_(None),

                Listing.end_date
                >= ranking_date,
            ),
        )
    )

    if primary_only:
        statement = statement.where(
            Listing.is_primary.is_(True)
        )

    rows = database.execute(
        statement
    ).all()

    candidates_found = len(
        rows
    )

    if (
        candidates_found
        < minimum_candidates
    ):
        raise ValueError(
            "Not enough reconstructed "
            "market-cap candidates exist "
            f"for {ranking_date}. "
            f"Found {candidates_found}; "
            f"minimum required is "
            f"{minimum_candidates}."
        )

    best_by_company = {}

    duplicate_company_observations = 0

    for observation, listing in rows:
        existing = best_by_company.get(
            observation.company_id
        )

        candidate = (
            observation,
            listing,
        )

        if existing is None:
            best_by_company[
                observation.company_id
            ] = candidate

            continue

        duplicate_company_observations += 1

        (
            existing_observation,
            existing_listing,
        ) = existing

        if (
            observation.market_cap_usd
            > existing_observation
            .market_cap_usd
        ):
            best_by_company[
                observation.company_id
            ] = candidate

        elif (
            observation.market_cap_usd
            == existing_observation
            .market_cap_usd
            and str(listing.id)
            < str(existing_listing.id)
        ):
            best_by_company[
                observation.company_id
            ] = candidate

    candidates = list(
        best_by_company.values()
    )

    candidates.sort(
        key=lambda item: (
            -Decimal(
                item[0].market_cap_usd
            ),
            str(
                item[0].company_id
            ),
        )
    )

    if (
        len(candidates)
        < minimum_candidates
    ):
        raise ValueError(
            "Not enough unique companies "
            "remain after deduplication. "
            f"Found {len(candidates)}; "
            f"minimum required is "
            f"{minimum_candidates}."
        )

    snapshot = RankingSnapshot(
        ranking_date=ranking_date,
        effective_date=effective_date,

        ranking_metric=RANKING_METRIC,
        base_currency=BASE_CURRENCY,

        status="draft",

        candidate_count=
            candidates_found,

        ranked_company_count=
            len(candidates),

        minimum_required_candidates=
            minimum_candidates,
    )

    database.add(
        snapshot
    )

    database.flush()

    rankings = []

    top_members = []

    for rank, (
        observation,
        listing,
    ) in enumerate(
        candidates,
        start=1,
    ):
        ranking = CompanyRanking(
            snapshot_id=snapshot.id,

            company_id=
                observation.company_id,

            rank=rank,

            market_cap_usd=
                observation.market_cap_usd,
        )

        rankings.append(
            ranking
        )

        if (
            rank
            <= TOP_PREVIEW_SIZE
        ):
            top_members.append(
                {
                    "company_id":
                        observation.company_id,

                    "listing_id":
                        listing.id,

                    "ticker":
                        listing.ticker,

                    "rank":
                        rank,

                    "market_cap_usd":
                        observation
                        .market_cap_usd,
                }
            )

    database.add_all(
        rankings
    )

    database.commit()

    database.refresh(
        snapshot
    )

    return {
        "snapshot_id":
            snapshot.id,

        "ranking_date":
            snapshot.ranking_date,

        "effective_date":
            snapshot.effective_date,

        "ranking_metric":
            snapshot.ranking_metric,

        "base_currency":
            snapshot.base_currency,

        "snapshot_status":
            snapshot.status,

        "candidates_found":
            candidates_found,

        "companies_ranked":
            len(rankings),

        "duplicate_company_observations":
            duplicate_company_observations,

        "reused_existing_snapshot":
            False,

        "top_members":
            top_members,
    }

def approve_market_cap_ranking_snapshot(
    database: Session,
    snapshot_id,
    note: str | None = None,
) -> RankingSnapshot:
    snapshot = database.get(
        RankingSnapshot,
        snapshot_id,
    )

    if snapshot is None:
        raise LookupError(
            "Ranking snapshot does not exist."
        )

    if (
        snapshot.ranking_metric
        != RANKING_METRIC
    ):
        raise ValueError(
            "Only reconstructed market-cap "
            "snapshots use this approval flow."
        )

    if snapshot.status == "approved":
        return snapshot

    if snapshot.status == "rejected":
        raise ValueError(
            "Rejected ranking snapshots "
            "cannot be approved."
        )

    ranked_count = (
        snapshot.ranked_company_count
    )

    minimum_required = (
        snapshot.minimum_required_candidates
    )

    if (
        ranked_count is None
        or minimum_required is None
    ):
        raise ValueError(
            "Snapshot completeness metadata "
            "is missing."
        )

    if (
        ranked_count
        < minimum_required
    ):
        raise ValueError(
            "Snapshot does not satisfy its "
            "minimum candidate requirement."
        )

    snapshot.status = "approved"

    snapshot.approved_at = (
        datetime.now(
            timezone.utc
        )
    )

    snapshot.approval_note = note

    database.commit()
    database.refresh(
        snapshot
    )

    return snapshot