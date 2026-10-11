import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.database import Base, get_db
from app.db.models.identity import Company
from app.db.models.sec_market_cap import SECMarketCapSnapshot
from app.dashboard.routes import companies, company_records, price_sources, prices, snapshot
from app.market_data.csv_service import import_raw_price_csv
from app.market_cap.sec_service import reconstruct_sec_market_cap
from test_csv_prices import request as csv_request
from test_sec_market_cap import case, request as cap_request
from test_filing_provenance import filing_database, count
from test_database_migrations import postgres_migrations


def seed(database, company_id, source_id):
    listing, price, _, _ = case(database, company_id, source_id)
    imported = import_raw_price_csv(database, listing.id, csv_request())
    result = reconstruct_sec_market_cap(database, listing.id, cap_request(price_source_id=imported.source_id))
    return listing, price, imported, result


def test_company_search_literal_and_stable_pagination(filing_database):
    database, company_id, _ = filing_database
    database.add_all([Company(legal_name="Percent % Company"), Company(legal_name="Underscore _ Company", is_active=False)])
    database.commit()
    assert [row["legal_name"] for row in companies(database, q="%", limit=25, offset=0)["items"]] == ["Percent % Company"]
    assert [row["legal_name"] for row in companies(database, q="_", limit=25, offset=0)["items"]] == ["Underscore _ Company"]
    assert len(companies(database, q="COMPANY", limit=25, offset=0)["items"]) == 3
    first = companies(database, limit=1, offset=0)
    second = companies(database, limit=1, offset=1)
    assert first["has_more"] and first["items"][0]["id"] != second["items"][0]["id"]
    assert not companies(database, limit=25, offset=99)["has_more"]


@pytest.mark.parametrize("section", ["filings", "shares", "mappings", "securities", "listings", "snapshots", "artifacts", "facts", "csv-archives"])
def test_sections_paginate_and_never_mix_companies(filing_database, section):
    database, company_id, source_id = filing_database
    seed(database, company_id, source_id)
    other = Company(legal_name="Other company")
    database.add(other); database.commit()
    result = company_records(company_id, section, database, limit=1, offset=0)
    assert len(result["items"]) == 1
    assert company_records(other.id, section, database, limit=50, offset=0)["items"] == []
    assert all("body" not in row and "manifest_json" not in row for row in result["items"])
    if section == "facts":
        assert result["items"][0]["context"]["scope"] == "entity"
    with pytest.raises(HTTPException) as error:
        company_records(uuid.uuid4(), section, database)
    assert error.value.status_code == 404


def test_prices_keep_decimal_text_filters_and_company_boundary(filing_database):
    database, company_id, source_id = filing_database
    listing, price, imported, _ = seed(database, company_id, source_id)
    result = prices(company_id, listing.id, imported.source_id, database, start=date(2021, 2, 2), end=date(2021, 2, 2))
    assert result["items"][0]["close_price"] == "12.00000000"
    assert prices(company_id, listing.id, price.source_id, database)["items"][0]["close_price"] == "10.00000000"
    assert prices(company_id, listing.id, imported.source_id, database, end=date(2021, 2, 1))["items"] == []
    with pytest.raises(HTTPException) as error:
        prices(company_id, listing.id, imported.source_id, database, start=date(2021, 2, 3), end=date(2021, 2, 2))
    assert error.value.status_code == 422
    other = Company(legal_name="Other company"); database.add(other); database.commit()
    with pytest.raises(HTTPException) as error:
        prices(other.id, listing.id, imported.source_id, database)
    assert error.value.status_code == 404


def test_sources_show_counts_but_do_not_imply_coverage(filing_database):
    database, company_id, source_id = filing_database
    listing, _, imported, _ = seed(database, company_id, source_id)
    result = price_sources(company_id, listing.id, database)
    csv = next(row for row in result if row["source_id"] == str(imported.source_id))
    assert csv["rows"] == 1 and csv["first_date"] == csv["last_date"] == "2021-02-02"
    with pytest.raises(HTTPException) as error:
        price_sources(company_id, uuid.uuid4(), database)
    assert error.value.status_code == 404


def test_snapshot_inspection_reads_captured_inputs_without_recalculation(filing_database):
    database, company_id, source_id = filing_database
    listing, price, imported, result = seed(database, company_id, source_id)
    before = count(database, SECMarketCapSnapshot)
    price.close_price = Decimal("999"); database.commit()
    read = snapshot(company_id, result.snapshot_id, database)
    assert read["manifest"]["result"]["market_cap_usd"] == "1200"
    assert read["manifest"]["price"]["csv_artifact_id"] == str(imported.csv_artifact_id)
    assert read["input_hash"] == result.input_hash
    assert count(database, SECMarketCapSnapshot) == before
    other = Company(legal_name="Other company"); database.add(other); database.commit()
    with pytest.raises(HTTPException) as error:
        snapshot(other.id, result.snapshot_id, database)
    assert error.value.status_code == 404


@pytest.fixture
def http_client():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    database = Session(engine, autoflush=False)
    def override():
        yield database
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            yield client, database
    finally:
        app.dependency_overrides.pop(get_db, None)
        database.close(); engine.dispose()


def test_http_assets_and_invalid_paths(http_client):
    client, _ = http_client
    for path in ["/dashboard", "/dashboard/", "/dashboard/assets/dashboard.js", "/dashboard/assets/dashboard.css"]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
    assert "Data workspace" in client.get("/dashboard").text
    assert client.get("/dashboard/assets/arbitrary.txt").status_code == 422
    assert client.get("/dashboard/api/companies?limit=201").status_code == 422
    assert client.get("/dashboard/api/companies?offset=-1").status_code == 422
    assert client.get("/dashboard/api/companies/not-a-uuid/filings").status_code == 422
    assert client.post("/dashboard/api/companies").status_code == 405


def test_http_empty_inventory_and_evidence_flow(http_client):
    client, database = http_client
    assert client.get("/dashboard/api/companies").json()["items"] == []
    from app.db.models.market_data import DataSource
    company = Company(legal_name="<script>alert('x')</script>")
    source = DataSource(provider_name="sec", dataset_name="COMPANY_FACTS")
    database.add_all([company, source]); database.commit()
    listing, _, imported, result = seed(database, company.id, source.id)
    root = f"/dashboard/api/companies/{company.id}"
    assert client.get("/dashboard/api/companies").json()["items"][0]["legal_name"] == company.legal_name
    assert client.get(root + "/filings").status_code == 200
    evidence = client.get(root + f"/snapshots/{result.snapshot_id}")
    assert evidence.status_code == 200 and evidence.json()["manifest"]["result"]["market_cap_usd"] == "1200"
    prices_response = client.get(root + f"/listings/{listing.id}/prices", params={"source_id": str(imported.source_id)})
    assert prices_response.json()["items"][0]["close_price"] == "12.00000000"
    assert client.get(root + "/unsupported").status_code == 422
    archive = client.get(f"/market-data/csv-artifacts/{imported.csv_artifact_id}")
    assert archive.content == csv_request().csv_text.encode("utf-8")
