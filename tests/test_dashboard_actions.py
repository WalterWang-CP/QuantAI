"""HTTP integration of the existing write APIs used by dashboard forms."""
import hashlib
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from app.db.models.identity import Company
from app.db.models.market_data import DataSource, DailyPriceBar
from app.db.models.csv_prices import CSVPriceArtifact
from app.db.models.sec_market_cap import SECMarketCapSnapshot
from app.db.models.share_scope import CompanyShareScope
from test_dashboard import http_client
from test_sec_market_cap import case, request as cap_request
from test_csv_prices import request as csv_request, CSV
from test_filing_provenance import count


def setup_case(database):
    company = Company(legal_name="Dashboard actions fixture")
    source = DataSource(provider_name="sec", dataset_name="COMPANY_FACTS")
    database.add_all([company, source]); database.commit()
    listing, price, _, _ = case(database, company.id, source.id)
    return company, listing, price


def import_csv(client, listing, **changes):
    return client.post(f"/market-data/listings/{listing.id}/daily/import-csv", json=csv_request(**changes).model_dump(mode="json"))


def test_import_receipt_exact_utf8_archive_and_repeat(http_client):
    client, database = http_client
    _, listing, price = setup_case(database)
    text = "\ufeff" + CSV
    first = import_csv(client, listing, csv_text=text)
    assert first.status_code == 200
    result = first.json()
    assert result["created"] and result["rows_inserted"] == 1
    archive = client.get(f"/market-data/csv-artifacts/{result['csv_artifact_id']}")
    assert archive.content == text.encode("utf-8")
    assert result["sha256"] == hashlib.sha256(archive.content).hexdigest()
    second = import_csv(client, listing, csv_text=text).json()
    assert not second["created"] and second["ingestion_run_id"] == result["ingestion_run_id"]
    assert second["rows_updated"] == second["rows_inserted"] == 0
    database.refresh(price)
    assert price.close_price == Decimal("10") and count(database, CSVPriceArtifact) == 1


@pytest.mark.parametrize("changes,status", [
    ({"confirm_unadjusted_prices": False}, 422),
    ({"csv_text": CSV.replace("close", "adjusted_close")}, 422),
    ({"symbol": "WRONG"}, 409),
])
def test_rejected_imports_leave_no_archive_or_changed_prices(http_client, changes, status):
    client, database = http_client
    _, listing, price = setup_case(database)
    body = csv_request().model_dump(mode="json"); body.update(changes)
    response = client.post(f"/market-data/listings/{listing.id}/daily/import-csv", json=body)
    assert response.status_code == status and response.json()["detail"]
    assert count(database, CSVPriceArtifact) == 0
    database.refresh(price)
    assert price.close_price == Decimal("10") and count(database, DailyPriceBar) == 1


def test_http_corrected_file_rejects_old_repeat(http_client):
    client, database = http_client
    _, listing, _ = setup_case(database)
    first = import_csv(client, listing).json()
    corrected = CSV.replace("12,13,11,12", "13,14,12,13")
    assert import_csv(client, listing, csv_text=corrected).json()["rows_updated"] == 1
    response = import_csv(client, listing)
    assert response.status_code == 409 and "later corrections" in response.json()["detail"]
    import uuid
    bar = database.scalar(select(DailyPriceBar).where(DailyPriceBar.source_id == uuid.UUID(first["source_id"])))
    assert bar.close_price == Decimal("13") and count(database, CSVPriceArtifact) == 2


def test_preview_and_calculation_explicit_csv_source_and_repeat(http_client):
    client, database = http_client
    company, listing, _ = setup_case(database)
    imported = import_csv(client, listing).json()
    root = f"/dashboard/api/companies/{company.id}"
    shares = client.get(f"/filings/securities/{listing.security_id}/selected-shares", params={"valuation_date": "2021-02-02", "max_age_days": 400})
    assert shares.status_code == 200 and shares.json()["shares_outstanding"] == "100"
    prices = client.get(root + f"/listings/{listing.id}/prices", params={"source_id": imported["source_id"], "end": "2021-02-02", "limit": 1}).json()
    assert prices["items"][0]["close_price"] == "12.00000000"
    payload = cap_request(price_source_id=imported["source_id"]).model_dump(mode="json")
    path = f"/market-cap/listings/{listing.id}/reconstruct-sec"
    response = client.post(path, json=payload)
    assert response.status_code == 200
    first = response.json()
    assert first["created"] and first["manifest"]["result"]["market_cap_usd"] == "1200"
    assert first["manifest"]["price"]["source_id"] == imported["source_id"]
    assert first["manifest"]["price"]["csv_artifact_id"] == imported["csv_artifact_id"]
    repeated = client.post(path, json=payload).json()
    assert not repeated["created"] and repeated["snapshot_id"] == first["snapshot_id"]
    stored = client.get(root + f"/snapshots/{first['snapshot_id']}").json()
    assert stored["manifest"] == first["manifest"] and count(database, SECMarketCapSnapshot) == 1


def test_unconfirmed_split_coverage_and_stale_price_reject_without_snapshot(http_client):
    client, database = http_client
    _, listing, _ = setup_case(database)
    imported = import_csv(client, listing).json()
    payload = cap_request(price_source_id=imported["source_id"]).model_dump(mode="json")
    path = f"/market-cap/listings/{listing.id}/reconstruct-sec"
    unconfirmed = dict(payload, confirm_split_coverage=False)
    assert client.post(path, json=unconfirmed).status_code == 422
    stale = dict(payload, valuation_date="2021-02-15", max_price_age_days=7)
    assert client.post(path, json=stale).status_code == 409
    assert count(database, SECMarketCapSnapshot) == 0


def test_missing_mapping_is_visible_in_preview_and_save(http_client):
    client, database = http_client
    company, listing, _ = setup_case(database)
    imported = import_csv(client, listing).json()
    database.execute(delete(CompanyShareScope).where(CompanyShareScope.company_id == company.id)); database.commit()
    preview = client.get(f"/filings/securities/{listing.security_id}/selected-shares", params={"valuation_date": "2021-02-02"})
    assert preview.status_code == 404 and preview.json()["detail"]
    payload = cap_request(price_source_id=imported["source_id"]).model_dump(mode="json")
    assert client.post(f"/market-cap/listings/{listing.id}/reconstruct-sec", json=payload).status_code == 404
    assert count(database, SECMarketCapSnapshot) == 0
