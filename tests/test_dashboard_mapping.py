"""Evidence-backed mapping HTTP flow used by the dashboard."""
from datetime import date

import pytest
from sqlalchemy import delete, select

from app.db.models.identity import Company, Security
from app.db.models.market_data import DataSource
from app.db.models.share_scope import CompanyShareScope
from app.db.models.sec_market_cap import SECMarketCapSnapshot
from test_dashboard import http_client
from test_sec_market_cap import case
from test_filing_provenance import count


def setup_case(database):
    company = Company(legal_name="Mapping dashboard fixture")
    source = DataSource(provider_name="sec", dataset_name="COMPANY_FACTS")
    database.add_all([company, source]); database.commit()
    listing, _, _, _ = case(database, company.id, source.id)
    database.get(Security, listing.security_id).start_date = date(2020, 1, 1)
    database.execute(delete(CompanyShareScope).where(CompanyShareScope.company_id == company.id)); database.commit()
    payload = dict(security_id=str(listing.security_id), valid_from="2020-01-01", valid_to="2025-12-31",
        known_date="2020-01-01", evidence_url="https://example.com/fixture-share-class",
        evidence_note="Synthetic fixture verifies one common-share class for this entire interval.", confirm_single_common_class=True)
    return company, listing, payload


def test_mapping_save_repeat_and_eligible_selection(http_client):
    client, database = http_client
    company, listing, payload = setup_case(database)
    path = f"/filings/companies/{company.id}/share-scope"
    first = client.post(path, json=payload)
    assert first.status_code == 200 and first.json()["scope_type"] == "single_common_class"
    second = client.post(path, json=payload)
    assert second.status_code == 200 and second.json()["id"] == first.json()["id"]
    assert count(database, CompanyShareScope) == 1 and count(database, SECMarketCapSnapshot) == 0
    inspected = client.get(f"/dashboard/api/companies/{company.id}/mappings").json()["items"]
    assert inspected[0]["evidence_note"] == payload["evidence_note"]
    selected = client.get(f"/filings/securities/{listing.security_id}/selected-shares", params={"valuation_date": "2021-02-02"})
    assert selected.status_code == 200 and selected.json()["mapping_id"] == first.json()["id"]


def test_overlap_rejects_changed_evidence_without_overwrite(http_client):
    client, database = http_client
    company, _, payload = setup_case(database)
    path = f"/filings/companies/{company.id}/share-scope"
    assert client.post(path, json=payload).status_code == 200
    response = client.post(path, json=dict(payload, evidence_note="A different assertion must not overwrite the earlier mapping."))
    assert response.status_code == 409
    assert database.scalar(select(CompanyShareScope)).evidence_note == payload["evidence_note"]
    assert count(database, CompanyShareScope) == 1


def test_other_company_security_is_rejected(http_client):
    client, database = http_client
    company, _, payload = setup_case(database)
    other = Company(legal_name="Other mapping company"); database.add(other); database.flush()
    security = Security(company_id=other.id, name="Other common stock", security_type="common_stock", start_date=date(2020, 1, 1))
    database.add(security); database.commit()
    response = client.post(f"/filings/companies/{company.id}/share-scope", json=dict(payload, security_id=str(security.id)))
    assert response.status_code == 409 and count(database, CompanyShareScope) == 0


@pytest.mark.parametrize("kind", ["adr", "common_stock"])
def test_unsupported_or_multiple_overlapping_securities_are_rejected(http_client, kind):
    client, database = http_client
    company, _, payload = setup_case(database)
    other = Security(company_id=company.id, name="Other class", security_type=kind, start_date=date(2020, 1, 1))
    database.add(other); database.commit()
    if kind == "adr":
        payload["security_id"] = str(other.id)
    response = client.post(f"/filings/companies/{company.id}/share-scope", json=payload)
    assert response.status_code == 409 and count(database, CompanyShareScope) == 0


@pytest.mark.parametrize("changes,status", [
    ({"valid_to": "2019-01-01"}, 422),
    ({"known_date": "2019-01-01"}, 422),
    ({"confirm_single_common_class": False}, 422),
    ({"valid_from": "2019-01-01"}, 409),
])
def test_invalid_declarations_create_no_mapping(http_client, changes, status):
    client, database = http_client
    company, _, payload = setup_case(database)
    response = client.post(f"/filings/companies/{company.id}/share-scope", json=dict(payload, **changes))
    assert response.status_code == status and count(database, CompanyShareScope) == 0
