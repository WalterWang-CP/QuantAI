"""Read-only, bounded inspection endpoints. No imports or calculations run here."""
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.identity import Company, Security, Listing
from app.db.models.filings import CompanyFiling, FilingSourceArtifact, RawFinancialFact
from app.db.models.share_normalization import NormalizedShareFact
from app.db.models.share_scope import CompanyShareScope
from app.db.models.sec_market_cap import SECMarketCapSnapshot
from app.db.models.csv_prices import CSVPriceArtifact
from app.db.models.market_data import DailyPriceBar, DataSource

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
Database = Annotated[Session, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]
STATIC = Path(__file__).resolve().parent / "static"
HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
}
Section = Literal["filings", "shares", "mappings", "securities", "listings", "snapshots", "artifacts", "facts", "csv-archives"]


def record(row):
    result = {}
    for column in row.__table__.columns:
        if column.name in {"body", "manifest_json", "context_json"}:
            continue
        value = getattr(row, column.name)
        if isinstance(value, (Decimal, uuid.UUID)):
            value = str(value)
        elif isinstance(value, (date, datetime)):
            value = value.isoformat()
        result[column.name] = value
    if isinstance(row, RawFinancialFact):
        result["context"] = json.loads(row.context_json)
    if isinstance(row, CSVPriceArtifact):
        result["declaration"] = json.loads(row.declaration_json)
        del result["declaration_json"]
    return result


def page(database, statement, limit, offset):
    rows = list(database.scalars(statement.limit(limit + 1).offset(offset)))
    return {"items": [record(row) for row in rows[:limit]], "has_more": len(rows) > limit,
            "limit": limit, "offset": offset}


def require_company(database, company_id):
    company = database.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company does not exist")
    return company


def require_listing(database, company_id, listing_id):
    require_company(database, company_id)
    listing = database.scalar(select(Listing).join(Security).where(
        Listing.id == listing_id, Security.company_id == company_id))
    if listing is None:
        raise HTTPException(404, "Listing does not belong to this company")
    return listing


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC / "index.html", media_type="text/html", headers=HEADERS)


@router.get("/assets/{name}", include_in_schema=False)
def asset(name: Literal["dashboard.js", "dashboard.css"]):
    media = "text/javascript" if name.endswith(".js") else "text/css"
    return FileResponse(STATIC / name, media_type=media, headers=HEADERS)


@router.get("/api/companies")
def companies(database: Database, q: Annotated[str, Query(max_length=100)] = "", limit: Limit = 25, offset: Offset = 0):
    statement = select(Company)
    if q.strip():
        statement = statement.where(func.lower(Company.legal_name).contains(q.strip().lower(), autoescape=True))
    return page(database, statement.order_by(Company.legal_name, Company.id), limit, offset)


@router.get("/api/companies/{company_id}/{section}")
def company_records(company_id: uuid.UUID, section: Section, database: Database, limit: Limit = 50, offset: Offset = 0):
    require_company(database, company_id)
    models = {"filings": CompanyFiling, "shares": NormalizedShareFact, "mappings": CompanyShareScope,
              "securities": Security, "snapshots": SECMarketCapSnapshot, "artifacts": FilingSourceArtifact}
    if section == "listings":
        statement = select(Listing).join(Security).where(Security.company_id == company_id).order_by(Listing.ticker, Listing.id)
    elif section == "facts":
        statement = select(RawFinancialFact).join(CompanyFiling).where(CompanyFiling.company_id == company_id).order_by(RawFinancialFact.period_end.desc(), RawFinancialFact.id)
    elif section == "csv-archives":
        statement = select(CSVPriceArtifact).join(Listing).join(Security).where(Security.company_id == company_id).order_by(CSVPriceArtifact.id)
    else:
        model = models[section]
        statement = select(model).where(model.company_id == company_id)
        sort = {"filings": CompanyFiling.filed_date, "shares": NormalizedShareFact.observation_date,
                "mappings": CompanyShareScope.valid_from, "snapshots": SECMarketCapSnapshot.valuation_date,
                "artifacts": FilingSourceArtifact.ingested_at}.get(section)
        statement = statement.order_by(sort.desc(), model.id) if sort is not None else statement.order_by(Security.name, Security.id)
    return page(database, statement, limit, offset)


@router.get("/api/companies/{company_id}/snapshots/{snapshot_id}")
def snapshot(company_id: uuid.UUID, snapshot_id: uuid.UUID, database: Database):
    require_company(database, company_id)
    row = database.scalar(select(SECMarketCapSnapshot).where(SECMarketCapSnapshot.id == snapshot_id,
                                                            SECMarketCapSnapshot.company_id == company_id))
    if row is None:
        raise HTTPException(404, "Snapshot does not belong to this company")
    return dict(record(row), manifest=json.loads(row.manifest_json))


@router.get("/api/companies/{company_id}/listings/{listing_id}/sources")
def price_sources(company_id: uuid.UUID, listing_id: uuid.UUID, database: Database):
    require_listing(database, company_id, listing_id)
    rows = database.execute(select(DataSource.id, DataSource.provider_name, DataSource.dataset_name,
        func.count(DailyPriceBar.id), func.min(DailyPriceBar.trading_date), func.max(DailyPriceBar.trading_date))
        .join(DailyPriceBar, DailyPriceBar.source_id == DataSource.id).where(DailyPriceBar.listing_id == listing_id)
        .group_by(DataSource.id, DataSource.provider_name, DataSource.dataset_name)
        .order_by(DataSource.provider_name, DataSource.dataset_name, DataSource.id))
    return [{"source_id": str(source_id), "provider_name": provider, "dataset_name": dataset,
             "rows": count, "first_date": first.isoformat(), "last_date": last.isoformat()}
            for source_id, provider, dataset, count, first, last in rows]


@router.get("/api/companies/{company_id}/listings/{listing_id}/prices")
def prices(company_id: uuid.UUID, listing_id: uuid.UUID, source_id: uuid.UUID, database: Database,
           start: date | None = None, end: date | None = None, limit: Limit = 50, offset: Offset = 0):
    require_listing(database, company_id, listing_id)
    if start is not None and end is not None and start > end:
        raise HTTPException(422, "Start date must be on or before end date")
    if database.get(DataSource, source_id) is None:
        raise HTTPException(404, "Price source does not exist")
    statement = select(DailyPriceBar).where(DailyPriceBar.listing_id == listing_id, DailyPriceBar.source_id == source_id)
    if start is not None:
        statement = statement.where(DailyPriceBar.trading_date >= start)
    if end is not None:
        statement = statement.where(DailyPriceBar.trading_date <= end)
    return page(database, statement.order_by(DailyPriceBar.trading_date.desc(), DailyPriceBar.id), limit, offset)
