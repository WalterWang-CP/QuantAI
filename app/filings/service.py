"""Archive filing inputs atomically; callers own the outer transaction.

Raw facts remain unnormalized. This module does not write shares, statements,
market caps, rankings, or tracking decisions.
"""
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.db.models.filings import CompanyFiling, FilingSourceArtifact, RawFinancialFact
from app.db.models.identity import Company
from app.db.models.market_data import DataSource
from app.filings.schemas import FilingCreate, RawFactCreate


class FilingConflictError(ValueError):
    pass


@dataclass(frozen=True)
class FilingImportResult:
    filing_id: uuid.UUID
    artifact_id: uuid.UUID
    filing_created: bool
    artifact_created: bool
    facts_inserted: int
    facts_existing: int


def _utc(value: datetime) -> datetime:
    # SQLite drops tzinfo from DateTime columns; stored timestamps are UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _insert(database: Session, table, values, unique_columns):
    dialect = database.get_bind().dialect.name
    factory = {"postgresql": pg_insert, "sqlite": sqlite_insert}.get(dialect)
    if factory is None:
        raise ValueError("Filing storage supports PostgreSQL and SQLite")
    return database.scalar(factory(table).values(**values).on_conflict_do_nothing(
        index_elements=unique_columns,
    ).returning(table.c.id))


def _fact_values(fact: RawFactCreate) -> dict:
    value_text = format(fact.value, "f")
    if "." in value_text:
        value_text = value_text.rstrip("0").rstrip(".")
    if fact.value == 0:
        value_text = "0"
    return {
        "taxonomy": fact.taxonomy, "tag": fact.tag, "unit": fact.unit,
        "period_start": fact.period_start, "period_end": fact.period_end,
        "value_text": value_text,
        "context_json": json.dumps(fact.context, sort_keys=True, separators=(",", ":")),
    }


def store_filing(
    database: Session, payload: FilingCreate, *, raw_body: bytes,
    source_url: str, content_type: str | None = None, fetched_at: datetime | None = None,
) -> FilingImportResult:
    """Flush an import without committing. Amendments have their own accession.

    Repeated facts deduplicate by semantic contents, including context and value.
    Different reported values are both retained for later normalization/review.
    Known filing metadata cannot be overwritten; missing metadata may be filled.
    """
    if not isinstance(raw_body, bytes) or not raw_body:
        raise ValueError("raw_body must contain nonempty original response bytes")
    if not source_url.strip():
        raise ValueError("source_url must not be blank")
    if content_type is not None and len(content_type) > 100:
        raise ValueError("content_type cannot exceed 100 characters")
    fetched_at = fetched_at or datetime.now(timezone.utc)
    if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
        raise ValueError("fetched_at must include a timezone")
    fetched_at = _utc(fetched_at)
    if database.get(Company, payload.company_id) is None:
        raise LookupError("Company does not exist")
    if database.get(DataSource, payload.source_id) is None:
        raise LookupError("Data source does not exist")

    # SQLite legacy transaction mode does not BEGIN for SELECT statements.
    # Ensure releasing the savepoint cannot accidentally commit the outer import.
    connection = database.connection()
    if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN")

    with database.begin_nested():
        digest = hashlib.sha256(raw_body).hexdigest()
        archive_id = _insert(database, FilingSourceArtifact.__table__, {
            "id": uuid.uuid4(), "company_id": payload.company_id, "source_id": payload.source_id,
            "source_url": source_url, "content_type": content_type, "sha256": digest,
            "body": raw_body, "byte_count": len(raw_body), "fetched_at": fetched_at,
        }, ["company_id", "source_id", "sha256"])
        archive_created = archive_id is not None
        if archive_id is None:
            archive_id = database.scalar(select(FilingSourceArtifact.id).where(
                FilingSourceArtifact.company_id == payload.company_id,
                FilingSourceArtifact.source_id == payload.source_id,
                FilingSourceArtifact.sha256 == digest,
            ))
        metadata = {name: getattr(payload, name) for name in (
            "company_id", "source_id", "cik", "accession_number", "form_type",
            "report_period", "filed_date", "accepted_at", "document_url",
        )}
        filing_id = _insert(database, CompanyFiling.__table__, {
            "id": uuid.uuid4(), "first_artifact_id": archive_id,
            "metadata_artifact_id": archive_id, **metadata,
        }, ["source_id", "accession_number"])
        filing_created = filing_id is not None
        filing = database.scalar(select(CompanyFiling).where(
            CompanyFiling.source_id == payload.source_id,
            CompanyFiling.accession_number == payload.accession_number,
        ).with_for_update().execution_options(populate_existing=True))
        for name, incoming in metadata.items():
            existing = getattr(filing, name)
            comparable = _utc(existing) if isinstance(existing, datetime) else existing
            if existing is not None and incoming is not None and comparable != incoming:
                raise FilingConflictError(f"Existing filing has conflicting {name}; no import changes saved")
            if existing is None and incoming is not None:
                setattr(filing, name, incoming)
                filing.metadata_artifact_id = archive_id
        # Validate the combined record, including metadata learned on separate imports.
        combined = {name: getattr(filing, name) for name in metadata}
        if combined["accepted_at"] is not None:
            combined["accepted_at"] = _utc(combined["accepted_at"])
        validated = FilingCreate(**combined, facts=payload.facts)
        availability_date = validated.filed_date or (
            validated.accepted_at.date() if validated.accepted_at else None
        )
        latest_period = database.scalar(select(func.max(RawFinancialFact.period_end)).where(
            RawFinancialFact.filing_id == filing.id,
        ))
        if availability_date and latest_period and latest_period > availability_date:
            raise FilingConflictError("Existing fact periods are later than filing availability")
        database.flush()
        inserted = 0
        for fact in payload.facts:
            values = _fact_values(fact)
            digest = hashlib.sha256(json.dumps(
                values, sort_keys=True, separators=(",", ":"), default=str,
            ).encode("utf-8")).hexdigest()
            fact_id = _insert(database, RawFinancialFact.__table__, {
                "id": uuid.uuid4(), "filing_id": filing.id, "artifact_id": archive_id,
                "fact_hash": digest, **values,
            }, ["filing_id", "fact_hash"])
            inserted += fact_id is not None
        return FilingImportResult(
            filing.id, archive_id, filing_created, archive_created,
            inserted, len(payload.facts) - inserted,
        )


def get_raw_facts_available_as_of(
    database: Session, company_id: uuid.UUID, cutoff: datetime,
) -> list[RawFinancialFact]:
    """Public-filing availability filter, not a normalized/restatement selection.

    Exact acceptance timestamps are used when present. With a filing date only,
    conservatively wait until the next UTC calendar day. Unknown dates are excluded.
    This reconstructs public availability; it is not a local ingestion-time replay.
    """
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("cutoff must include a timezone")
    cutoff = _utc(cutoff)
    return list(database.scalars(select(RawFinancialFact).join(
        CompanyFiling, RawFinancialFact.filing_id == CompanyFiling.id,
    ).where(
        CompanyFiling.company_id == company_id,
        or_(CompanyFiling.accepted_at <= cutoff, and_(
            CompanyFiling.accepted_at.is_(None), CompanyFiling.filed_date < cutoff.date(),
        )),
    ).order_by(RawFinancialFact.period_end, RawFinancialFact.fact_hash, RawFinancialFact.id)))
