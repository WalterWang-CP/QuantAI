"""Conservative SEC shares review. Does not populate legacy market-cap inputs."""
import json
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.filings import CompanyFiling, RawFinancialFact
from app.db.models.identity import Company
from app.db.models.market_data import DataSource
from app.db.models.share_normalization import NormalizedShareFact

RULE_VERSION = "sec-shares-v1"
TAGS = {("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding")}
FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A"}


class ShareNormalizationResult(BaseModel):
    company_id: uuid.UUID
    rule_version: str = RULE_VERSION
    facts_reviewed: int
    reviews_inserted: int
    reviews_updated: int
    accepted: int
    excluded: int
    conflicts: int


class NormalizedShareRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    raw_fact_id: uuid.UUID
    company_id: uuid.UUID
    observation_date: date
    known_date: date | None
    shares_outstanding: Decimal | None
    status: str
    reason: str
    rule_version: str


def _review(raw, filing):
    """Return a decision; daily inputs become usable the following UTC day."""
    if raw.unit != "shares":
        return "excluded", "unsupported_unit", None, None
    if raw.period_start is not None:
        return "excluded", "duration_fact_not_instant_shares", None, None
    if filing.form_type not in FORMS:
        return "excluded", "unsupported_form", None, None
    try:
        context = json.loads(raw.context_json)
    except (ValueError, TypeError):
        return "excluded", "invalid_context", None, None
    if not isinstance(context, dict) or context.get("scope") != "entity" or set(context) - {"scope", "fy", "fp", "frame"}:
        return "excluded", "entity_scope_not_confirmed", None, None
    try:
        value = Decimal(raw.value_text)
    except (InvalidOperation, TypeError):
        return "excluded", "invalid_share_count", None, None
    if not value.is_finite() or value <= 0 or value != value.to_integral_value() or value >= Decimal("1e26"):
        return "excluded", "share_count_must_be_positive_whole_and_fit_storage", None, None
    publication = filing.filed_date
    if filing.accepted_at is not None:
        accepted = filing.accepted_at
        if accepted.tzinfo is None:  # SQLite drops timezone information on stored UTC times.
            accepted = accepted.replace(tzinfo=timezone.utc)
        accepted_date = accepted.astimezone(timezone.utc).date()
        publication = max(publication, accepted_date) if publication else accepted_date
    if publication is None:
        return "excluded", "publication_date_unknown", None, None
    if publication < raw.period_end or publication == date.max:
        return "excluded", "invalid_publication_date", None, None
    return "accepted", "company_wide_instant_shares", value, publication + timedelta(days=1)


def normalize_company_shares(database: Session, company_id: uuid.UUID) -> ShareNormalizationResult:
    """Re-review all SEC share facts, including previously accepted conflicting groups.

    The company lock serializes this with SEC imports. Original facts/archives remain unchanged.
    """
    try:
        company = database.scalar(select(Company).where(Company.id == company_id).with_for_update())
        if company is None:
            raise LookupError("Company does not exist")
        rows = database.execute(select(RawFinancialFact, CompanyFiling)
            .join(CompanyFiling, RawFinancialFact.filing_id == CompanyFiling.id)
            .join(DataSource, CompanyFiling.source_id == DataSource.id)
            .where(CompanyFiling.company_id == company_id, DataSource.provider_name == "sec")
            .order_by(CompanyFiling.id, RawFinancialFact.id)).all()
        rows = [(raw, filing) for raw, filing in rows if (raw.taxonomy, raw.tag) in TAGS]
        decisions = {raw.id: _review(raw, filing) for raw, filing in rows}
        groups = defaultdict(list)
        for raw, filing in rows:
            if decisions[raw.id][0] == "accepted":
                groups[(filing.id, raw.period_end)].append(raw.id)
        for ids in groups.values():
            if len({decisions[raw_id][2] for raw_id in ids}) > 1:
                for raw_id in ids:
                    _, _, value, known = decisions[raw_id]
                    decisions[raw_id] = ("conflict", "different_values_in_same_filing_and_period", value, known)
        existing = {row.raw_fact_id: row for row in database.scalars(
            select(NormalizedShareFact).where(NormalizedShareFact.company_id == company_id))}
        inserted = updated = 0
        counts = {"accepted": 0, "excluded": 0, "conflict": 0}
        now = datetime.now(timezone.utc)
        for raw, _ in rows:
            status, reason, value, known = decisions[raw.id]
            counts[status] += 1
            values = dict(observation_date=raw.period_end, known_date=known,
                          shares_text=format(value, ".0f") if value is not None else None, status=status, reason=reason, rule_version=RULE_VERSION)
            review = existing.get(raw.id)
            if review is None:
                database.add(NormalizedShareFact(raw_fact_id=raw.id, company_id=company_id, **values))
                inserted += 1
            elif any(getattr(review, key) != value for key, value in values.items()):
                for key, value in values.items():
                    setattr(review, key, value)
                review.reviewed_at = now
                updated += 1
        database.commit()
        return ShareNormalizationResult(company_id=company_id, facts_reviewed=len(rows),
            reviews_inserted=inserted, reviews_updated=updated, accepted=counts["accepted"],
            excluded=counts["excluded"], conflicts=counts["conflict"])
    except Exception:
        database.rollback()
        raise
