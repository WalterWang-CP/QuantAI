import hashlib
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic import command
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models.filings import CompanyFiling, FilingSourceArtifact, RawFinancialFact
from app.db.models.identity import Company
from app.db.models.market_data import DataSource
from app.filings.schemas import FilingCreate, RawFactCreate
from app.filings.service import FilingConflictError, get_raw_facts_available_as_of, store_filing
from test_database_migrations import postgres_migrations


@pytest.fixture(params=["sqlite", "postgresql"])
def filing_database(request):
    if request.param == "postgresql":
        connection, config = request.getfixturevalue("postgres_migrations")
        command.upgrade(config, "head")
        database = Session(bind=connection, autoflush=False, join_transaction_mode="create_savepoint")
        engine = None
    else:
        engine = sa.create_engine("sqlite+pysqlite:///:memory:")
        @sa.event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(engine)
        database = Session(bind=engine, autoflush=False)
    company = Company(legal_name="Filing Test Company", is_active=True)
    source = DataSource(provider_name="sec", dataset_name="COMPANY_FACTS")
    database.add_all([company, source])
    database.commit()
    company_id, source_id = company.id, source.id
    try:
        yield database, company_id, source_id
    finally:
        database.close()
        if engine is not None:
            engine.dispose()


def fact(**changes):
    values = dict(taxonomy="dei", tag="EntityCommonStockSharesOutstanding", unit="shares",
                  period_end=date(2020, 12, 31), value=Decimal("123456789.12345678901234567890"))
    values.update(changes)
    return RawFactCreate(**values)


def payload(company_id, source_id, **changes):
    values = dict(company_id=company_id, source_id=source_id, cik="320193",
                  accession_number="0000320193-21-000001", form_type="10-K",
                  report_period=date(2020, 12, 31), filed_date=date(2021, 2, 1),
                  facts=[fact()])
    values.update(changes)
    return FilingCreate(**values)


def store(database, value, body=b'{"original":true}', **kwargs):
    return store_filing(database, value, raw_body=body,
                        source_url="https://data.sec.gov/test.json", **kwargs)


def count(database, model):
    return database.scalar(sa.select(sa.func.count()).select_from(model))


def test_archive_preserves_exact_bytes_hash_and_decimal(filing_database):
    database, company_id, source_id = filing_database
    body = b'{"original": true, "spacing":  2}\n'
    result = store(database, payload(company_id, source_id), body)
    database.commit()
    archive = database.get(FilingSourceArtifact, result.artifact_id)
    assert archive.body == body
    assert archive.sha256 == hashlib.sha256(body).hexdigest()
    assert archive.byte_count == len(body)
    row = database.scalar(sa.select(RawFinancialFact))
    assert Decimal(row.value_text) == fact().value
    assert row.artifact_id == archive.id
    assert row.normalization_status == "pending"
    assert database.get(CompanyFiling, result.filing_id).cik == "0000320193"


def test_repeated_import_is_idempotent(filing_database):
    database, company_id, source_id = filing_database
    value = payload(company_id, source_id)
    first = store(database, value)
    database.commit()
    second = store(database, value)
    database.commit()
    assert first.filing_id == second.filing_id
    assert first.artifact_id == second.artifact_id
    assert first.facts_inserted == 1
    assert second.facts_inserted == 0 and second.facts_existing == 1
    assert not second.filing_created and not second.artifact_created
    assert count(database, RawFinancialFact) == 1


def test_amended_filing_keeps_original_and_later_version(filing_database):
    database, company_id, source_id = filing_database
    first = store(database, payload(company_id, source_id))
    amendment = store(database, payload(company_id, source_id,
        accession_number="0000320193-21-000002", form_type="10-K/A",
        filed_date=date(2021, 3, 1), facts=[fact(value=999)]), b'{"amended":true}')
    database.commit()
    assert first.filing_id != amendment.filing_id
    assert count(database, CompanyFiling) == 2
    early = get_raw_facts_available_as_of(database, company_id, datetime(2021, 2, 2, tzinfo=timezone.utc))
    assert [row.filing_id for row in early] == [first.filing_id]
    later = get_raw_facts_available_as_of(database, company_id, datetime(2021, 3, 2, tzinfo=timezone.utc))
    assert len(later) == 2


