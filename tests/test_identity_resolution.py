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
from app.identity.resolution_schemas import (
    CompanyIdentifierCreate,
    CompanyRelationshipCreate,
    ListingLifecycleEventCreate,
    ListingProviderSymbolCreate,
    SecurityIdentifierCreate,
)
from app.identity.resolution_service import (
    add_company_identifier,
    add_company_relationship,
    add_listing_lifecycle_event,
    add_listing_provider_symbol,
    add_security_identifier,
    get_company_relationships,
    get_listing_lifecycle_events,
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


def test_company_relationship():
    database = create_database()

    company_a, _, _ = create_identity(
        database
    )

    company_b = Company(
        legal_name="Successor Corp",
        country_code="US",
    )

    database.add(company_b)
    database.commit()

    relationship = (
        add_company_relationship(
            database=database,

            payload=
                CompanyRelationshipCreate(
                    source_company_id=
                        company_a.id,

                    target_company_id=
                        company_b.id,

                    relationship_type=
                        "merged_into",

                    known_date=date(
                        2024,
                        5,
                        1,
                    ),

                    effective_date=date(
                        2024,
                        7,
                        1,
                    ),

                    note=
                        "Synthetic merger.",
                ),
        )
    )

    assert (
        relationship
        .source_company_id
        == company_a.id
    )

    assert (
        relationship
        .target_company_id
        == company_b.id
    )

    relationships = (
        get_company_relationships(
            database=database,
            company_id=company_a.id,
        )
    )

    assert len(
        relationships
    ) == 1


def test_company_relationship():
    database = create_database()

    company_a, _, _ = create_identity(
        database
    )

    company_b = Company(
        legal_name="Successor Corp",
        country_code="US",
    )

    database.add(company_b)
    database.commit()

    relationship = (
        add_company_relationship(
            database=database,

            payload=
                CompanyRelationshipCreate(
                    source_company_id=
                        company_a.id,

                    target_company_id=
                        company_b.id,

                    relationship_type=
                        "merged_into",

                    known_date=date(
                        2024,
                        5,
                        1,
                    ),

                    effective_date=date(
                        2024,
                        7,
                        1,
                    ),

                    note=
                        "Synthetic merger.",
                ),
        )
    )

    assert (
        relationship
        .source_company_id
        == company_a.id
    )

    assert (
        relationship
        .target_company_id
        == company_b.id
    )

    relationships = (
        get_company_relationships(
            database=database,
            company_id=company_a.id,
        )
    )

    assert len(
        relationships
    ) == 1

def test_listing_ticker_change():
    database = create_database()

    _, security, old_listing = (
        create_identity(
            database
        )
    )

    new_listing = Listing(
        security_id=security.id,

        ticker="NEW",

        exchange_code="NASDAQ",

        currency_code="USD",

        start_date=date(
            2024,
            7,
            1,
        ),

        is_primary=True,
    )

    database.add(new_listing)
    database.commit()

    event = (
        add_listing_lifecycle_event(
            database=database,

            payload=
                ListingLifecycleEventCreate(
                    listing_id=
                        old_listing.id,

                    successor_listing_id=
                        new_listing.id,

                    event_type=
                        "ticker_change",

                    known_date=date(
                        2024,
                        6,
                        15,
                    ),

                    effective_date=date(
                        2024,
                        7,
                        1,
                    ),

                    note=
                        "Synthetic ticker change.",
                ),
        )
    )

    assert (
        event.successor_listing_id
        == new_listing.id
    )

    events = (
        get_listing_lifecycle_events(
            database=database,
            listing_id=
                old_listing.id,
        )
    )

    assert len(events) == 1

def test_provider_symbol_respects_validity():
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

                symbol="OLD",

                valid_from=date(
                    2020,
                    1,
                    1,
                ),

                valid_to=date(
                    2023,
                    12,
                    31,
                ),
            ),
    )

    add_listing_provider_symbol(
        database=database,

        payload=
            ListingProviderSymbolCreate(
                listing_id=listing.id,

                provider_name=
                    "alpha_vantage",

                symbol="NEW",

                valid_from=date(
                    2024,
                    1,
                    1,
                ),

                valid_to=None,
            ),
    )

    old_symbol = (
        resolve_provider_symbol(
            database=database,

            listing_id=listing.id,

            provider_name=
                "alpha_vantage",

            as_of_date=date(
                2023,
                6,
                1,
            ),
        )
    )

    new_symbol = (
        resolve_provider_symbol(
            database=database,

            listing_id=listing.id,

            provider_name=
                "alpha_vantage",

            as_of_date=date(
                2025,
                6,
                1,
            ),
        )
    )

    assert old_symbol == "OLD"

    assert new_symbol == "NEW"