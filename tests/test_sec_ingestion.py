import json
import uuid
from datetime import date, datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.filings.routes as routes
from app.core.config import settings
from app.db.database import get_db
from app.db.models.filings import CompanyFiling, FilingSourceArtifact, RawFinancialFact
from app.db.models.identity import Company
from app.db.models.identity_resolution import CompanyIdentifier
from app.filings.schemas import SECImportRequest, SECImportResult
from app.filings.sec_service import SECIdentityError, import_sec_company
from app.main import app
from app.providers.errors import ProviderRateLimitError, ProviderRequestError, ProviderTemporaryError
from app.providers.sec import SECResponse
from test_filing_provenance import count, filing_database
from test_database_migrations import postgres_migrations

ACCESSION = "0000320193-21-000001"
OLD_ACCESSION = "0000320193-20-000001"


def raw(url, body):
    return SECResponse(url, json.dumps(body).encode(), "application/json",
                       datetime(2026, 1, 1, tzinfo=timezone.utc))


def submissions_columns(accession=ACCESSION, filed="2021-02-01", report="2020-12-31"):
    return {"accessionNumber": [accession], "filingDate": [filed], "form": ["10-K"],
            "reportDate": [report], "acceptanceDateTime": [filed + "T20:00:00Z"],
            "primaryDocument": ["report.htm"]}


