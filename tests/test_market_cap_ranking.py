from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models.fundamentals import (
    SharesOutstandingObservation,
)
from app.db.models.identity import (
    Company,
    Listing,
    Security,
)
from app.db.models.market_cap import (
    MarketCapObservation,
)
from app.db.models.market_data import (
    DataSource,
)
from app.db.models.universe import (
    CompanyRanking,
)
from app.universe.market_cap_ranking import (
    build_market_cap_ranking_snapshot,
)
from app.db.models.fx import (
    FxRate,
)
from app.db.models.universe import (
    CompanyRanking,
    RankingSnapshot,
)
from app.universe.market_cap_ranking import (
    approve_market_cap_ranking_snapshot,
    build_market_cap_ranking_snapshot,
)


VALUATION_DATE = date(
    2024,
    12,
    31,
)

EFFECTIVE_DATE = date(
    2025,
    1,
    2,
)


def create_database():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )

    Base.metadata.create_all(
        engine
    )

    return Session(engine)


def create_market_cap_candidate(
    database: Session,
    source: DataSource,
    name: str,
    ticker: str,
    market_cap_usd: Decimal,
) -> tuple[
    Company,
    Listing,
]:
    company = Company(
        legal_name=name,
        country_code="US",
    )

    database.add(
        company
    )

    database.flush()

    security = Security(
        company_id=company.id,

        name=f"{name} Common Stock",

        security_type=
            "common_stock",

        start_date=date(
            2000,
            1,
            1,
        ),
    )

    database.add(
        security
    )

    database.flush()

    listing = Listing(
        security_id=security.id,

        ticker=ticker,

        exchange_code="NASDAQ",

        currency_code="USD",

        start_date=date(
            2000,
            1,
            1,
        ),

        is_primary=True,
    )

    database.add(
        listing
    )

    database.flush()

    shares = (
        SharesOutstandingObservation(
            company_id=company.id,

            security_id=security.id,

            source_id=source.id,

            observation_date=date(
                2024,
                9,
                30,
            ),

            known_date=date(
                2024,
                11,
                1,
            ),

            shares_outstanding=
                Decimal(
                    "1000000000"
                ),
        )
    )

    database.add(
        shares
    )

    database.flush()

    observation = (
        MarketCapObservation(
            company_id=company.id,

            listing_id=listing.id,

            valuation_date=
                VALUATION_DATE,

            price_date=
                VALUATION_DATE,

            shares_observation_id=
                shares.id,

            fx_rate_id=None,

            local_currency="USD",

            price=Decimal(
                "100"
            ),

            shares_outstanding=
                Decimal(
                    "1000000000"
                ),

            local_market_cap=
                market_cap_usd,

            market_cap_usd=
                market_cap_usd,
        )
    )

    database.add(
        observation
    )

    database.commit()

    return (
        company,
        listing,
    )


def test_market_cap_ranking_orders_companies():
    database = create_database()

    source = DataSource(
        provider_name="manual",

        dataset_name=
            "SHARES_OUTSTANDING",
    )

    database.add(source)
    database.commit()

    company_a, _ = (
        create_market_cap_candidate(
            database=database,
            source=source,
            name="Company A",
            ticker="AAA",
            market_cap_usd=Decimal(
                "300000000000"
            ),
        )
    )

    company_b, _ = (
        create_market_cap_candidate(
            database=database,
            source=source,
            name="Company B",
            ticker="BBB",
            market_cap_usd=Decimal(
                "500000000000"
            ),
        )
    )

    company_c, _ = (
        create_market_cap_candidate(
            database=database,
            source=source,
            name="Company C",
            ticker="CCC",
            market_cap_usd=Decimal(
                "100000000000"
            ),
        )
    )

    result = (
        build_market_cap_ranking_snapshot(
            database=database,

            ranking_date=
                VALUATION_DATE,

            effective_date=
                EFFECTIVE_DATE,

            primary_only=True,

            minimum_candidates=3,
        )
    )

    snapshot = database.get(
    RankingSnapshot,
    result["snapshot_id"],
    )

    assert snapshot.status == "draft"

    assert (
        snapshot.candidate_count
        == 3
    )

    assert (
        snapshot.ranked_company_count
        == 3
    )

    assert (
        snapshot.minimum_required_candidates
        == 3
    )
    assert (
        result["companies_ranked"]
        == 3
    )

    rankings = (
        database.query(
            CompanyRanking
        )
        .filter(
            CompanyRanking.snapshot_id
            == result["snapshot_id"]
        )
        .order_by(
            CompanyRanking.rank
        )
        .all()
    )

    assert (
        rankings[0].company_id
        == company_b.id
    )

    assert rankings[0].rank == 1

    assert (
        rankings[1].company_id
        == company_a.id
    )

    assert rankings[1].rank == 2

    assert (
        rankings[2].company_id
        == company_c.id
    )

    assert rankings[2].rank == 3


