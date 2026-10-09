import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.db.models.identity import Company, Security
from app.db.models.share_scope import CompanyShareScope
from app.filings.share_normalization import normalize_company_shares
from app.filings.share_selection import ShareScopeCreate, ShareSelectionConflict, create_share_scope, select_security_shares
from test_database_migrations import postgres_migrations
from test_filing_provenance import count, fact, filing_database, payload, store


def setup(database, company_id, *, known=date(2020, 1, 1), end=date(2025, 12, 31)):
    security = Security(company_id=company_id, name="Common shares", security_type="common_stock")
    database.add(security)
    database.commit()
    request = ShareScopeCreate(security_id=security.id, valid_from=date(2020, 1, 1), valid_to=end,
        known_date=known, evidence_url="https://www.sec.gov/Archives/edgar/data/test.htm",
        evidence_note="Test fixture confirms a single common share class for this period.",
        confirm_single_common_class=True)
    mapping = create_share_scope(database, company_id, request)
    return security, mapping, request


def add(database, company_id, source_id, *, value=100, accession="0000320193-21-000001",
        filed=date(2021, 2, 1), accepted=None, period=date(2020, 12, 31), context=None):
    result = store(database, payload(company_id, source_id, accession_number=accession,
        filed_date=filed, accepted_at=accepted, report_period=period,
        facts=[fact(value=value, period_end=period, context=context or {"scope": "entity"})]))
    database.commit()
    return result


def test_scope_repeat_is_idempotent_and_evidence_is_immutable(filing_database):
    database, company_id, _ = filing_database
    security, mapping, request = setup(database, company_id)
    assert create_share_scope(database, company_id, request).id == mapping.id
    assert count(database, CompanyShareScope) == 1
    with pytest.raises(ShareSelectionConflict, match="overlapping"):
        create_share_scope(database, company_id, request.model_copy(update={"evidence_note": "A changed assertion must not replace original evidence."}))
    assert database.get(CompanyShareScope, mapping.id).evidence_note == request.evidence_note


def test_scope_rejects_other_company_and_adr(filing_database):
    database, company_id, _ = filing_database
    other = Company(legal_name="Other")
    database.add(other); database.commit()
    security = Security(company_id=other.id, name="Other shares", security_type="common_stock")
    database.add(security); database.commit()
    request = ShareScopeCreate(security_id=security.id, valid_from=date(2020, 1, 1), valid_to=date(2025, 1, 1),
        known_date=date(2020, 1, 1), evidence_url="https://example.com/evidence",
        evidence_note="Explicit fixture evidence for a single common share class.", confirm_single_common_class=True)
    with pytest.raises(ShareSelectionConflict, match="different company"):
        create_share_scope(database, company_id, request)
    security.company_id = company_id; security.security_type = "adr"; database.commit()
    with pytest.raises(ShareSelectionConflict, match="common_stock only"):
        create_share_scope(database, company_id, request)


def test_additional_security_blocks_mapping_and_selection(filing_database):
    database, company_id, source_id = filing_database
    security, _, request = setup(database, company_id)
    add(database, company_id, source_id); normalize_company_shares(database, company_id)
    database.add(Security(company_id=company_id, name="Class B", security_type="common_stock")); database.commit()
    with pytest.raises(ShareSelectionConflict, match="overlapping securities"):
        create_share_scope(database, company_id, request)
    with pytest.raises(ShareSelectionConflict, match="overlapping securities"):
        select_security_shares(database, security.id, date(2021, 2, 2))


def test_daily_cutoff_and_provenance(filing_database):
    database, company_id, source_id = filing_database
    security, mapping, _ = setup(database, company_id)
    result = add(database, company_id, source_id, value=Decimal("99999999999999999999999999"))
    normalize_company_shares(database, company_id)
    with pytest.raises(LookupError, match="No eligible"):
        select_security_shares(database, security.id, date(2021, 2, 1))
    selected = select_security_shares(database, security.id, date(2021, 2, 2))
    assert selected.shares_outstanding == Decimal("99999999999999999999999999")
    assert selected.filing_id == result.filing_id and selected.artifact_id == result.artifact_id
    assert selected.mapping_id == mapping.id and selected.raw_fact_id in selected.equivalent_raw_fact_ids


def test_amendment_only_changes_later_cutoffs(filing_database):
    database, company_id, source_id = filing_database
    security, _, _ = setup(database, company_id)
    original = add(database, company_id, source_id)
    amendment = add(database, company_id, source_id, accession="0000320193-21-000002", filed=date(2021, 3, 1), value=200)
    normalize_company_shares(database, company_id)
    assert select_security_shares(database, security.id, date(2021, 2, 15)).filing_id == original.filing_id
    assert select_security_shares(database, security.id, date(2021, 3, 2)).filing_id == amendment.filing_id


def test_future_conflict_does_not_invalidate_earlier_revision(filing_database):
    database, company_id, source_id = filing_database
    security, _, _ = setup(database, company_id)
    original = add(database, company_id, source_id)
    for value in (200, 300):
        add(database, company_id, source_id, accession="0000320193-21-000002", filed=date(2021, 3, 1), value=value)
    normalize_company_shares(database, company_id)
    assert select_security_shares(database, security.id, date(2021, 2, 15)).filing_id == original.filing_id
    with pytest.raises(ShareSelectionConflict, match="conflicting shares"):
        select_security_shares(database, security.id, date(2021, 3, 2))


