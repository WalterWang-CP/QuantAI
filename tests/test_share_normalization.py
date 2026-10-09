import uuid
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from app.db.models.filings import RawFinancialFact
from app.db.models.fundamentals import SharesOutstandingObservation
from app.db.models.share_normalization import NormalizedShareFact
from app.filings.share_normalization import _review, normalize_company_shares
from test_database_migrations import postgres_migrations
from test_filing_provenance import count, fact, filing_database, payload, store


def add(database, company_id, source_id, *, facts=None, **changes):
    store(database, payload(company_id, source_id, facts=facts if facts is not None else [
        fact(value=123456, context={"scope": "entity"})], **changes))
    database.commit()


def test_exact_provenance_repeat_and_legacy_untouched(filing_database):
    database, company_id, source_id = filing_database
    exact = Decimal("99999999999999999999999999")
    add(database, company_id, source_id, facts=[fact(value=exact, context={"scope": "entity"})])
    first = normalize_company_shares(database, company_id)
    second = normalize_company_shares(database, company_id)
    assert first.accepted == first.reviews_inserted == 1
    assert second.reviews_inserted == second.reviews_updated == 0
    review = database.scalar(select(NormalizedShareFact))
    raw = database.get(RawFinancialFact, review.raw_fact_id)
    assert review.shares_outstanding == exact
    assert review.observation_date == raw.period_end
    assert review.known_date == date(2021, 2, 2)
    assert raw.normalization_status == "pending"
    assert count(database, SharesOutstandingObservation) == 0


def test_new_conflict_invalidates_previous_candidate(filing_database):
    database, company_id, source_id = filing_database
    add(database, company_id, source_id)
    assert normalize_company_shares(database, company_id).accepted == 1
    add(database, company_id, source_id, facts=[fact(value=999, context={"scope": "entity", "frame": "CY2020Q4I"})])
    result = normalize_company_shares(database, company_id)
    assert result.conflicts == 2 and result.accepted == 0
    assert result.reviews_inserted == result.reviews_updated == 1
    assert {row.status for row in database.scalars(select(NormalizedShareFact))} == {"conflict"}


def test_equal_values_across_tags_are_not_conflicts(filing_database):
    database, company_id, source_id = filing_database
    add(database, company_id, source_id, facts=[fact(value=100, context={"scope": "entity"}),
        fact(value=100, taxonomy="us-gaap", tag="CommonStockSharesOutstanding", context={"scope": "entity"})])
    result = normalize_company_shares(database, company_id)
    assert result.accepted == 2 and result.conflicts == 0


def test_amendment_preserves_both_versions_and_dates(filing_database):
    database, company_id, source_id = filing_database
    add(database, company_id, source_id)
    add(database, company_id, source_id, accession_number="0000320193-21-000002",
        form_type="10-K/A", filed_date=date(2021, 3, 1),
        facts=[fact(value=999, context={"scope": "entity"})])
    result = normalize_company_shares(database, company_id)
    assert result.accepted == 2 and result.conflicts == 0
    assert {row.known_date for row in database.scalars(select(NormalizedShareFact))} == {date(2021, 2, 2), date(2021, 3, 2)}


def test_unknown_publication_is_excluded(filing_database):
    database, company_id, source_id = filing_database
    add(database, company_id, source_id, filed_date=None, accepted_at=None)
    result = normalize_company_shares(database, company_id)
    assert result.excluded == 1
    row = database.scalar(select(NormalizedShareFact))
    assert row.reason == "publication_date_unknown" and row.known_date is None


def test_other_concepts_are_left_for_later_normalizers(filing_database):
    database, company_id, source_id = filing_database
    add(database, company_id, source_id, facts=[fact(value=100, taxonomy="us-gaap",
        tag="WeightedAverageNumberOfDilutedSharesOutstanding", context={"scope": "entity"})])
    assert normalize_company_shares(database, company_id).facts_reviewed == 0
    assert count(database, NormalizedShareFact) == 0


def test_routes_review_dates_and_company_isolation(filing_database):
    database, company_id, source_id = filing_database
    add(database, company_id, source_id)
    from fastapi import HTTPException
    from app.filings.routes import normalize_shares, list_normalized_shares
    from app.filings.share_normalization import NormalizedShareRead
    assert normalize_shares(company_id, database).accepted == 1
    assert list_normalized_shares(company_id, database, as_of=date(2021, 2, 1), limit=100, offset=0) == []
    rows = list_normalized_shares(company_id, database, as_of=date(2021, 2, 2), limit=100, offset=0)
    assert len(rows) == 1
    result = NormalizedShareRead.model_validate(rows[0]).model_dump(mode="json")
    assert Decimal(result["shares_outstanding"]) == 123456 and result["raw_fact_id"]
    for function in (normalize_shares, list_normalized_shares):
        with pytest.raises(HTTPException) as error:
            function(uuid.uuid4(), database)
        assert error.value.status_code == 404


def test_failure_rolls_back_all_reviews(filing_database, monkeypatch):
    database, company_id, source_id = filing_database
    add(database, company_id, source_id)
    monkeypatch.setattr(database, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failed")))
    with pytest.raises(RuntimeError, match="commit failed"):
        normalize_company_shares(database, company_id)
    assert count(database, NormalizedShareFact) == 0


@pytest.mark.parametrize("changes,reason", [
    ({"unit": "USD"}, "unsupported_unit"),
    ({"period_start": date(2020, 1, 1)}, "duration_fact_not_instant_shares"),
    ({"context_json": '{}'}, "entity_scope_not_confirmed"),
    ({"context_json": '{"scope":"entity","axis":"ClassA"}'}, "entity_scope_not_confirmed"),
    ({"context_json": '[]'}, "entity_scope_not_confirmed"),
    ({"context_json": 'bad'}, "invalid_context"),
    ({"value_text": 'NaN'}, "share_count_must_be_positive_whole_and_fit_storage"),
    ({"value_text": '0'}, "share_count_must_be_positive_whole_and_fit_storage"),
    ({"value_text": '-1'}, "share_count_must_be_positive_whole_and_fit_storage"),
    ({"value_text": '1.5'}, "share_count_must_be_positive_whole_and_fit_storage"),
    ({"value_text": '1e26'}, "share_count_must_be_positive_whole_and_fit_storage"),
    ({"value_text": 'bad'}, "invalid_share_count"),
])
def test_invalid_candidates_are_explicitly_excluded(changes, reason):
    values = dict(unit="shares", period_start=None, period_end=date(2020, 12, 31),
                  value_text="100", context_json='{"scope":"entity"}')
    values.update(changes)
    filing = SimpleNamespace(form_type="10-K", filed_date=date(2021, 2, 1), accepted_at=None)
    status, actual, value, known = _review(SimpleNamespace(**values), filing)
    assert status == "excluded" and actual == reason and value is known is None


def test_acceptance_utc_date_controls_daily_availability():
    raw = SimpleNamespace(unit="shares", period_start=None, period_end=date(2020, 12, 31),
                          value_text="100", context_json='{"scope":"entity"}')
    filing = SimpleNamespace(form_type="10-K", filed_date=date(2021, 2, 1),
                             accepted_at=datetime.fromisoformat("2021-02-01T23:30:00-05:00"))
    assert _review(raw, filing)[3] == date(2021, 2, 3)