def test_market_cap_ranking_is_idempotent():
    database = create_database()

    source = DataSource(
        provider_name="manual",

        dataset_name=
            "SHARES_OUTSTANDING",
    )

    database.add(source)
    database.commit()

    create_market_cap_candidate(
        database=database,
        source=source,
        name="Company A",
        ticker="AAA",
        market_cap_usd=Decimal(
            "300000000000"
        ),
    )

    first = (
        build_market_cap_ranking_snapshot(
            database=database,

            ranking_date=
                VALUATION_DATE,

            effective_date=
                EFFECTIVE_DATE,
        )
    )

    second = (
        build_market_cap_ranking_snapshot(
            database=database,

            ranking_date=
                VALUATION_DATE,

            effective_date=
                EFFECTIVE_DATE,
        )
    )

    assert (
        first["snapshot_id"]
        == second["snapshot_id"]
    )

    assert (
        second[
            "reused_existing_snapshot"
        ]
        is True
    )

    ranking_count = (
        database.query(
            CompanyRanking
        )
        .filter(
            CompanyRanking.snapshot_id
            == first["snapshot_id"]
        )
        .count()
    )

    assert ranking_count == 1


def test_market_cap_ranking_requires_minimum_candidates():
    database = create_database()

    source = DataSource(
        provider_name="manual",

        dataset_name=
            "SHARES_OUTSTANDING",
    )

    database.add(source)
    database.commit()

    create_market_cap_candidate(
        database=database,
        source=source,
        name="Company A",
        ticker="AAA",
        market_cap_usd=Decimal(
            "300000000000"
        ),
    )

    try:
        build_market_cap_ranking_snapshot(
            database=database,

            ranking_date=
                VALUATION_DATE,

            effective_date=
                EFFECTIVE_DATE,

            minimum_candidates=2,
        )

    except ValueError as error:
        assert (
            "Not enough reconstructed"
            in str(error)
        )

    else:
        raise AssertionError(
            "Expected candidate-count "
            "validation to fail."
        )


def test_market_cap_snapshot_can_be_approved():
    database = create_database()

    source = DataSource(
        provider_name="manual",
        dataset_name=
            "SHARES_OUTSTANDING",
    )

    database.add(source)
    database.commit()

    create_market_cap_candidate(
        database=database,
        source=source,
        name="Company A",
        ticker="AAA",
        market_cap_usd=Decimal(
            "300000000000"
        ),
    )

    result = (
        build_market_cap_ranking_snapshot(
            database=database,

            ranking_date=
                VALUATION_DATE,

            effective_date=
                EFFECTIVE_DATE,

            minimum_candidates=1,
        )
    )

    snapshot = (
        approve_market_cap_ranking_snapshot(
            database=database,

            snapshot_id=
                result["snapshot_id"],

            note="Synthetic test approval.",
        )
    )

    assert (
        snapshot.status
        == "approved"
    )

    assert (
        snapshot.approved_at
        is not None
    )

    assert (
        snapshot.approval_note
        == "Synthetic test approval."
    )