def test_same_day_exact_acceptance_orders_revisions(filing_database):
    database, company_id, source_id = filing_database
    security, _, _ = setup(database, company_id)
    add(database, company_id, source_id, accepted=datetime(2021, 2, 1, 10, tzinfo=timezone.utc))
    later = add(database, company_id, source_id, accession="0000320193-21-000002", value=200,
        accepted=datetime(2021, 2, 1, 20, tzinfo=timezone.utc))
    normalize_company_shares(database, company_id)
    assert select_security_shares(database, security.id, date(2021, 2, 2)).filing_id == later.filing_id


def test_same_day_unknown_acceptance_does_not_guess(filing_database):
    database, company_id, source_id = filing_database
    security, _, _ = setup(database, company_id)
    add(database, company_id, source_id)
    add(database, company_id, source_id, accession="0000320193-21-000002", value=200,
        accepted=datetime(2021, 2, 1, 20, tzinfo=timezone.utc))
    normalize_company_shares(database, company_id)
    with pytest.raises(ShareSelectionConflict, match="conflicting shares"):
        select_security_shares(database, security.id, date(2021, 2, 2))


def test_equal_ties_are_deterministic_and_keep_all_provenance(filing_database):
    database, company_id, source_id = filing_database
    security, _, _ = setup(database, company_id)
    add(database, company_id, source_id)
    add(database, company_id, source_id, context={"scope": "entity", "frame": "CY2020Q4I"})
    normalize_company_shares(database, company_id)
    first = select_security_shares(database, security.id, date(2021, 2, 2))
    second = select_security_shares(database, security.id, date(2021, 2, 2))
    assert first == second and len(first.equivalent_raw_fact_ids) == 2


def test_missing_review_requires_normalization(filing_database):
    database, company_id, source_id = filing_database
    security, _, _ = setup(database, company_id)
    add(database, company_id, source_id)
    with pytest.raises(ShareSelectionConflict, match="run normalize-shares again"):
        select_security_shares(database, security.id, date(2021, 2, 2))


def test_mapping_known_date_and_validity_are_enforced(filing_database):
    database, company_id, source_id = filing_database
    security, _, _ = setup(database, company_id, known=date(2021, 3, 1), end=date(2021, 12, 31))
    add(database, company_id, source_id); normalize_company_shares(database, company_id)
    for cutoff in (date(2021, 2, 2), date(2022, 1, 1)):
        with pytest.raises(LookupError, match="No evidence-backed"):
            select_security_shares(database, security.id, cutoff)
    assert select_security_shares(database, security.id, date(2021, 3, 1)).shares_outstanding == 100


def test_stale_observation_refuses_silent_carry_forward(filing_database):
    database, company_id, source_id = filing_database
    security, _, _ = setup(database, company_id)
    add(database, company_id, source_id); normalize_company_shares(database, company_id)
    with pytest.raises(ShareSelectionConflict, match="max_age_days"):
        select_security_shares(database, security.id, date(2022, 2, 15))


def test_later_report_of_older_period_does_not_replace_newer_observation(filing_database):
    database, company_id, source_id = filing_database
    security, _, _ = setup(database, company_id)
    newer = add(database, company_id, source_id, period=date(2021, 1, 15))
    add(database, company_id, source_id, accession="0000320193-21-000002", filed=date(2021, 3, 1), value=200)
    normalize_company_shares(database, company_id)
    assert select_security_shares(database, security.id, date(2021, 3, 2)).filing_id == newer.filing_id


def test_route_errors_and_mapping_read(filing_database):
    database, company_id, source_id = filing_database
    from app.filings.routes import read_selected_shares, read_share_scopes, register_share_scope, read_company_securities
    security, mapping, request = setup(database, company_id)
    assert register_share_scope(company_id, request, database).id == mapping.id
    assert read_share_scopes(company_id, database)[0].id == mapping.id
    assert read_company_securities(company_id, database)[0].id == security.id
    add(database, company_id, source_id); normalize_company_shares(database, company_id)
    assert read_selected_shares(security.id, date(2021, 2, 2), database, 400).shares_outstanding == 100
    with pytest.raises(HTTPException) as error:
        read_selected_shares(uuid.uuid4(), date(2021, 2, 2), database, 400)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        read_selected_shares(security.id, date(2022, 2, 15), database, 400)
    assert error.value.status_code == 409


@pytest.mark.parametrize("changes", [
    {"confirm_single_common_class": False},
    {"valid_to": date(2019, 12, 31)},
    {"known_date": date(2019, 12, 31)},
    {"evidence_url": "file:///tmp/evidence"},
    {"evidence_note": ""},
])
def test_scope_schema_rejects_invalid_assertions(changes):
    values = dict(security_id=uuid.uuid4(), valid_from=date(2020, 1, 1), valid_to=date(2025, 1, 1),
        known_date=date(2020, 1, 1), evidence_url="https://example.com/evidence",
        evidence_note="An explicit evidence statement for the company common share class.", confirm_single_common_class=True)
    values.update(changes)
    with pytest.raises(ValidationError):
        ShareScopeCreate(**values)
