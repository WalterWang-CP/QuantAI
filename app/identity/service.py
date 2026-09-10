import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.identity import Company, Listing, Security
from app.identity.schemas import (
    CompanyCreate,
    ListingCreate,
    SecurityCreate,
)


def create_company(
    database: Session,
    company_data: CompanyCreate,
) -> Company:
    company = Company(
        legal_name=company_data.legal_name,
        country_code=company_data.country_code,
        website=company_data.website,
    )

    database.add(company)
    database.commit()
    database.refresh(company)

    return company


def get_companies(
    database: Session,
) -> list[Company]:
    statement = select(Company).order_by(
        Company.legal_name,
    )

    return list(
        database.scalars(statement).all()
    )


def create_security(
    database: Session,
    security_data: SecurityCreate,
) -> Security:
    company = database.get(
        Company,
        security_data.company_id,
    )

    if company is None:
        raise ValueError("Company does not exist.")

    security = Security(
        company_id=security_data.company_id,
        name=security_data.name,
        security_type=security_data.security_type,
        isin=security_data.isin,
        start_date=security_data.start_date,
        end_date=security_data.end_date,
    )

    database.add(security)
    database.commit()
    database.refresh(security)

    return security


def create_listing(
    database: Session,
    listing_data: ListingCreate,
) -> Listing:
    security = database.get(
        Security,
        listing_data.security_id,
    )

    if security is None:
        raise ValueError("Security does not exist.")

    listing = Listing(
        security_id=listing_data.security_id,
        ticker=listing_data.ticker.upper(),
        exchange_code=listing_data.exchange_code.upper(),
        currency_code=listing_data.currency_code.upper(),
        start_date=listing_data.start_date,
        end_date=listing_data.end_date,
        is_primary=listing_data.is_primary,
    )

    database.add(listing)
    database.commit()
    database.refresh(listing)

    return listing