def fake_client(*, history=False, facts=None, cik=320193):
    files = [{"name": "CIK0000320193-submissions-001.json", "filingFrom": "2020-02-01",
              "filingTo": "2020-02-01"}] if history else []
    row = {"accn": ACCESSION, "form": "10-K", "filed": "2021-02-01", "end": "2020-12-31",
           "val": 123456, "fy": 2020, "fp": "FY"}
    client = Mock()
    client.fetch_submissions.return_value = raw("https://data.sec.gov/submissions/CIK0000320193.json", {
        "cik": str(cik), "filings": {"recent": submissions_columns(), "files": files}})
    client.fetch_company_facts.return_value = raw("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json", {
        "cik": cik, "facts": {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": facts if facts is not None else [row]}}}}})
    client.fetch_history_file.return_value = raw("https://data.sec.gov/submissions/CIK0000320193-submissions-001.json",
        submissions_columns(OLD_ACCESSION, "2020-02-01", "2019-12-31"))
    return client


def map_cik(database, company_id, **changes):
    values = dict(company_id=company_id, scheme="CIK", value="320193", is_primary=True)
    values.update(changes)
    database.add(CompanyIdentifier(**values))
    database.commit()


def test_real_storage_import_and_repeat_are_idempotent(filing_database):
    database, company_id, _ = filing_database
    map_cik(database, company_id)
    client = fake_client()
    first = import_sec_company(database, company_id, SECImportRequest(cik="320193"), client=client)
    second = import_sec_company(database, company_id, SECImportRequest(cik="320193"), client=client)
    assert first.status == "completed" and first.filings_inserted == 1 and first.facts_inserted == 1
    assert first.artifacts_inserted == 2
    assert second.filings_inserted == 0 and second.facts_inserted == 0 and second.facts_existing == 1
    assert second.artifacts_inserted == 0
    filing = database.scalar(select(CompanyFiling))
    row = database.scalar(select(RawFinancialFact))
    assert row.normalization_status == "pending"
    assert row.artifact_id != filing.first_artifact_id
    assert count(database, CompanyFiling) == 1


def test_older_submissions_are_followed(filing_database):
    database, company_id, _ = filing_database
    map_cik(database, company_id)
    client = fake_client(history=True)
    result = import_sec_company(database, company_id, SECImportRequest(cik="320193"), client=client)
    assert result.metadata_history_complete
    assert result.filings_inserted == 2 and result.artifacts_inserted == 3
    client.fetch_history_file.assert_called_once()


def test_excluding_older_history_is_reported(filing_database):
    database, company_id, _ = filing_database
    map_cik(database, company_id)
    client = fake_client(history=True)
    result = import_sec_company(database, company_id, SECImportRequest(cik="320193", include_history=False), client=client)
    assert result.status == "incomplete" and not result.metadata_history_complete
    assert result.warnings
    client.fetch_history_file.assert_not_called()


def test_history_outside_requested_range_is_not_downloaded(filing_database):
    database, company_id, _ = filing_database
    map_cik(database, company_id)
    client = fake_client(history=True)
    result = import_sec_company(database, company_id, SECImportRequest(cik="320193", start_date=date(2021, 1, 1)), client=client)
    assert result.metadata_history_complete and result.filings_seen == 1
    client.fetch_history_file.assert_not_called()


def test_missing_identity_mapping_prevents_network_call(filing_database):
    database, company_id, _ = filing_database
    client = fake_client()
    with pytest.raises(SECIdentityError, match="Register"):
        import_sec_company(database, company_id, SECImportRequest(cik="320193"), client=client)
    client.fetch_submissions.assert_not_called()


def test_conflicting_company_mapping_is_rejected(filing_database):
    database, company_id, _ = filing_database
    map_cik(database, company_id)
    other = Company(legal_name="Conflicting Entity", is_active=True)
    database.add(other)
    database.commit()
    map_cik(database, other.id)
    with pytest.raises(SECIdentityError, match="another company"):
        import_sec_company(database, company_id, SECImportRequest(cik="320193"), client=fake_client())


def test_mapping_must_cover_historical_range(filing_database):
    database, company_id, _ = filing_database
    map_cik(database, company_id, valid_from=date(2022, 1, 1))
    with pytest.raises(SECIdentityError, match="validity"):
        import_sec_company(database, company_id, SECImportRequest(cik="320193", start_date=date(2019, 1, 1)), client=fake_client())


def test_payload_cik_mismatch_saves_nothing(filing_database):
    database, company_id, _ = filing_database
    map_cik(database, company_id)
    with pytest.raises(SECIdentityError, match="does not match"):
        import_sec_company(database, company_id, SECImportRequest(cik="320193"), client=fake_client(cik=999))
    assert count(database, FilingSourceArtifact) == 0


def test_invalid_facts_are_archived_and_reported(filing_database):
    database, company_id, _ = filing_database
    map_cik(database, company_id)
    bad = {"accn": ACCESSION, "form": "10-K", "filed": "2021-02-01", "end": "2030-01-01", "val": 1}
    result = import_sec_company(database, company_id, SECImportRequest(cik="320193"), client=fake_client(facts=[bad]))
    assert result.status == "incomplete" and result.facts_received == result.facts_rejected == 1
    assert result.facts_inserted == 0 and result.warnings
    assert count(database, FilingSourceArtifact) == 2


def test_unselected_tags_and_forms_produce_no_facts(filing_database):
    database, company_id, _ = filing_database
    map_cik(database, company_id)
    result = import_sec_company(database, company_id, SECImportRequest(cik="320193", tags=["OtherTag"]), client=fake_client())
    assert result.status == "no_facts" and result.facts_received == 0
    assert count(database, RawFinancialFact) == 0


def test_write_failure_rolls_back_entire_request(filing_database, monkeypatch):
    database, company_id, _ = filing_database
    map_cik(database, company_id)
    monkeypatch.setattr("app.filings.sec_service.store_filing", Mock(side_effect=ValueError("storage conflict")))
    with pytest.raises(ValueError, match="storage conflict"):
        import_sec_company(database, company_id, SECImportRequest(cik="320193"), client=fake_client())
    assert count(database, FilingSourceArtifact) == 0
    assert count(database, CompanyFiling) == 0


def test_schema_does_not_accept_backwards_range():
    with pytest.raises(ValueError, match="start_date"):
        SECImportRequest(cik="320193", start_date=date(2021, 1, 1), end_date=date(2020, 1, 1))


@pytest.mark.parametrize("error,status", [
    (LookupError("missing company"), 404), (SECIdentityError("identity conflict"), 409),
    (ProviderRequestError("configuration"), 400), (ProviderRateLimitError("rate limit"), 429),
    (ProviderTemporaryError("bad feed"), 502), (ValueError("invalid data"), 422),
])
def test_import_route_reports_errors(monkeypatch, error, status):
    monkeypatch.setattr(routes, "import_sec_company", Mock(side_effect=error))
    app.dependency_overrides[get_db] = lambda: Mock()
    try:
        with TestClient(app) as client:
            response = client.post(f"/filings/companies/{uuid.uuid4()}/import-sec", json={"cik": "320193"})
        assert response.status_code == status
        assert response.json()["detail"] == str(error)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_import_route_returns_summary(monkeypatch):
    company_id = uuid.uuid4()
    result = SECImportResult(company_id=company_id, cik="0000320193", status="completed",
        filings_seen=1, filings_inserted=1, facts_received=1, facts_inserted=1, facts_existing=0,
        facts_rejected=0, artifacts_inserted=2, metadata_history_complete=True, warnings=[])
    importer = Mock(return_value=result)
    monkeypatch.setattr(routes, "import_sec_company", importer)
    app.dependency_overrides[get_db] = lambda: Mock()
    try:
        with TestClient(app) as client:
            response = client.post(f"/filings/companies/{company_id}/import-sec", json={"cik": "320193"})
        assert response.status_code == 200 and response.json()["facts_inserted"] == 1
        assert importer.call_args.args[1] == company_id
        assert importer.call_args.args[2].cik == "0000320193"
    finally:
        app.dependency_overrides.pop(get_db, None)



def test_companyfacts_cik_mismatch_saves_nothing(filing_database):
    database, company_id, _ = filing_database
    map_cik(database, company_id)
    client = fake_client()
    bad = json.loads(client.fetch_company_facts.return_value.body)
    bad["cik"] = 999
    client.fetch_company_facts.return_value = raw(client.fetch_company_facts.return_value.url, bad)
    with pytest.raises(SECIdentityError, match="company facts CIK"):
        import_sec_company(database, company_id, SECImportRequest(cik="320193"), client=client)
    assert count(database, FilingSourceArtifact) == 0


def test_fact_without_submission_metadata_keeps_unknown_report_period(filing_database):
    database, company_id, _ = filing_database
    map_cik(database, company_id)
    row = {"accn": OLD_ACCESSION, "form": "10-K", "filed": "2020-02-01", "end": "2019-12-31", "val": 100}
    result = import_sec_company(database, company_id, SECImportRequest(cik="320193"), client=fake_client(facts=[row]))
    filing = database.scalar(select(CompanyFiling).where(CompanyFiling.accession_number == OLD_ACCESSION))
    assert filing.report_period is None and filing.accepted_at is None
    assert filing.filed_date == date(2020, 2, 1)
    assert result.facts_inserted == 1


def test_malformed_columns_save_nothing(filing_database):
    database, company_id, _ = filing_database
    map_cik(database, company_id)
    client = fake_client()
    bad = json.loads(client.fetch_submissions.return_value.body)
    bad["filings"]["recent"]["form"] = []
    client.fetch_submissions.return_value = raw(client.fetch_submissions.return_value.url, bad)
    with pytest.raises(ProviderTemporaryError, match="columns"):
        import_sec_company(database, company_id, SECImportRequest(cik="320193"), client=client)
    assert count(database, FilingSourceArtifact) == 0


def test_empty_companyfacts_are_archived(filing_database):
    database, company_id, _ = filing_database
    map_cik(database, company_id)
    result = import_sec_company(database, company_id, SECImportRequest(cik="320193"), client=fake_client(facts=[]))
    assert result.status == "no_facts" and result.artifacts_inserted == 2
    assert count(database, RawFinancialFact) == 0
