from datetime import date

import app.db.models

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models.identity import (
    Company,
    Listing,
    Security,
)
from app.identity.resolution_schemas import (
    CompanyIdentifierCreate,
    ListingProviderSymbolCreate,
    SecurityIdentifierCreate,
)
from app.identity.resolution_service import (
    add_company_identifier,
    add_listing_provider_symbol,
    add_security_identifier,
    resolve_company_identifier,
    resolve_provider_symbol,
    resolve_security_identifier,
)


def create_database():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )

    Base.metadata.create_all(
        engine
    )

    return Session(engine)


def create_identity(
    database: Session,
):
    company = Company(
        legal_name="Synthetic Corp",
        country_code="US",
    )

    database.add(company)
    database.flush()

    security = Security(
        company_id=company.id,

        name="Synthetic Common Stock",

        security_type="common_stock",

        start_date=date(
            2000,
            1,
            1,
        ),
    )

    database.add(security)
    database.flush()

    listing = Listing(
        security_id=security.id,

        ticker="SYN",

        exchange_code="NASDAQ",

        currency_code="USD",

        start_date=date(
            2000,
            1,
            1,
        ),

        is_primary=True,
    )

    database.add(listing)
    database.commit()

    return (
        company,
        security,
        listing,
    )

def test_resolve_company_identifier():
    database = create_database()

    company, _, _ = create_identity(
        database
    )

    add_company_identifier(
        database=database,

        payload=
            CompanyIdentifierCreate(
                company_id=company.id,

                scheme="cik",

                value="0000123456",
            ),
    )

    resolved = (
        resolve_company_identifier(
            database=database,

            scheme="CIK",

            value="0000123456",
        )
    )

    assert resolved.id == company.id

def test_resolve_security_identifier():
    database = create_database()

    _, security, _ = create_identity(
        database
    )

    add_security_identifier(
        database=database,

        payload=
            SecurityIdentifierCreate(
                security_id=security.id,

                scheme="figi",

                value="BBGTEST123",
            ),
    )

    resolved = (
        resolve_security_identifier(
            database=database,

            scheme="FIGI",

            value="BBGTEST123",
        )
    )

    assert (
        resolved.id
        == security.id
    )


def test_provider_symbol_override():
    database = create_database()

    _, _, listing = create_identity(
        database
    )

    add_listing_provider_symbol(
        database=database,

        payload=
            ListingProviderSymbolCreate(
                listing_id=listing.id,

                provider_name=
                    "alpha_vantage",

                symbol="SYN.TEST",
            ),
    )

    symbol = resolve_provider_symbol(
        database=database,

        listing_id=listing.id,

        provider_name=
            "alpha_vantage",
    )

    assert symbol == "SYN.TEST"

def test_provider_symbol_falls_back_to_ticker():
    database = create_database()

    _, _, listing = create_identity(
        database
    )

    symbol = resolve_provider_symbol(
        database=database,

        listing_id=listing.id,

        provider_name=
            "unknown_provider",
    )

    assert symbol == "SYN"