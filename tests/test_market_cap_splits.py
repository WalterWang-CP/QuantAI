from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models.corporate_actions import StockSplit
from app.db.models.fundamentals import SharesOutstandingObservation
from app.db.models.identity import Company, Listing, Security
from app.db.models.market_cap import MarketCapObservation
from app.db.models.market_data import DailyPriceBar, DataSource, IngestionRun
from app.market_cap.service import reconstruct_market_cap, reconstruct_market_caps_batch


def day(number):
    return date(2025, 1, number)


@pytest.fixture
def case():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    database = Session(engine, autoflush=False)
    company = Company(legal_name="Split Test Company", country_code="US")
    database.add(company)
    database.flush()
    security = Security(
        company_id=company.id, name="Split Test Stock",
        security_type="common_stock", start_date=day(1),
    )
    database.add(security)
    database.flush()
    listing = Listing(
        security_id=security.id, ticker="SPLIT", exchange_code="NASDAQ",
        currency_code="USD", start_date=day(1), is_primary=True,
    )
    sources = {
        "price": DataSource(provider_name="alpha_vantage", dataset_name="TIME_SERIES_DAILY"),
        "shares": DataSource(provider_name="manual", dataset_name="SHARES_OUTSTANDING"),
        "split": DataSource(provider_name="alpha_vantage", dataset_name="SPLITS"),
        "other_split": DataSource(provider_name="other", dataset_name="SPLITS"),
    }
    database.add_all([listing, *sources.values()])
    database.flush()

    def add_shares(count="1000", observed=2, known=2):
        observation = SharesOutstandingObservation(
            company_id=company.id, security_id=security.id,
            source_id=sources["shares"].id, observation_date=day(observed),
            known_date=day(known), shares_outstanding=Decimal(count),
        )
        database.add(observation)
        database.commit()
        return observation

    original_shares = add_shares()

    def ingestion(source, target):
        run = IngestionRun(
            source_id=source.id, listing_id=target.id,
            requested_symbol=target.ticker, full_history=False, status="completed",
        )
        database.add(run)
        database.flush()
        return run

    def add_price(close="50", trading_day=8):
        run = ingestion(sources["price"], listing)
        bar = DailyPriceBar(
            listing_id=listing.id, source_id=sources["price"].id,
            last_ingestion_run_id=run.id, trading_date=day(trading_day),
            open_price=Decimal(close), high_price=Decimal(close),
            low_price=Decimal(close), close_price=Decimal(close), volume=100,
        )
        database.add(bar)
        database.commit()
        return bar

    def add_split(factor="2", effective=6, source="split", target=None):
        target = target or listing
        run = ingestion(sources[source], target)
        split = StockSplit(
            listing_id=target.id, source_id=sources[source].id,
            last_ingestion_run_id=run.id, effective_date=day(effective),
            split_factor=Decimal(factor),
        )
        database.add(split)
        database.commit()
        return split

    yield database, listing, original_shares, add_price, add_split, add_shares
    database.close()
    engine.dispose()


@pytest.mark.parametrize("factor,close,expected_shares", [
    ("2", "50", "2000"),
    ("0.2", "500", "200"),
])
def test_forward_and_reverse_splits_preserve_market_cap(case, factor, close, expected_shares):
    database, listing, raw_shares, price, split, _ = case
    bar = price(close)
    split(factor)
    result = reconstruct_market_cap(database, listing.id, day(8))
    assert result.shares_outstanding == Decimal(expected_shares)
    assert result.market_cap_usd == Decimal("100000")
    assert result.shares_observation_id == raw_shares.id
    database.refresh(raw_shares)
    database.refresh(bar)
    assert raw_shares.shares_outstanding == Decimal("1000")
    assert bar.close_price == Decimal(close)


def test_multiple_splits_compound(case):
    database, listing, _, price, split, _ = case
    price("10")
    split("2", effective=5)
    split("3", effective=6)
    result = reconstruct_market_cap(database, listing.id, day(8))
    assert result.shares_outstanding == Decimal("6000")
    assert result.market_cap_usd == Decimal("60000")


def test_observation_on_split_date_is_not_adjusted_twice(case):
    database, listing, _, price, split, shares = case
    price()
    split()
    post_split = shares("2000", observed=6, known=6)
    result = reconstruct_market_cap(database, listing.id, day(8))
    assert result.shares_observation_id == post_split.id
    assert result.shares_outstanding == Decimal("2000")
    assert result.market_cap_usd == Decimal("100000")


