import hashlib
import uuid
from decimal import Decimal
import pytest
from pydantic import ValidationError
from fastapi import HTTPException
from sqlalchemy import select
from app.db.models.csv_prices import CSVPriceArtifact
from app.db.models.market_data import DailyPriceBar, DataSource, IngestionRun, RawDataArtifact
from app.market_data.csv_service import CSVPriceImportRequest, CSVPriceConflict, import_raw_price_csv, parse_raw_price_csv
from app.market_cap.sec_service import reconstruct_sec_market_cap
from app.filings.share_selection import ShareSelectionConflict
from test_database_migrations import postgres_migrations
from test_filing_provenance import filing_database, count
from test_sec_market_cap import case, request as cap_request

CSV = "date,open,high,low,close,volume\r\n2021-02-02,12,13,11,12,100\r\n"

def request(**changes):
    values = dict(csv_text=CSV, source_name="fixture", source_url="https://example.com/export",
        source_note="Fixture export containing original unadjusted OHLC prices.", symbol="TEST",
        currency_code="USD", confirm_unadjusted_prices=True)
    values.update(changes)
    return CSVPriceImportRequest(**values)

@pytest.mark.parametrize("text", [
    "", "date,open,high,low,close,volume\n", CSV.replace("volume", "adjusted_close"),
    CSV + "2021-02-02,12,13,11,12,100\n", CSV.replace(",12,13,11,12,", ",12,11,11,12,"),
    CSV.replace(",100", ",-1"), CSV.replace(",100", ",9223372036854775808"),
    CSV.replace(",12,13", ",NaN,13"), CSV.replace(",12,13", ",0,13"),
    CSV.replace(",12,13", ",12.000000001,13"), CSV.replace("2021-02-02", "2099-01-01"),
    CSV.replace("2021-02-02", "2021-02-30"), CSV.replace(",100", ",100,extra"),
])
def test_invalid_csv_rejected(text):
    with pytest.raises(ValueError):
        parse_raw_price_csv(text)

def test_exact_bom_crlf_archive_and_sorted_rows():
    text = "\ufeff" + CSV + "2021-02-01,10,10,10,10,0\r\n"
    body, rows = parse_raw_price_csv(text)
    assert body == text.encode("utf-8")
    assert [row["trading_date"].day for row in rows] == [1, 2]
    assert rows[1]["close_price"] == Decimal("12")

def test_limits(monkeypatch):
    import app.market_data.csv_service as module
    monkeypatch.setattr(module, "MAX_BYTES", 10)
    with pytest.raises(ValueError, match="MB"):
        parse_raw_price_csv(CSV)
    monkeypatch.setattr(module, "MAX_BYTES", 2000000)
    monkeypatch.setattr(module, "MAX_ROWS", 1)
    with pytest.raises(ValueError, match="row limit"):
        parse_raw_price_csv(CSV + "2021-02-01,10,10,10,10,0\n")

@pytest.mark.parametrize("changes", [{"confirm_unadjusted_prices": False}, {"source_name": "bad/name"}, {"currency_code": "usd"}])
def test_declaration_schema(changes):
    with pytest.raises(ValidationError):
        request(**changes)

def test_archive_repeat_and_explicit_source_reconstruction(filing_database):
    database, company, sec_source = filing_database
    listing, alpha_price, _, _ = case(database, company, sec_source)
    text = "\ufeff" + CSV
    result = import_raw_price_csv(database, listing.id, request(csv_text=text))
    repeat = import_raw_price_csv(database, listing.id, request(csv_text=text))
    assert result.created and not repeat.created and repeat.rows_inserted == repeat.rows_updated == 0
    assert repeat.ingestion_run_id == result.ingestion_run_id
    artifact = database.get(CSVPriceArtifact, result.csv_artifact_id)
    assert artifact.body == text.encode() and artifact.sha256 == hashlib.sha256(artifact.body).hexdigest()
    assert alpha_price.close_price == Decimal("10")
    default = reconstruct_sec_market_cap(database, listing.id, cap_request())
    selected = reconstruct_sec_market_cap(database, listing.id, cap_request(price_source_id=result.source_id))
    assert default.manifest["result"]["market_cap_usd"] == "1000"
    assert selected.manifest["result"]["market_cap_usd"] == "1200"
    assert selected.manifest["price"]["csv_artifact_id"] == str(artifact.id)
    assert selected.manifest["price"]["csv_declaration"]["independently_verified"] is False
    assert not reconstruct_sec_market_cap(database, listing.id, cap_request(price_source_id=result.source_id)).created

