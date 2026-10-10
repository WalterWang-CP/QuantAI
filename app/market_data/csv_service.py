"""Validated raw-price CSV import, using exact text archives and isolated sources."""
import csv
import hashlib
import io
import json
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.csv_prices import CSVPriceArtifact
from app.db.models.identity import Company, Listing, Security
from app.db.models.market_data import DailyPriceBar, DataSource, IngestionRun, RawDataArtifact
from app.filings.service import _insert

MAX_BYTES = 2_000_000
MAX_ROWS = 20_000
COLUMNS = {"date", "open", "high", "low", "close", "volume"}


class CSVPriceConflict(ValueError):
    pass


class CSVPriceImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    csv_text: str = Field(min_length=1, max_length=MAX_BYTES)
    source_name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,69}$")
    source_url: HttpUrl
    source_note: str = Field(min_length=20, max_length=2000)
    symbol: str = Field(min_length=1, max_length=32)
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    confirm_unadjusted_prices: Literal[True]


class CSVPriceImportResult(BaseModel):
    ingestion_run_id: uuid.UUID
    source_id: uuid.UUID
    csv_artifact_id: uuid.UUID
    raw_artifact_id: uuid.UUID
    created: bool
    rows_received: int
    rows_inserted: int
    rows_updated: int
    first_date: date
    last_date: date
    sha256: str


def _price(text, line):
    try:
        value = Decimal(text.strip())
        with localcontext() as context:
            context.prec = 60
            valid = value.is_finite() and 0 < value < Decimal("1e16") and value == value.quantize(Decimal("0.00000001"))
        if not valid:
            raise ValueError
    except (InvalidOperation, ValueError, AttributeError):
        raise ValueError(f"CSV row {line}: prices must be positive, finite, fit 16 integer digits and have at most 8 decimal places") from None
    return value


def parse_raw_price_csv(text: str):
    body = text.encode("utf-8")
    if len(body) > MAX_BYTES:
        raise ValueError("CSV exceeds the 2 MB limit")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff"), newline=""), strict=True)
    try:
        header = reader.fieldnames
        if header is None or len(header) != 6:
            raise ValueError("CSV must have exactly date,open,high,low,close,volume columns")
        names = [name.strip().lower() for name in header]
        if len(set(names)) != 6 or set(names) != COLUMNS:
            raise ValueError("CSV headers must be date,open,high,low,close,volume; adjusted prices are not accepted")
        rows = []
        seen = set()
        for line, original in enumerate(reader, 2):
            if len(rows) >= MAX_ROWS:
                raise ValueError("CSV exceeds the 20000 row limit")
            if None in original or any(value is None for value in original.values()):
                raise ValueError(f"CSV row {line}: wrong number of fields")
            row = {name: original[key].strip() for key, name in zip(header, names)}
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["date"]):
                raise ValueError(f"CSV row {line}: date must use YYYY-MM-DD")
            trading = date.fromisoformat(row["date"])
            if trading > datetime.now(timezone.utc).date():
                raise ValueError(f"CSV row {line}: future trading dates are not accepted")
            if trading in seen:
                raise ValueError(f"CSV row {line}: duplicate trading date")
            seen.add(trading)
            prices = {key + "_price": _price(row[key], line) for key in ("open", "high", "low", "close")}
            if prices["low_price"] > min(prices["open_price"], prices["close_price"]) or prices["high_price"] < max(prices["open_price"], prices["close_price"]) or prices["low_price"] > prices["high_price"]:
                raise ValueError(f"CSV row {line}: OHLC prices are inconsistent")
            if not re.fullmatch(r"[0-9]+", row["volume"]) or int(row["volume"]) > 2**63 - 1:
                raise ValueError(f"CSV row {line}: volume must be a nonnegative 64-bit integer")
            rows.append(dict(trading_date=trading, volume=int(row["volume"]), **prices))
    except csv.Error as error:
        raise ValueError(f"Malformed CSV: {error}") from error
    if not rows:
        raise ValueError("CSV contains no price rows")
    return body, sorted(rows, key=lambda row: row["trading_date"])


