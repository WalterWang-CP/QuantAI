import uuid
from datetime import date
from decimal import Decimal
import hashlib
import json

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from app.db.models.identity import Listing
from app.db.models.market_data import DailyPriceBar, DataSource, IngestionRun, RawDataArtifact
from app.db.models.corporate_actions import StockSplit
from app.db.models.sec_market_cap import SECMarketCapSnapshot
from app.db.models.market_cap import MarketCapObservation
from app.filings.share_normalization import normalize_company_shares
from app.filings.share_selection import ShareSelectionConflict
from app.market_cap.sec_service import SECMarketCapRequest, reconstruct_sec_market_cap
from test_database_migrations import postgres_migrations
from test_filing_provenance import count, filing_database
from test_share_selection import setup, add


def request(**changes):
    values = dict(valuation_date=date(2021, 2, 2), confirm_split_coverage=True,
        split_evidence_url="https://example.com/fixture-splits",
        split_evidence_note="Fixture establishes split coverage for the tested interval.")
    values.update(changes)
    return SECMarketCapRequest(**values)


def case(database, company_id, source_id, *, observed=date(2020, 12, 31), price_date=date(2021, 2, 2), currency="USD"):
    security, _, _ = setup(database, company_id)
    listing = Listing(security_id=security.id, ticker="TEST", exchange_code="NASDAQ", currency_code=currency,
        start_date=date(2020, 1, 1), is_primary=True)
    source = DataSource(provider_name="alpha_vantage", dataset_name="TIME_SERIES_DAILY")
    split_source = DataSource(provider_name="alpha_vantage", dataset_name="SPLITS")
    database.add_all([listing, source, split_source]); database.flush()
    run = IngestionRun(source_id=source.id, listing_id=listing.id, requested_symbol="TEST", full_history=True, status="completed")
    database.add(run); database.flush()
    price = DailyPriceBar(listing_id=listing.id, source_id=source.id, last_ingestion_run_id=run.id,
        trading_date=price_date, open_price=10, high_price=10, low_price=10, close_price=10, volume=100)
    archive = RawDataArtifact(ingestion_run_id=run.id, source_id=source.id, listing_id=listing.id,
        storage_path="fixture.json", sha256="a" * 64, byte_count=10, content_type="application/json")
    database.add_all([price, archive]); database.commit()
    add(database, company_id, source_id, value=100, period=observed)
    normalize_company_shares(database, company_id)
    def split(factor, effective=date(2021, 1, 15), alternate=False):
        selected_source = split_source
        if alternate:
            selected_source = DataSource(provider_name="other", dataset_name="SPLITS")
            database.add(selected_source); database.flush()
        action_run = IngestionRun(source_id=selected_source.id, listing_id=listing.id, requested_symbol="TEST", full_history=True, status="completed")
        database.add(action_run); database.flush()
        row = StockSplit(listing_id=listing.id, source_id=selected_source.id, last_ingestion_run_id=action_run.id,
            effective_date=effective, split_factor=Decimal(factor))
        database.add(row); database.commit()
        return row
    return listing, price, archive, split


