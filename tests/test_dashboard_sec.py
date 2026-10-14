"""HTTP SEC workflow used by the dashboard; provider responses are synthetic."""
from unittest.mock import Mock

from app.db.models.identity import Company
from app.db.models.identity_resolution import CompanyIdentifier
from app.db.models.filings import CompanyFiling, FilingSourceArtifact, RawFinancialFact
from app.db.models.share_normalization import NormalizedShareFact
from app.providers.errors import ProviderRateLimitError
from test_dashboard import http_client
from test_filing_provenance import count
from test_sec_ingestion import fake_client, map_cik


def company_case(database, mapped=True):
    company = Company(legal_name="SEC dashboard fixture")
    database.add(company); database.commit()
    if mapped:
        map_cik(database, company.id)
    return company


def provider(monkeypatch, client=None):
    selected = client if client is not None else fake_client()
    factory = Mock(return_value=selected)
    monkeypatch.setattr("app.filings.sec_service.SECClient", factory)
    return selected, factory


def test_company_cik_choices_are_scoped(http_client):
    client, database = http_client
    company = company_case(database)
    other = Company(legal_name="Another company"); database.add(other); database.commit()
    map_cik(database, other.id, value="999999")
    response = client.get(f"/identity-resolution/companies/{company.id}/identifiers")
    assert response.status_code == 200
    assert len(response.json()) == 1 and response.json()[0]["value"] == "320193"
    assert response.json()[0]["company_id"] == str(company.id)


def test_sec_import_then_explicit_review_and_repeats(http_client, monkeypatch):
    client, database = http_client
    company = company_case(database)
    provider(monkeypatch)
    root = f"/filings/companies/{company.id}"
    payload = {"cik": "0000320193", "start_date": "2020-01-01", "end_date": "2021-12-31", "include_history": True}
    imported = client.post(root + "/import-sec", json=payload)
    assert imported.status_code == 200
    assert imported.json()["facts_inserted"] == imported.json()["filings_inserted"] == 1
    assert imported.json()["artifacts_inserted"] == 2
    assert count(database, NormalizedShareFact) == 0
    repeated = client.post(root + "/import-sec", json=payload).json()
    assert repeated["filings_inserted"] == repeated["facts_inserted"] == repeated["artifacts_inserted"] == 0
    assert repeated["facts_existing"] == 1
    reviewed = client.post(root + "/normalize-shares")
    assert reviewed.status_code == 200
    assert reviewed.json()["accepted"] == reviewed.json()["facts_reviewed"] == reviewed.json()["reviews_inserted"] == 1
    second_review = client.post(root + "/normalize-shares").json()
    assert second_review["reviews_inserted"] == second_review["reviews_updated"] == 0
    assert count(database, FilingSourceArtifact) == 2 and count(database, RawFinancialFact) == 1
    from sqlalchemy import select
    assert database.scalar(select(RawFinancialFact)).normalization_status == "pending"
    inspected = client.get(f"/dashboard/api/companies/{company.id}/shares").json()["items"]
    assert inspected[0]["status"] == "accepted" and inspected[0]["shares_text"] == "123456"


def test_invalid_range_never_contacts_provider(http_client, monkeypatch):
    client, database = http_client
    company = company_case(database)
    _, factory = provider(monkeypatch)
    response = client.post(f"/filings/companies/{company.id}/import-sec", json={"cik": "320193", "start_date": "2021-01-01", "end_date": "2020-01-01"})
    assert response.status_code == 422
    factory.assert_not_called()
    assert count(database, CompanyFiling) == 0


def test_missing_cik_registration_is_rejected_without_network_or_archive(http_client, monkeypatch):
    client, database = http_client
    company = company_case(database, mapped=False)
    _, factory = provider(monkeypatch)
    response = client.post(f"/filings/companies/{company.id}/import-sec", json={"cik": "320193"})
    assert response.status_code == 409 and "Register" in response.json()["detail"]
    factory.assert_not_called()
    assert count(database, FilingSourceArtifact) == 0


def test_incomplete_history_and_warnings_remain_visible(http_client, monkeypatch):
    client, database = http_client
    company = company_case(database)
    upstream, _ = provider(monkeypatch, fake_client(history=True))
    response = client.post(f"/filings/companies/{company.id}/import-sec", json={"cik": "320193", "include_history": False})
    assert response.status_code == 200
    assert not response.json()["metadata_history_complete"] and response.json()["warnings"]
    upstream.fetch_history_file.assert_not_called()


def test_rate_limit_surfaces_without_partial_archive(http_client, monkeypatch):
    client, database = http_client
    company = company_case(database)
    upstream, _ = provider(monkeypatch)
    upstream.fetch_submissions.side_effect = ProviderRateLimitError("SEC rate limited this request")
    response = client.post(f"/filings/companies/{company.id}/import-sec", json={"cik": "320193"})
    assert response.status_code == 429 and "rate limited" in response.json()["detail"]
    assert count(database, FilingSourceArtifact) == 0


def test_review_empty_inventory_is_truthful(http_client):
    client, database = http_client
    company = company_case(database, mapped=False)
    response = client.post(f"/filings/companies/{company.id}/normalize-shares")
    assert response.status_code == 200
    assert response.json()["facts_reviewed"] == response.json()["accepted"] == response.json()["excluded"] == response.json()["conflicts"] == 0
    assert count(database, NormalizedShareFact) == 0