def import_raw_price_csv(database: Session, listing_id: uuid.UUID, payload: CSVPriceImportRequest):
    # Parse before any database mutation; one invalid row rejects the whole import.
    body, rows = parse_raw_price_csv(payload.csv_text)
    if not payload.source_note.strip() or len(payload.source_note.strip()) < 20:
        raise ValueError("source_note must explain the source and unadjusted price basis")
    try:
        listing = database.get(Listing, listing_id)
        if listing is None:
            raise LookupError("Listing does not exist")
        security = database.get(Security, listing.security_id)
        database.scalar(select(Company).where(Company.id == security.company_id).with_for_update())
        if payload.symbol.strip().upper() != listing.ticker.strip().upper() or payload.currency_code != listing.currency_code.strip().upper():
            raise CSVPriceConflict("CSV symbol/currency declaration does not match this listing")
        if rows[0]["trading_date"] < listing.start_date or (listing.end_date is not None and rows[-1]["trading_date"] > listing.end_date):
            raise CSVPriceConflict("CSV trading dates fall outside the listing lifetime")
        declaration = dict(source_name=payload.source_name, source_url=str(payload.source_url), source_note=payload.source_note.strip(),
            symbol=listing.ticker, currency_code=payload.currency_code, price_basis="unadjusted",
            asserted_by_operator=True, independently_verified=False, schema_version="raw-price-csv-v1")
        declared = json.dumps(declaration, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(body).hexdigest()
        import_hash = hashlib.sha256((content_hash + "\n" + declared).encode("utf-8")).hexdigest()
        provider = "csv_" + payload.source_name
        source_id = _insert(database, DataSource.__table__, dict(id=uuid.uuid4(), provider_name=provider,
            dataset_name="RAW_DAILY_CSV"), ["provider_name", "dataset_name"])
        if source_id is None:
            source_id = database.scalar(select(DataSource.id).where(DataSource.provider_name == provider,
                DataSource.dataset_name == "RAW_DAILY_CSV"))
        existing = database.scalar(select(CSVPriceArtifact).where(CSVPriceArtifact.listing_id == listing.id,
            CSVPriceArtifact.source_id == source_id, CSVPriceArtifact.import_hash == import_hash))
        bars = {bar.trading_date: bar for bar in database.scalars(select(DailyPriceBar).where(
            DailyPriceBar.listing_id == listing.id, DailyPriceBar.source_id == source_id,
            DailyPriceBar.trading_date.in_([row["trading_date"] for row in rows])))}
        if existing is not None:
            if any(row["trading_date"] not in bars or any(getattr(bars[row["trading_date"]], key) != value for key, value in row.items()) for row in rows):
                raise CSVPriceConflict("This CSV was previously imported but current prices differ; an old-file repeat will not overwrite later corrections")
            raw_archive = database.scalar(select(RawDataArtifact).where(RawDataArtifact.ingestion_run_id == existing.ingestion_run_id))
            if raw_archive is None or raw_archive.sha256 != content_hash or hashlib.sha256(existing.body).hexdigest() != content_hash:
                raise CSVPriceConflict("Previously imported CSV archive is missing or mismatched")
            database.commit()
            return CSVPriceImportResult(ingestion_run_id=existing.ingestion_run_id, source_id=source_id,
                csv_artifact_id=existing.id, raw_artifact_id=raw_archive.id, created=False, rows_received=len(rows),
                rows_inserted=0, rows_updated=0, first_date=rows[0]["trading_date"], last_date=rows[-1]["trading_date"], sha256=content_hash)
        run = IngestionRun(source_id=source_id, listing_id=listing.id, requested_symbol=listing.ticker,
            full_history=False, status="completed", rows_received=len(rows), requested_start_date=rows[0]["trading_date"],
            requested_end_date=rows[-1]["trading_date"], completed_at=datetime.now(timezone.utc))
        database.add(run); database.flush()
        csv_id = uuid.uuid4()
        artifact = CSVPriceArtifact(id=csv_id, ingestion_run_id=run.id, source_id=source_id, listing_id=listing.id,
            body=body, byte_count=len(body), sha256=content_hash, import_hash=import_hash, declaration_json=declared)
        raw_archive = RawDataArtifact(ingestion_run_id=run.id, source_id=source_id, listing_id=listing.id,
            storage_path="database:csv_price_artifacts/" + str(csv_id), sha256=content_hash,
            content_type="text/csv; charset=utf-8", byte_count=len(body))
        database.add_all([artifact, raw_archive])
        inserted = updated = 0
        for values in rows:
            bar = bars.get(values["trading_date"])
            if bar is None:
                bar = DailyPriceBar(listing_id=listing.id, source_id=source_id, last_ingestion_run_id=run.id, **values)
                database.add(bar); inserted += 1
            else:
                for key, value in values.items():
                    setattr(bar, key, value)
                bar.last_ingestion_run_id = run.id
                updated += 1
            bars[values["trading_date"]] = bar
        database.flush()
        # SQLite numeric storage can round unusually large prices: refuse silent changes.
        for values in rows:
            bar = bars[values["trading_date"]]
            database.refresh(bar)
            if any(getattr(bar, key) != value for key, value in values.items()):
                raise ValueError("Database storage would change a supplied price; reduce precision or use PostgreSQL")
        run.rows_inserted = inserted; run.rows_updated = updated
        database.commit()
        return CSVPriceImportResult(ingestion_run_id=run.id, source_id=source_id, csv_artifact_id=artifact.id,
            raw_artifact_id=raw_archive.id, created=True, rows_received=len(rows), rows_inserted=inserted,
            rows_updated=updated, first_date=rows[0]["trading_date"], last_date=rows[-1]["trading_date"], sha256=content_hash)
    except Exception:
        database.rollback()
        raise
