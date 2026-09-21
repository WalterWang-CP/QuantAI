import uuid
from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.identity.resolution_schemas import (
    CompanyAliasCreate,
    CompanyAliasRead,
    CompanyIdentifierCreate,
    CompanyIdentifierRead,
    ListingProviderSymbolCreate,
    ListingProviderSymbolRead,
    SecurityIdentifierCreate,
    SecurityIdentifierRead,
    CompanyRelationshipCreate,
    CompanyRelationshipRead,
    ListingLifecycleEventCreate,
    ListingLifecycleEventRead,
    ProviderSymbolSegmentRead,
)
from app.identity.resolution_service import (
    add_company_alias,
    add_company_identifier,
    add_listing_provider_symbol,
    add_security_identifier,
    get_company_aliases,
    get_company_identifiers,
    resolve_company_identifier,
    resolve_provider_symbol,
    resolve_security_identifier,
    add_company_relationship,
    add_listing_lifecycle_event,
    get_company_relationships,
    get_listing_lifecycle_events,
    get_provider_symbol_segments,
)


router = APIRouter(
    prefix="/identity-resolution",
    tags=["Identity Resolution"],
)


DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]

@router.post(
    "/company-identifiers",
    response_model=
        CompanyIdentifierRead,
)
def create_company_identifier(
    payload: CompanyIdentifierCreate,
    database: DatabaseSession,
):
    try:
        return add_company_identifier(
            database=database,
            payload=payload,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )


@router.get(
    "/companies/{company_id}/identifiers",
    response_model=list[
        CompanyIdentifierRead
    ],
)
def read_company_identifiers(
    company_id: uuid.UUID,
    database: DatabaseSession,
):
    try:
        return get_company_identifiers(
            database=database,
            company_id=company_id,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

@router.get(
"/companies/resolve",
)
def resolve_company(
scheme: str,
value: str,
database: DatabaseSession,
as_of_date: date | None = None,
):
    try:
        company = (
            resolve_company_identifier(
                database=database,
                scheme=scheme,
                value=value,
                as_of_date=
                    as_of_date,
            )
        )

        return {
            "company_id":
                company.id,

            "legal_name":
                company.legal_name,

            "country_code":
                company.country_code,
        }

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

@router.post(
"/security-identifiers",
response_model=
    SecurityIdentifierRead,
)
def create_security_identifier(
    payload:
        SecurityIdentifierCreate,
    database: DatabaseSession,
):
    try:
        return add_security_identifier(
            database=database,
            payload=payload,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )


@router.get(
    "/securities/resolve",
)
def resolve_security(
    scheme: str,
    value: str,
    database: DatabaseSession,
    as_of_date: date | None = None,
):
    try:
        security = (
            resolve_security_identifier(
                database=database,
                scheme=scheme,
                value=value,
                as_of_date=
                    as_of_date,
            )
        )

        return {
            "security_id":
                security.id,

            "company_id":
                security.company_id,

            "name":
                security.name,

            "security_type":
                security.security_type,
        }

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

@router.post(
"/company-aliases",
response_model=CompanyAliasRead,
)
def create_company_alias(
    payload: CompanyAliasCreate,
    database: DatabaseSession,
):
    try:
        return add_company_alias(
            database=database,
            payload=payload,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )


@router.get(
    "/companies/{company_id}/aliases",
    response_model=list[
        CompanyAliasRead
    ],
)
def read_company_aliases(
    company_id: uuid.UUID,
    database: DatabaseSession,
):
    return get_company_aliases(
        database=database,
        company_id=company_id,
    )

@router.post(
    "/provider-symbols",
    response_model=
        ListingProviderSymbolRead,
)
def create_provider_symbol(
    payload:
        ListingProviderSymbolCreate,
    database: DatabaseSession,
):
    try:
        return (
            add_listing_provider_symbol(
                database=database,
                payload=payload,
            )
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )


@router.get(
    "/listings/{listing_id}/provider-symbol",
)
def read_provider_symbol(
    listing_id: uuid.UUID,
    provider_name: str,
    database: DatabaseSession,
    as_of_date: date | None = None,
):
    try:
        symbol = resolve_provider_symbol(
            database=database,

            listing_id=listing_id,

            provider_name=
                provider_name,

            as_of_date=
                as_of_date,
        )

        return {
            "listing_id":
                listing_id,

            "provider_name":
                provider_name,

            "symbol":
                symbol,
        }

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

@router.post(
"/company-relationships",
response_model=
    CompanyRelationshipRead,
)
def create_company_relationship(
    payload:
        CompanyRelationshipCreate,
    database: DatabaseSession,
):
    try:
        return add_company_relationship(
            database=database,
            payload=payload,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        )


@router.get(
    "/companies/{company_id}/relationships",
    response_model=list[
        CompanyRelationshipRead
    ],
)
def read_company_relationships(
    company_id: uuid.UUID,
    database: DatabaseSession,
):
    try:
        return get_company_relationships(
            database=database,
            company_id=company_id,
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )


@router.post(
    "/listing-events",
    response_model=
        ListingLifecycleEventRead,
)
def create_listing_event(
    payload:
        ListingLifecycleEventCreate,
    database: DatabaseSession,
):
    try:
        return (
            add_listing_lifecycle_event(
                database=database,
                payload=payload,
            )
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        )


@router.get(
    "/listings/{listing_id}/events",
    response_model=list[
        ListingLifecycleEventRead
    ],
)
def read_listing_events(
    listing_id: uuid.UUID,
    database: DatabaseSession,
):
    try:
        return (
            get_listing_lifecycle_events(
                database=database,
                listing_id=listing_id,
            )
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )


@router.get(
    "/listings/{listing_id}/provider-symbol-segments",
    response_model=list[
        ProviderSymbolSegmentRead
    ],
)
def read_provider_symbol_segments(
    listing_id: uuid.UUID,
    provider_name: str,
    start_date: date,
    end_date: date,
    database: DatabaseSession,
):
    try:
        return (
            get_provider_symbol_segments(
                database=database,

                listing_id=
                    listing_id,

                provider_name=
                    provider_name,

                start_date=
                    start_date,

                end_date=
                    end_date,
            )
        )

    except LookupError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        )