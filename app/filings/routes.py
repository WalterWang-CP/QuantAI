import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.filings import CompanyFiling, FilingSourceArtifact, RawFinancialFact
from app.db.models.identity import Company
from app.filings.schemas import FilingRead, RawFactRead, SECImportRequest, SECImportResult
from app.filings.sec_service import SECIdentityError, import_sec_company
from app.filings.service import FilingConflictError
from app.db.models.share_normalization import NormalizedShareFact
from app.filings.share_normalization import (NormalizedShareRead, ShareNormalizationResult, normalize_company_shares)
from datetime import date
from app.providers.errors import ProviderRateLimitError, ProviderRequestError, ProviderTemporaryError

router = APIRouter(prefix="/filings", tags=["Filings"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post("/companies/{company_id}/import-sec", response_model=SECImportResult)
def import_company(company_id: uuid.UUID, payload: SECImportRequest, database: DatabaseSession):
    try:
        return import_sec_company(database, company_id, payload)
    except LookupError as error:
        raise HTTPException(404, detail=str(error)) from error
    except (SECIdentityError, FilingConflictError) as error:
        raise HTTPException(409, detail=str(error)) from error
    except ProviderRateLimitError as error:
        raise HTTPException(429, detail=str(error)) from error
    except ProviderRequestError as error:
        raise HTTPException(400, detail=str(error)) from error
    except ProviderTemporaryError as error:
        raise HTTPException(502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(422, detail=str(error)) from error


@router.get("/companies/{company_id}", response_model=list[FilingRead])
def list_company_filings(company_id: uuid.UUID, database: DatabaseSession,
                         limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    if database.get(Company, company_id) is None:
        raise HTTPException(404, detail="Company does not exist")
    return list(database.scalars(select(CompanyFiling).where(CompanyFiling.company_id == company_id)
        .order_by(CompanyFiling.filed_date, CompanyFiling.accession_number, CompanyFiling.id)
        .offset(offset).limit(limit)))


@router.get("/{filing_id}/facts", response_model=list[RawFactRead])
def list_filing_facts(filing_id: uuid.UUID, database: DatabaseSession,
                     limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    if database.get(CompanyFiling, filing_id) is None:
        raise HTTPException(404, detail="Filing does not exist")
    return list(database.scalars(select(RawFinancialFact).where(RawFinancialFact.filing_id == filing_id)
        .order_by(RawFinancialFact.fact_hash, RawFinancialFact.id).offset(offset).limit(limit)))


@router.get("/artifacts/{artifact_id}")
def download_artifact(artifact_id: uuid.UUID, database: DatabaseSession):
    artifact = database.get(FilingSourceArtifact, artifact_id)
    if artifact is None:
        raise HTTPException(404, detail="Artifact does not exist")
    return Response(content=artifact.body, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{artifact.id}.json"'})


@router.post("/companies/{company_id}/normalize-shares", response_model=ShareNormalizationResult)
def normalize_shares(company_id: uuid.UUID, database: DatabaseSession):
    try:
        return normalize_company_shares(database, company_id)
    except LookupError as error:
        raise HTTPException(404, detail=str(error)) from error


@router.get("/companies/{company_id}/normalized-shares", response_model=list[NormalizedShareRead])
def list_normalized_shares(company_id: uuid.UUID, database: DatabaseSession,
                           as_of: date | None = None,
                           limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    if database.get(Company, company_id) is None:
        raise HTTPException(404, detail="Company does not exist")
    statement = select(NormalizedShareFact).where(NormalizedShareFact.company_id == company_id)
    if as_of is not None:
        # All eligible filing versions, not a winner selected for market-cap calculation.
        statement = statement.where(NormalizedShareFact.status == "accepted",
            NormalizedShareFact.known_date <= as_of, NormalizedShareFact.observation_date <= as_of)
    return list(database.scalars(statement.order_by(NormalizedShareFact.observation_date,
        NormalizedShareFact.known_date, NormalizedShareFact.raw_fact_id).offset(offset).limit(limit)))
