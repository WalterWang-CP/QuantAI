import uuid
from datetime import date

from sqlalchemy import (
    and_,
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.db.models.identity import (
    Company,
    Listing,
    Security,
)
from app.db.models.identity_resolution import (
    CompanyAlias,
    CompanyIdentifier,
    ListingProviderSymbol,
    SecurityIdentifier,
)
from app.identity.resolution_schemas import (
    CompanyAliasCreate,
    CompanyIdentifierCreate,
    ListingProviderSymbolCreate,
    SecurityIdentifierCreate,
)

def valid_as_of(
    model,
    as_of_date: date,
):
    return and_(
        or_(
            model.valid_from.is_(None),
            model.valid_from
            <= as_of_date,
        ),
        or_(
            model.valid_to.is_(None),
            model.valid_to
            >= as_of_date,
        ),
    )

def add_company_identifier(
    database: Session,
    payload: CompanyIdentifierCreate,
) -> CompanyIdentifier:
    company = database.get(
        Company,
        payload.company_id,
    )

    if company is None:
        raise LookupError(
            "Company does not exist."
        )

    statement = select(
        CompanyIdentifier
    ).where(
        CompanyIdentifier.company_id
        == payload.company_id,

        CompanyIdentifier.scheme
        == payload.scheme,

        CompanyIdentifier.value
        == payload.value,

        CompanyIdentifier.valid_from
        == payload.valid_from,
    )

    existing = database.scalar(
        statement
    )

    if existing is not None:
        existing.valid_to = (
            payload.valid_to
        )

        existing.is_primary = (
            payload.is_primary
        )

        database.commit()
        database.refresh(existing)

        return existing

    identifier = CompanyIdentifier(
        company_id=
            payload.company_id,

        scheme=
            payload.scheme,

        value=
            payload.value,

        valid_from=
            payload.valid_from,

        valid_to=
            payload.valid_to,

        is_primary=
            payload.is_primary,
    )

    database.add(identifier)
    database.commit()
    database.refresh(identifier)

    return identifier


def get_company_identifiers(
    database: Session,
    company_id: uuid.UUID,
) -> list[CompanyIdentifier]:
    company = database.get(
        Company,
        company_id,
    )

    if company is None:
        raise LookupError(
            "Company does not exist."
        )

    statement = (
        select(
            CompanyIdentifier
        )
        .where(
            CompanyIdentifier.company_id
            == company_id
        )
        .order_by(
            CompanyIdentifier.scheme,
            CompanyIdentifier.valid_from,
        )
    )

    return list(
        database.scalars(
            statement
        ).all()
    )


def resolve_company_identifier(
    database: Session,
    scheme: str,
    value: str,
    as_of_date: date | None = None,
) -> Company:
    scheme = (
        scheme
        .strip()
        .upper()
    )

    value = value.strip()

    statement = (
        select(Company)
        .join(
            CompanyIdentifier,
            CompanyIdentifier.company_id
            == Company.id,
        )
        .where(
            CompanyIdentifier.scheme
            == scheme,

            CompanyIdentifier.value
            == value,
        )
    )

    if as_of_date is not None:
        statement = statement.where(
            valid_as_of(
                CompanyIdentifier,
                as_of_date,
            )
        )

    company = database.scalar(
        statement
    )

    if company is None:
        raise LookupError(
            "No company matches that "
            "identifier."
        )

    return company

def add_security_identifier(
    database: Session,
    payload: SecurityIdentifierCreate,
) -> SecurityIdentifier:
    security = database.get(
        Security,
        payload.security_id,
    )

    if security is None:
        raise LookupError(
            "Security does not exist."
        )

    statement = select(
        SecurityIdentifier
    ).where(
        SecurityIdentifier.security_id
        == payload.security_id,

        SecurityIdentifier.scheme
        == payload.scheme,

        SecurityIdentifier.value
        == payload.value,

        SecurityIdentifier.valid_from
        == payload.valid_from,
    )

    existing = database.scalar(
        statement
    )

    if existing is not None:
        existing.valid_to = (
            payload.valid_to
        )

        existing.is_primary = (
            payload.is_primary
        )

        database.commit()
        database.refresh(existing)

        return existing

    identifier = SecurityIdentifier(
        security_id=
            payload.security_id,

        scheme=
            payload.scheme,

        value=
            payload.value,

        valid_from=
            payload.valid_from,

        valid_to=
            payload.valid_to,

        is_primary=
            payload.is_primary,
    )

    database.add(identifier)
    database.commit()
    database.refresh(identifier)

    return identifier

def resolve_security_identifier(
    database: Session,
    scheme: str,
    value: str,
    as_of_date: date | None = None,
) -> Security:
    scheme = (
        scheme
        .strip()
        .upper()
    )

    value = value.strip()

    statement = (
        select(Security)
        .join(
            SecurityIdentifier,
            SecurityIdentifier.security_id
            == Security.id,
        )
        .where(
            SecurityIdentifier.scheme
            == scheme,

            SecurityIdentifier.value
            == value,
        )
    )

    if as_of_date is not None:
        statement = statement.where(
            valid_as_of(
                SecurityIdentifier,
                as_of_date,
            )
        )

    security = database.scalar(
        statement
    )

    if security is None:
        raise LookupError(
            "No security matches that "
            "identifier."
        )

    return security

def add_company_alias(
    database: Session,
    payload: CompanyAliasCreate,
) -> CompanyAlias:
    company = database.get(
        Company,
        payload.company_id,
    )

    if company is None:
        raise LookupError(
            "Company does not exist."
        )

    alias = CompanyAlias(
        company_id=
            payload.company_id,

        alias=
            payload.alias.strip(),

        alias_type=
            payload.alias_type.strip(),

        valid_from=
            payload.valid_from,

        valid_to=
            payload.valid_to,
    )

    database.add(alias)
    database.commit()
    database.refresh(alias)

    return alias


def get_company_aliases(
    database: Session,
    company_id: uuid.UUID,
) -> list[CompanyAlias]:
    statement = (
        select(CompanyAlias)
        .where(
            CompanyAlias.company_id
            == company_id
        )
        .order_by(
            CompanyAlias.alias
        )
    )

    return list(
        database.scalars(
            statement
        ).all()
    )

def add_listing_provider_symbol(
    database: Session,
    payload:
        ListingProviderSymbolCreate,
) -> ListingProviderSymbol:
    listing = database.get(
        Listing,
        payload.listing_id,
    )

    if listing is None:
        raise LookupError(
            "Listing does not exist."
        )

    statement = select(
        ListingProviderSymbol
    ).where(
        ListingProviderSymbol.listing_id
        == payload.listing_id,

        ListingProviderSymbol.provider_name
        == payload.provider_name,

        ListingProviderSymbol.symbol
        == payload.symbol,

        ListingProviderSymbol.valid_from
        == payload.valid_from,
    )

    existing = database.scalar(
        statement
    )

    if existing is not None:
        existing.valid_to = (
            payload.valid_to
        )

        database.commit()
        database.refresh(existing)

        return existing

    symbol = ListingProviderSymbol(
        listing_id=
            payload.listing_id,

        provider_name=
            payload.provider_name,

        symbol=
            payload.symbol,

        valid_from=
            payload.valid_from,

        valid_to=
            payload.valid_to,
    )

    database.add(symbol)
    database.commit()
    database.refresh(symbol)

    return symbol

def resolve_provider_symbol(
    database: Session,
    listing_id: uuid.UUID,
    provider_name: str,
    as_of_date: date | None = None,
) -> str:
    listing = database.get(
        Listing,
        listing_id,
    )

    if listing is None:
        raise LookupError(
            "Listing does not exist."
        )

    provider_name = (
        provider_name
        .strip()
        .lower()
    )

    statement = select(
        ListingProviderSymbol
    ).where(
        ListingProviderSymbol.listing_id
        == listing_id,

        ListingProviderSymbol.provider_name
        == provider_name,
    )

    if as_of_date is not None:
        statement = statement.where(
            valid_as_of(
                ListingProviderSymbol,
                as_of_date,
            )
        )

    statement = statement.order_by(
        ListingProviderSymbol.valid_from
        .desc()
    )

    provider_symbol = (
        database.scalar(
            statement
        )
    )

    if provider_symbol is not None:
        return provider_symbol.symbol

    return listing.ticker