def test_exact_repeat_captured_manifest_and_legacy_untouched(filing_database):
    database, company_id, source_id = filing_database
    listing, _, _, _ = case(database, company_id, source_id)
    first = reconstruct_sec_market_cap(database, listing.id, request())
    second = reconstruct_sec_market_cap(database, listing.id, request())
    assert first.created and not second.created and first.snapshot_id == second.snapshot_id
    assert first.manifest["result"]["market_cap_usd"] == "1000"
    assert first.manifest["fx"]["rate"] == "1"
    assert first.manifest["shares_selection"]["filing_id"]
    assert first.manifest["shares_fact"]["artifact_sha256"]
    encoded = json.dumps(first.manifest, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(encoded.encode()).hexdigest() == first.input_hash
    assert count(database, SECMarketCapSnapshot) == 1 and count(database, MarketCapObservation) == 0


@pytest.mark.parametrize("factor,expected", [("2", "2000"), ("0.2", "200")])
def test_forward_and_reverse_split_arithmetic(filing_database, factor, expected):
    database, company_id, source_id = filing_database
    listing, _, _, split = case(database, company_id, source_id)
    split(factor)
    result = reconstruct_sec_market_cap(database, listing.id, request())
    assert result.manifest["result"]["market_cap_usd"] == expected
    assert len(result.manifest["splits"]) == 1


def test_equal_split_duplicates_count_once_and_conflicts_fail(filing_database):
    database, company_id, source_id = filing_database
    listing, _, _, split = case(database, company_id, source_id)
    split("2"); other = split("2", alternate=True)
    first = reconstruct_sec_market_cap(database, listing.id, request())
    assert first.manifest["result"]["market_cap_usd"] == "2000"
    assert len(first.manifest["splits"]) == 2
    other.split_factor = Decimal("3"); database.commit()
    with pytest.raises(ShareSelectionConflict, match="Conflicting split"):
        reconstruct_sec_market_cap(database, listing.id, request())
    assert count(database, SECMarketCapSnapshot) == 1


def test_backward_split_basis_uses_selected_price_date(filing_database):
    database, company_id, source_id = filing_database
    listing, _, _, split = case(database, company_id, source_id, observed=date(2021, 1, 31), price_date=date(2021, 1, 30))
    split("2", effective=date(2021, 1, 31))
    result = reconstruct_sec_market_cap(database, listing.id, request())
    assert result.manifest["result"]["shares_on_price_date"] == "50"
    assert result.manifest["result"]["market_cap_usd"] == "500"


def test_changed_price_preserves_previous_result(filing_database):
    database, company_id, source_id = filing_database
    listing, price, _, _ = case(database, company_id, source_id)
    first = reconstruct_sec_market_cap(database, listing.id, request())
    price.close_price = 12; database.commit()
    second = reconstruct_sec_market_cap(database, listing.id, request())
    assert second.created and second.input_hash != first.input_hash
    assert count(database, SECMarketCapSnapshot) == 2
    old = database.get(SECMarketCapSnapshot, first.snapshot_id)
    assert json.loads(old.manifest_json)["result"]["market_cap_usd"] == "1000"
    assert second.manifest["result"]["market_cap_usd"] == "1200"


def test_stale_price_and_non_usd_refused(filing_database):
    database, company_id, source_id = filing_database
    listing, price, _, _ = case(database, company_id, source_id, currency="CAD")
    with pytest.raises(ShareSelectionConflict, match="USD listings only"):
        reconstruct_sec_market_cap(database, listing.id, request())
    listing.currency_code = "USD"; price.trading_date = date(2021, 1, 1); database.commit()
    with pytest.raises(ShareSelectionConflict, match="max_price_age_days"):
        reconstruct_sec_market_cap(database, listing.id, request())
    assert count(database, SECMarketCapSnapshot) == 0


def test_missing_price_archive_refused(filing_database):
    database, company_id, source_id = filing_database
    listing, _, archive, _ = case(database, company_id, source_id)
    database.delete(archive); database.commit()
    with pytest.raises(ShareSelectionConflict, match="source archive"):
        reconstruct_sec_market_cap(database, listing.id, request())
    assert count(database, SECMarketCapSnapshot) == 0


def test_routes_and_failed_commit_rollback(filing_database, monkeypatch):
    database, company_id, source_id = filing_database
    from app.market_cap.routes import reconstruct_listing_sec_market_cap, read_sec_market_cap_history, read_sec_security_listings
    listing, _, _, _ = case(database, company_id, source_id)
    result = reconstruct_listing_sec_market_cap(listing.id, request(), database)
    assert read_sec_market_cap_history(listing.id, database, 100, 0)[0].snapshot_id == result.snapshot_id
    assert read_sec_security_listings(listing.security_id, database)[0].id == listing.id
    with pytest.raises(HTTPException) as error:
        reconstruct_listing_sec_market_cap(uuid.uuid4(), request(), database)
    assert error.value.status_code == 404
    monkeypatch.setattr(database, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failed")))
    with pytest.raises(RuntimeError, match="commit failed"):
        reconstruct_sec_market_cap(database, listing.id, request(split_evidence_note="A different coverage assertion creates another input version."))
    assert count(database, SECMarketCapSnapshot) == 1


@pytest.mark.parametrize("changes", [{"confirm_split_coverage": False}, {"max_price_age_days": 32}, {"split_evidence_note": ""}])
def test_request_requires_coverage_and_valid_limits(changes):
    with pytest.raises(ValidationError):
        request(**changes)
