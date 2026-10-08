"""Company-scoped source archives, filings, and unnormalized financial facts."""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, Integer, LargeBinary,
    String, Text, UniqueConstraint, Uuid, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class FilingSourceArtifact(Base):
    __tablename__ = "filing_source_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id"), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    body: Mapped[bytes] = mapped_column(LargeBinary)
    byte_count: Mapped[int] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("company_id", "source_id", "sha256", name="uq_filing_artifact_content"),
        CheckConstraint("byte_count > 0", name="ck_filing_artifact_nonempty"),
    )


class CompanyFiling(Base):
    __tablename__ = "company_filings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id"), index=True)
    first_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("filing_source_artifacts.id"))
    metadata_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("filing_source_artifacts.id"))
    cik: Mapped[str] = mapped_column(String(10), index=True)
    accession_number: Mapped[str] = mapped_column(String(80))
    form_type: Mapped[str] = mapped_column(String(30))
    report_period: Mapped[date | None] = mapped_column(Date)
    filed_date: Mapped[date | None] = mapped_column(Date, index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    document_url: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("source_id", "accession_number", name="uq_company_filing_accession"),
        CheckConstraint("report_period IS NULL OR filed_date IS NULL OR report_period <= filed_date",
                        name="ck_filing_report_before_filed"),
    )


class RawFinancialFact(Base):
    __tablename__ = "raw_financial_facts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    filing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company_filings.id"), index=True)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("filing_source_artifacts.id"))
    taxonomy: Mapped[str] = mapped_column(String(100))
    tag: Mapped[str] = mapped_column(String(255))
    unit: Mapped[str] = mapped_column(String(100))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    # Exact decimal text avoids SQL numeric scale rounding. Original bytes remain archived.
    value_text: Mapped[str] = mapped_column(Text)
    context_json: Mapped[str] = mapped_column(Text)
    fact_hash: Mapped[str] = mapped_column(String(64))
    normalization_status: Mapped[str] = mapped_column(String(20), server_default="pending")
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("filing_id", "fact_hash", name="uq_raw_fact_filing_hash"),
        CheckConstraint("period_start IS NULL OR period_start <= period_end",
                        name="ck_raw_fact_period"),
        CheckConstraint("normalization_status IN ('pending', 'accepted', 'excluded', 'conflict')",
                        name="ck_raw_fact_normalization_status"),
    )
