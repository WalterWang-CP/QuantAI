from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.identity.schemas import (
    CompanyCreate,
    CompanyRead,
    ListingCreate,
    ListingRead,
    SecurityCreate,
    SecurityRead,
)
from app.identity.service import (
    create_company,
    create_listing,
    create_security,
    get_companies,
)


router = APIRouter(
    prefix="/identity",
    tags=["Identity"],
)


DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]


@router.post(
    "/companies",
    response_model=CompanyRead,
    status_code=201,
)
def add_company(
    company_data: CompanyCreate,
    database: DatabaseSession,
):
    return create_company(
        database,
        company_data,
    )


@router.get(
    "/companies",
    response_model=list[CompanyRead],
)
def read_companies(
    database: DatabaseSession,
):
    return get_companies(database)


@router.post(
    "/securities",
    response_model=SecurityRead,
    status_code=201,
)
def add_security(
    security_data: SecurityCreate,
    database: DatabaseSession,
):
    try:
        return create_security(
            database,
            security_data,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )


@router.post(
    "/listings",
    response_model=ListingRead,
    status_code=201,
)
def add_listing(
    listing_data: ListingCreate,
    database: DatabaseSession,
):
    try:
        return create_listing(
            database,
            listing_data,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )