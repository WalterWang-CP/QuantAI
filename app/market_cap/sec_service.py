"""USD-only SEC shares reconstruction, preserving earlier calculation versions."""
import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal, localcontext
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.csv_prices import CSVPriceArtifact
from app.db.models.corporate_actions import StockSplit
from app.db.models.filings import FilingSourceArtifact, RawFinancialFact, CompanyFiling
from app.db.models.identity import Company, Listing, Security
from app.db.models.market_data import DailyPriceBar, RawDataArtifact
from app.db.models.sec_market_cap import SECMarketCapSnapshot
from app.db.models.share_scope import CompanyShareScope
from app.filings.service import _insert
from app.filings.share_selection import select_security_shares, ShareSelectionConflict
from app.market_cap.price_service import find_historical_close


class SECMarketCapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    valuation_date: date
    price_source_id: uuid.UUID | None = None
    max_share_age_days: int = Field(400, ge=1, le=3660)
    max_price_age_days: int = Field(7, ge=0, le=31)
    confirm_split_coverage: Literal[True]
    split_evidence_url: HttpUrl
    split_evidence_note: str = Field(min_length=20, max_length=2000)


class SECMarketCapRead(BaseModel):
    snapshot_id: uuid.UUID
    created: bool
    listing_id: uuid.UUID
    valuation_date: date
    input_hash: str
    manifest: dict


def _decimal(value):
    result = Decimal(value)
    if not result.is_finite() or result <= 0:
        raise ShareSelectionConflict("Calculation inputs must be finite and positive")
    return result


def _text(value):
    result = format(Decimal(value), "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def snapshot_read(row, created=False):
    return SECMarketCapRead(snapshot_id=row.id, created=created, listing_id=row.listing_id,
        valuation_date=row.valuation_date, input_hash=row.input_hash, manifest=json.loads(row.manifest_json))


def reconstruct_sec_market_cap(database: Session, listing_id: uuid.UUID, payload: SECMarketCapRequest):
    try:
        listing = database.get(Listing, listing_id)
        if listing is None:
            raise LookupError("Listing does not exist")
        security = database.get(Security, listing.security_id)
        if security is None:
            raise LookupError("Security does not exist")
        # Serialize with SEC imports, normalization, and mapping writes on PostgreSQL.
        database.scalar(select(Company).where(Company.id == security.company_id).with_for_update())
        if payload.valuation_date < listing.start_date or (listing.end_date is not None and payload.valuation_date > listing.end_date):
            raise ShareSelectionConflict("Valuation date is outside the listing lifetime")
        if listing.currency_code.strip().upper() != "USD":
            raise ShareSelectionConflict("This SEC reconstruction pilot supports USD listings only; explicit FX provenance is required for other currencies")
        selected = select_security_shares(database, security.id, payload.valuation_date, payload.max_share_age_days)
        bar = find_historical_close(database, listing.id, payload.valuation_date, source_id=payload.price_source_id)
        if bar.trading_date < listing.start_date or (payload.valuation_date - bar.trading_date).days > payload.max_price_age_days:
            raise ShareSelectionConflict("Selected price is outside the listing lifetime or exceeds max_price_age_days")
        mapping = database.get(CompanyShareScope, selected.mapping_id)
        if bar.trading_date < mapping.valid_from:
            raise ShareSelectionConflict("Price date is before the evidenced security mapping period")
        start = min(selected.observation_date, bar.trading_date)
        end = max(selected.observation_date, bar.trading_date)
        splits = list(database.scalars(select(StockSplit).where(StockSplit.listing_id == listing.id,
            StockSplit.effective_date > start, StockSplit.effective_date <= end)
            .order_by(StockSplit.effective_date, StockSplit.source_id, StockSplit.id)))
        raw = database.get(RawFinancialFact, selected.raw_fact_id)
        artifact = database.get(FilingSourceArtifact, selected.artifact_id)
        filing = database.get(CompanyFiling, selected.filing_id)
        metadata_artifact = database.get(FilingSourceArtifact, filing.metadata_artifact_id)
        price_archive = database.scalar(select(RawDataArtifact).where(RawDataArtifact.ingestion_run_id == bar.last_ingestion_run_id))
        if price_archive is None:
            raise ShareSelectionConflict("Selected price lacks its source archive record; re-import prices before reconstruction")
        if price_archive.listing_id != listing.id or price_archive.source_id != bar.source_id:
            raise ShareSelectionConflict("Price archive ownership does not match the selected price")
        with localcontext() as context:
            context.prec = 80
            price = _decimal(bar.close_price)
            # Use the captured rows once: manifest and arithmetic share the same inputs.
            factors = {}
            for split in splits:
                factor = _decimal(split.split_factor)
                previous = factors.get(split.effective_date)
                if previous is not None and previous != factor:
                    raise ShareSelectionConflict("Conflicting split factors for the same effective date")
                factors[split.effective_date] = factor
            cumulative = Decimal("1")
            for factor in factors.values():
                cumulative *= factor
            shares = selected.shares_outstanding
            if selected.observation_date < bar.trading_date:
                shares *= cumulative
            elif selected.observation_date > bar.trading_date:
                shares /= cumulative
            shares = _decimal(shares)
            market_cap = _decimal(price * shares)
        manifest = {
            "calculation_rule": "sec-usd-market-cap-v1", "decimal_precision": 80,
            "company_id": str(security.company_id), "security_id": str(security.id), "listing_id": str(listing.id),
            "valuation_date": payload.valuation_date.isoformat(), "currency": "USD",
            "shares_selection": selected.model_dump(mode="json"),
            "shares_fact": {"fact_hash": raw.fact_hash, "value_text": raw.value_text,
                "artifact_sha256": artifact.sha256, "artifact_url": artifact.source_url,
                "metadata_artifact_id": str(metadata_artifact.id), "metadata_sha256": metadata_artifact.sha256},
            "mapping": {"id": str(mapping.id), "valid_from": mapping.valid_from.isoformat(),
                "valid_to": mapping.valid_to.isoformat(), "known_date": mapping.known_date.isoformat(),
                "evidence_url": mapping.evidence_url, "evidence_note": mapping.evidence_note},
            "price": {"bar_id": str(bar.id), "source_id": str(bar.source_id), "basis": "raw_close",
                "trading_date": bar.trading_date.isoformat(), "close": _text(price),
                "ingestion_run_id": str(bar.last_ingestion_run_id), "artifact_id": str(price_archive.id),
                "artifact_sha256": price_archive.sha256, "artifact_path": price_archive.storage_path},
            "splits": [{"id": str(split.id), "source_id": str(split.source_id),
                "effective_date": split.effective_date.isoformat(), "factor": _text(split.split_factor),
                "ingestion_run_id": str(split.last_ingestion_run_id)} for split in splits],
            "split_coverage": {"asserted_by_operator": True, "independently_verified": False,
                "start_date": start.isoformat(), "end_date": end.isoformat(),
                "evidence_url": str(payload.split_evidence_url), "evidence_note": payload.split_evidence_note},
            "fx": {"from_currency": "USD", "to_currency": "USD", "rate": "1", "rate_record_id": None},
            "limits": {"max_share_age_days": payload.max_share_age_days, "max_price_age_days": payload.max_price_age_days},
            "result": {"shares_on_price_date": _text(shares), "local_market_cap": _text(market_cap), "market_cap_usd": _text(market_cap)},
        }
        if price_archive.storage_path.startswith("database:csv_price_artifacts/"):
            csv_archive = database.scalar(select(CSVPriceArtifact).where(CSVPriceArtifact.ingestion_run_id == bar.last_ingestion_run_id))
            if csv_archive is None or csv_archive.sha256 != price_archive.sha256 or csv_archive.source_id != bar.source_id or csv_archive.listing_id != listing.id or hashlib.sha256(csv_archive.body).hexdigest() != csv_archive.sha256:
                raise ShareSelectionConflict("CSV price archive is missing or mismatched")
            manifest["price"]["csv_artifact_id"] = str(csv_archive.id)
            manifest["price"]["csv_declaration"] = json.loads(csv_archive.declaration_json)
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        snapshot_id = _insert(database, SECMarketCapSnapshot.__table__, dict(id=uuid.uuid4(),
            company_id=security.company_id, listing_id=listing.id, valuation_date=payload.valuation_date,
            input_hash=fingerprint, manifest_json=encoded), ["listing_id", "valuation_date", "input_hash"])
        created = snapshot_id is not None
        row = database.scalar(select(SECMarketCapSnapshot).where(SECMarketCapSnapshot.listing_id == listing.id,
            SECMarketCapSnapshot.valuation_date == payload.valuation_date, SECMarketCapSnapshot.input_hash == fingerprint))
        database.commit()
        return snapshot_read(row, created)
    except Exception:
        database.rollback()
        raise