def test_correction_preserves_archive_and_old_repeat_cannot_revert(filing_database):
    database, company, sec_source = filing_database
    listing, _, _, _ = case(database, company, sec_source)
    first = import_raw_price_csv(database, listing.id, request())
    corrected = CSV.replace("12,13,11,12", "13,14,12,13")
    second = import_raw_price_csv(database, listing.id, request(csv_text=corrected))
    assert second.rows_updated == 1 and second.rows_inserted == 0
    assert database.get(CSVPriceArtifact, first.csv_artifact_id).body == CSV.encode()
    with pytest.raises(CSVPriceConflict, match="later corrections"):
        import_raw_price_csv(database, listing.id, request())
    bar = database.scalar(select(DailyPriceBar).where(DailyPriceBar.source_id == second.source_id))
    assert bar.close_price == Decimal("13") and count(database, CSVPriceArtifact) == 2

@pytest.mark.parametrize("changes", [{"symbol": "OTHER"}, {"currency_code": "EUR"}, {"csv_text": CSV.replace("2021-02-02", "2019-02-02")}])
def test_listing_mismatch_has_no_partial_import(filing_database, changes):
    database, company, sec_source = filing_database
    listing, _, _, _ = case(database, company, sec_source)
    before = count(database, IngestionRun)
    with pytest.raises(CSVPriceConflict):
        import_raw_price_csv(database, listing.id, request(**changes))
    assert count(database, CSVPriceArtifact) == 0 and count(database, IngestionRun) == before
    assert database.scalar(select(DataSource).where(DataSource.provider_name == "csv_fixture")) is None

def test_archive_tampering_blocks_calculation_and_repeat(filing_database):
    database, company, sec_source = filing_database
    listing, _, _, _ = case(database, company, sec_source)
    result = import_raw_price_csv(database, listing.id, request())
    artifact = database.get(CSVPriceArtifact, result.csv_artifact_id)
    artifact.body = b"modified"; database.commit()
    with pytest.raises(ShareSelectionConflict, match="archive"):
        reconstruct_sec_market_cap(database, listing.id, cap_request(price_source_id=result.source_id))
    with pytest.raises(CSVPriceConflict, match="archive"):
        import_raw_price_csv(database, listing.id, request())

def test_routes_download_source_listing_and_errors(filing_database):
    from app.market_data.routes import import_daily_price_csv, download_csv_price_artifact, read_listing_price_sources, read_daily_prices_by_source
    database, company, sec_source = filing_database
    listing, _, _, _ = case(database, company, sec_source)
    result = import_daily_price_csv(listing.id, request(), database)
    assert download_csv_price_artifact(result.csv_artifact_id, database).body == CSV.encode()
    assert result.source_id in {row["source_id"] for row in read_listing_price_sources(listing.id, database)}
    assert len(read_daily_prices_by_source(listing.id, result.source_id, database, limit=100, offset=0)) == 1
    for payload, status in [(request(symbol="OTHER"), 409), (request(csv_text="bad"), 422)]:
        with pytest.raises(HTTPException) as error:
            import_daily_price_csv(listing.id, payload, database)
        assert error.value.status_code == status
    with pytest.raises(HTTPException) as error:
        download_csv_price_artifact(uuid.uuid4(), database)
    assert error.value.status_code == 404

def test_failed_commit_rolls_back_rows_and_archives(filing_database, monkeypatch):
    database, company, sec_source = filing_database
    listing, _, _, _ = case(database, company, sec_source)
    before = count(database, IngestionRun)
    def fail():
        raise RuntimeError("commit failure")
    with monkeypatch.context() as patch:
        patch.setattr(database, "commit", fail)
        with pytest.raises(RuntimeError, match="commit failure"):
            import_raw_price_csv(database, listing.id, request())
    assert count(database, CSVPriceArtifact) == 0 and count(database, IngestionRun) == before
    assert database.scalar(select(DataSource).where(DataSource.provider_name == "csv_fixture")) is None