def test_date_only_filing_waits_until_next_day(filing_database):
    database, company_id, source_id = filing_database
    store(database, payload(company_id, source_id))
    database.commit()
    assert not get_raw_facts_available_as_of(database, company_id,
        datetime(2021, 2, 1, 23, 59, tzinfo=timezone.utc))
    assert len(get_raw_facts_available_as_of(database, company_id,
        datetime(2021, 2, 2, tzinfo=timezone.utc))) == 1


def test_exact_acceptance_timestamp_controls_availability(filing_database):
    database, company_id, source_id = filing_database
    store(database, payload(company_id, source_id,
        accepted_at=datetime(2021, 2, 1, 20, tzinfo=timezone.utc)))
    database.commit()
    assert not get_raw_facts_available_as_of(database, company_id,
        datetime(2021, 2, 1, 19, 59, tzinfo=timezone.utc))
    assert len(get_raw_facts_available_as_of(database, company_id,
        datetime(2021, 2, 1, 20, tzinfo=timezone.utc))) == 1


def test_unknown_public_date_is_preserved_and_excluded(filing_database):
    database, company_id, source_id = filing_database
    result = store(database, payload(company_id, source_id, filed_date=None))
    database.commit()
    assert database.get(CompanyFiling, result.filing_id).filed_date is None
    assert not get_raw_facts_available_as_of(database, company_id,
        datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_missing_metadata_can_be_enriched_with_archive_link(filing_database):
    database, company_id, source_id = filing_database
    first = store(database, payload(company_id, source_id, filed_date=None))
    database.commit()
    second = store(database, payload(company_id, source_id,
        accepted_at=datetime(2021, 2, 1, 20, tzinfo=timezone.utc)), b'{"more_metadata":true}')
    database.commit()
    filing = database.get(CompanyFiling, first.filing_id)
    assert filing.first_artifact_id == first.artifact_id
    assert filing.metadata_artifact_id == second.artifact_id
    assert filing.filed_date == date(2021, 2, 1)
    # Re-read SQLite timestamps without tzinfo and import again.
    database.expire_all()
    store(database, payload(company_id, source_id,
        accepted_at=datetime(2021, 2, 1, 20, tzinfo=timezone.utc)), b'{"more_metadata":true}')
    database.commit()
    assert count(database, RawFinancialFact) == 1


def test_conflicting_metadata_rolls_back_entire_import(filing_database):
    database, company_id, source_id = filing_database
    first = store(database, payload(company_id, source_id))
    database.commit()
    with pytest.raises(FilingConflictError, match="filed_date"):
        store(database, payload(company_id, source_id, filed_date=date(2021, 2, 3)), b'{"bad":true}')
    assert count(database, FilingSourceArtifact) == 1
    assert count(database, RawFinancialFact) == 1
    assert database.get(CompanyFiling, first.filing_id).filed_date == date(2021, 2, 1)


def test_reusing_accession_for_another_company_is_rejected(filing_database):
    database, company_id, source_id = filing_database
    store(database, payload(company_id, source_id))
    other = Company(legal_name="Other Company", is_active=True)
    database.add(other)
    database.commit()
    with pytest.raises(FilingConflictError, match="company_id"):
        store(database, payload(other.id, source_id))
    assert count(database, FilingSourceArtifact) == 1


def test_context_and_conflicting_values_remain_separate(filing_database):
    database, company_id, source_id = filing_database
    result = store(database, payload(company_id, source_id, facts=[
        fact(value=100, context={"class": "A"}),
        fact(value=100, context={"class": "B"}),
        fact(value=101, context={"class": "A"}),
    ]))
    database.commit()
    assert result.facts_inserted == 3
    assert count(database, RawFinancialFact) == 3


def test_equal_decimals_and_context_order_deduplicate(filing_database):
    database, company_id, source_id = filing_database
    result = store(database, payload(company_id, source_id, facts=[
        fact(value=Decimal("1.00"), context={"b": "2", "a": "1"}),
        fact(value=Decimal("1"), context={"a": "1", "b": "2"}),
    ]))
    database.commit()
    assert result.facts_inserted == 1 and result.facts_existing == 1


def test_same_body_is_kept_separate_between_data_sources(filing_database):
    database, company_id, source_id = filing_database
    other = DataSource(provider_name="manual", dataset_name="FILING_FACTS")
    database.add(other)
    database.commit()
    first = store(database, payload(company_id, source_id))
    second = store(database, payload(company_id, other.id))
    database.commit()
    assert first.artifact_id != second.artifact_id
    assert first.filing_id != second.filing_id


def test_outer_rollback_discards_import(filing_database):
    database, company_id, source_id = filing_database
    store(database, payload(company_id, source_id))
    database.rollback()
    assert count(database, CompanyFiling) == 0
    assert count(database, FilingSourceArtifact) == 0
    assert count(database, RawFinancialFact) == 0


def test_unknown_company_or_source_is_rejected(filing_database):
    database, company_id, source_id = filing_database
    with pytest.raises(LookupError, match="Company"):
        store(database, payload(uuid.uuid4(), source_id))
    with pytest.raises(LookupError, match="source"):
        store(database, payload(company_id, uuid.uuid4()))
    assert count(database, FilingSourceArtifact) == 0


def test_empty_body_and_naive_timestamps_are_rejected(filing_database):
    database, company_id, source_id = filing_database
    with pytest.raises(ValueError, match="nonempty"):
        store(database, payload(company_id, source_id), b"")
    with pytest.raises(ValueError, match="timezone"):
        store(database, payload(company_id, source_id), fetched_at=datetime(2021, 1, 1))
    with pytest.raises(ValueError, match="timezone"):
        get_raw_facts_available_as_of(database, company_id, datetime(2021, 1, 1))


@pytest.mark.parametrize("changes", [
    {"cik": "0"}, {"cik": "not-a-cik"},
    {"accepted_at": datetime(2021, 2, 1)},
    {"report_period": date(2021, 3, 1)},
    {"accepted_at": datetime(2021, 1, 1, tzinfo=timezone.utc)},
])
def test_invalid_filing_metadata_is_rejected(changes):
    with pytest.raises(ValidationError):
        payload(uuid.uuid4(), uuid.uuid4(), **changes)


@pytest.mark.parametrize("changes", [
    {"period_start": date(2021, 1, 1)}, {"value": "NaN"}, {"value": "Infinity"},
])
def test_invalid_raw_fact_is_rejected(changes):
    with pytest.raises(ValidationError):
        fact(**changes)


def test_fact_period_after_known_filing_date_is_rejected():
    with pytest.raises(ValidationError, match="period_end"):
        payload(uuid.uuid4(), uuid.uuid4(), facts=[fact(period_end=date(2022, 1, 1))])


def test_enrichment_cannot_backdate_existing_facts(filing_database):
    database, company_id, source_id = filing_database
    first = store(database, payload(company_id, source_id,
        filed_date=None, report_period=None, facts=[fact(period_end=date(2022, 1, 1))]))
    database.commit()
    with pytest.raises(FilingConflictError, match="fact periods"):
        store(database, payload(company_id, source_id, report_period=None, facts=[]), b'{"backdated":true}')
    assert database.get(CompanyFiling, first.filing_id).filed_date is None
    assert count(database, FilingSourceArtifact) == 1