def test_late_publication_uses_observation_date_as_share_basis(case):
    database, listing, raw_shares, price, split, _ = case
    raw_shares.known_date = day(7)
    database.commit()
    price()
    split()
    result = reconstruct_market_cap(database, listing.id, day(8))
    assert result.shares_outstanding == Decimal("2000")


def test_shares_not_yet_known_are_not_used(case):
    database, listing, raw_shares, price, split, shares = case
    price()
    split()
    shares("3000", observed=7, known=9)
    result = reconstruct_market_cap(database, listing.id, day(8))
    assert result.shares_observation_id == raw_shares.id
    assert result.shares_outstanding == Decimal("2000")


def test_future_split_is_not_applied(case):
    database, listing, _, price, split, _ = case
    price("100")
    split(effective=10)
    result = reconstruct_market_cap(database, listing.id, day(8))
    assert result.shares_outstanding == Decimal("1000")
    assert result.market_cap_usd == Decimal("100000")


def test_stale_price_does_not_receive_later_split_adjustment(case):
    database, listing, _, price, split, _ = case
    price("100", trading_day=3)
    split()
    result = reconstruct_market_cap(database, listing.id, day(8))
    assert result.price_date == day(3)
    assert result.shares_outstanding == Decimal("1000")
    assert result.market_cap_usd == Decimal("100000")


def test_post_split_shares_are_mapped_back_to_stale_price_basis(case):
    database, listing, _, price, split, shares = case
    price("100", trading_day=3)
    split()
    post_split = shares("2000", observed=6, known=7)
    result = reconstruct_market_cap(database, listing.id, day(8))
    assert result.shares_observation_id == post_split.id
    assert result.shares_outstanding == Decimal("1000")
    assert result.market_cap_usd == Decimal("100000")
    database.refresh(post_split)
    assert post_split.shares_outstanding == Decimal("2000")


def test_same_split_from_two_sources_is_applied_once(case):
    database, listing, _, price, split, _ = case
    price()
    split()
    split(source="other_split")
    result = reconstruct_market_cap(database, listing.id, day(8))
    assert result.shares_outstanding == Decimal("2000")
    assert result.market_cap_usd == Decimal("100000")


def test_conflicting_split_sources_reject_valuation(case):
    database, listing, _, price, split, _ = case
    price()
    split("2")
    split("3", source="other_split")
    with pytest.raises(ValueError, match="Conflicting split factors"):
        reconstruct_market_cap(database, listing.id, day(8))
    assert database.scalar(select(func.count(MarketCapObservation.id))) == 0


def test_other_listing_split_is_not_applied(case):
    database, listing, _, price, split, _ = case
    price("100")
    other = Listing(
        security_id=listing.security_id, ticker="OTHER", exchange_code="NYSE",
        currency_code="USD", start_date=day(1), is_primary=False,
    )
    database.add(other)
    database.commit()
    split(target=other)
    result = reconstruct_market_cap(database, listing.id, day(8))
    assert result.shares_outstanding == Decimal("1000")


def test_reconstructing_again_updates_existing_market_cap(case):
    database, listing, _, price, split, _ = case
    price()
    first = reconstruct_market_cap(database, listing.id, day(8))
    old_id = first.id
    assert first.market_cap_usd == Decimal("50000")
    split()
    repaired = reconstruct_market_cap(database, listing.id, day(8))
    assert repaired.id == old_id
    assert repaired.market_cap_usd == Decimal("100000")
    assert database.scalar(select(func.count(MarketCapObservation.id))) == 1


def test_batch_reports_conflicting_splits_as_invalid_input(case):
    database, listing, _, price, split, _ = case
    price()
    split("2")
    split("3", source="other_split")
    result = reconstruct_market_caps_batch(database, day(8), listing_ids=[listing.id])
    assert result["completed"] == 0
    assert result["failed"] == 1
    assert result["items"][0]["error_type"] == "missing_or_invalid_input"
    assert "Conflicting split factors" in result["items"][0]["error_message"]


def test_split_effective_on_price_date_is_applied(case):
    database, listing, _, price, split, _ = case
    price("50", trading_day=6)
    split(effective=6)
    result = reconstruct_market_cap(database, listing.id, day(6))
    assert result.shares_outstanding == Decimal("2000")
    assert result.market_cap_usd == Decimal("100000")
