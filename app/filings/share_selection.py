"""Evidence-backed company-wide shares selection; no market-cap writes."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.filings import CompanyFiling, RawFinancialFact
from app.db.models.identity import Company, Security
from app.db.models.market_data import DataSource
from app.db.models.share_normalization import NormalizedShareFact
from app.db.models.share_scope import CompanyShareScope
from app.filings.share_normalization import RULE_VERSION, TAGS, _review


class ShareSelectionConflict(ValueError):
    pass


class ShareScopeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    security_id: uuid.UUID
    valid_from: date
    valid_to: date
    known_date: date
    evidence_url: HttpUrl
    evidence_note: str = Field(min_length=20, max_length=2000)
    confirm_single_common_class: Literal[True]

    @model_validator(mode="after")
    def dates(self):
        if self.valid_to < self.valid_from:
            raise ValueError("valid_to must be on or after valid_from")
        if self.known_date < self.valid_from:
            raise ValueError("known_date must be on or after valid_from")
        return self


class ShareScopeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    company_id: uuid.UUID
    security_id: uuid.UUID
    valid_from: date
    valid_to: date
    known_date: date
    evidence_url: str
    evidence_note: str
    scope_type: str


class SelectedShareRead(BaseModel):
    security_id: uuid.UUID
    company_id: uuid.UUID
    valuation_date: date
    observation_date: date
    known_date: date
    shares_outstanding: Decimal
    mapping_id: uuid.UUID
    normalized_fact_id: uuid.UUID
    raw_fact_id: uuid.UUID
    filing_id: uuid.UUID
    artifact_id: uuid.UUID
    accession_number: str
    equivalent_raw_fact_ids: list[uuid.UUID]
    selection_rule: str = "sec-shares-selection-v1"


def _active(security, start, end):
    return (security.start_date is None or security.start_date <= start) and (security.end_date is None or security.end_date >= end)


def _validate_security(database, company_id, security_id, start, end):
    security = database.get(Security, security_id)
    if security is None:
        raise LookupError("Security does not exist")
    if security.company_id != company_id:
        raise ShareSelectionConflict("Security belongs to a different company")
    if security.security_type != "common_stock":
        raise ShareSelectionConflict("This pilot supports common_stock only; ADRs and other security types need separate rules")
    if not _active(security, start, end):
        raise ShareSelectionConflict("Mapping period is outside the security lifetime")
    # The assertion is still required: incomplete identity data cannot prove one class.
    other_securities = database.scalars(select(Security).where(Security.company_id == company_id, Security.id != security_id))
    for other in other_securities:
        if (other.start_date is None or other.start_date <= end) and (other.end_date is None or other.end_date >= start):
            raise ShareSelectionConflict("Other overlapping securities exist; company-wide shares cannot be mapped automatically")
    return security


def create_share_scope(database: Session, company_id: uuid.UUID, payload: ShareScopeCreate):
    try:
        company = database.scalar(select(Company).where(Company.id == company_id).with_for_update())
        if company is None:
            raise LookupError("Company does not exist")
        _validate_security(database, company_id, payload.security_id, payload.valid_from, payload.valid_to)
        values = dict(company_id=company_id, security_id=payload.security_id, valid_from=payload.valid_from,
            valid_to=payload.valid_to, known_date=payload.known_date,
            evidence_url=str(payload.evidence_url), evidence_note=payload.evidence_note)
        for row in database.scalars(select(CompanyShareScope).where(CompanyShareScope.company_id == company_id)):
            if all(getattr(row, key) == value for key, value in values.items()):
                database.commit()
                return row
            if row.valid_from <= payload.valid_to and row.valid_to >= payload.valid_from:
                raise ShareSelectionConflict("An overlapping shares mapping already exists; existing evidence is never overwritten")
        row = CompanyShareScope(**values)
        database.add(row)
        database.commit()
        database.refresh(row)
        return row
    except Exception:
        database.rollback()
        raise


def _publication_key(filing):
    accepted = filing.accepted_at
    if accepted is None:
        return None
    if accepted.tzinfo is None:
        accepted = accepted.replace(tzinfo=timezone.utc)
    return accepted.astimezone(timezone.utc)


def select_security_shares(database: Session, security_id: uuid.UUID, valuation_date: date,
                           max_age_days: int = 400) -> SelectedShareRead:
    """Read a candidate on its observation split basis, without copying or modifying data.

    Reviews provide provenance inventory. Decisions are recomputed from source facts for
    the requested daily cutoff, so a future publication cannot invalidate an earlier value.
    """
    if not 1 <= max_age_days <= 3660:
        raise ValueError("max_age_days must be between 1 and 3660")
    security = database.get(Security, security_id)
    if security is None:
        raise LookupError("Security does not exist")
    company_id = security.company_id
    if not _active(security, valuation_date, valuation_date):
        raise ShareSelectionConflict("Valuation date is outside the security lifetime")
    mappings = list(database.scalars(select(CompanyShareScope).where(
        CompanyShareScope.company_id == company_id, CompanyShareScope.security_id == security_id,
        CompanyShareScope.valid_from <= valuation_date, CompanyShareScope.valid_to >= valuation_date,
        CompanyShareScope.known_date <= valuation_date)))
    if not mappings:
        raise LookupError("No evidence-backed shares mapping is available for this valuation date")
    if len(mappings) != 1:
        raise ShareSelectionConflict("Ambiguous shares mapping")
    mapping = mappings[0]
    _validate_security(database, company_id, security_id, mapping.valid_from, valuation_date)
    reviews = {row.raw_fact_id: row for row in database.scalars(select(NormalizedShareFact)
        .where(NormalizedShareFact.company_id == company_id))}
    rows = database.execute(select(RawFinancialFact, CompanyFiling).join(CompanyFiling,
        RawFinancialFact.filing_id == CompanyFiling.id).join(DataSource, CompanyFiling.source_id == DataSource.id)
        .where(CompanyFiling.company_id == company_id, DataSource.provider_name == "sec")).all()
    eligible = []
    for raw, filing in rows:
        if (raw.taxonomy, raw.tag) not in TAGS:
            continue
        status, _, value, known = _review(raw, filing)
        if status != "accepted" or known > valuation_date or raw.period_end > valuation_date:
            continue
        if raw.period_end < mapping.valid_from:
            continue
        review = reviews.get(raw.id)
        if review is None or review.rule_version != RULE_VERSION:
            raise ShareSelectionConflict("Eligible raw facts are not reviewed under the current rule; run normalize-shares again")
        eligible.append((raw, filing, review, value, known))
    if not eligible:
        raise LookupError("No eligible SEC shares fact is available for this valuation date and mapping period")
    latest_period = max(item[0].period_end for item in eligible)
    if (valuation_date - latest_period).days > max_age_days:
        raise ShareSelectionConflict("Most recent available shares observation exceeds max_age_days")
    period_rows = [item for item in eligible if item[0].period_end == latest_period]
    # Detect conflicts within each filing before deciding between filing revisions.
    filing_values = {}
    for item in period_rows:
        filing_values.setdefault(item[1].id, set()).add(item[3])
    latest_known = max(item[4] for item in period_rows)
    finalists = [item for item in period_rows if item[4] == latest_known]
    # Same-day revision order is usable only when every contender has an exact acceptance time.
    keys = [_publication_key(item[1]) for item in finalists]
    if all(key is not None for key in keys):
        latest_publication = max(keys)
        finalists = [item for item, key in zip(finalists, keys) if key == latest_publication]
    if any(len(filing_values[item[1].id]) > 1 for item in finalists) or len({item[3] for item in finalists}) > 1:
        raise ShareSelectionConflict("Latest available filing revision has conflicting shares values; no older fallback is selected")
    # Deterministic tie-breaking applies only to equal counts, never to conflicting values.
    finalists.sort(key=lambda item: (item[1].accession_number, str(item[0].id)))
    raw, filing, review, value, known = finalists[0]
    return SelectedShareRead(security_id=security_id, company_id=company_id, valuation_date=valuation_date,
        observation_date=raw.period_end, known_date=known, shares_outstanding=value,
        mapping_id=mapping.id, normalized_fact_id=review.id, raw_fact_id=raw.id,
        filing_id=filing.id, artifact_id=raw.artifact_id, accession_number=filing.accession_number,
        equivalent_raw_fact_ids=[item[0].id for item in finalists])
