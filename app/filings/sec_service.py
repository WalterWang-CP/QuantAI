"""Manual SEC import into provenance storage; no normalized shares are produced."""
import re
import uuid
from datetime import date, datetime
from urllib.parse import quote

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.identity import Company
from app.db.models.identity_resolution import CompanyIdentifier
from app.db.models.market_data import DataSource
from app.filings.schemas import FilingCreate, RawFactCreate, SECImportRequest, SECImportResult
from app.filings.service import _insert, archive_filing_response, store_filing
from app.providers.errors import ProviderTemporaryError
from app.providers.sec import SECClient, decode_sec_json, normalize_cik


class SECIdentityError(ValueError):
    pass


def verify_company_cik(database, company_id, request):
    if database.get(Company, company_id) is None:
        raise LookupError("Company does not exist")
    # Require an explicit identifier mapping covering the requested range.
    rows = database.scalars(select(CompanyIdentifier).where(CompanyIdentifier.scheme == "CIK"))
    matching = []
    for row in rows:
        try:
            if normalize_cik(row.value) == request.cik:
                matching.append(row)
        except ValueError:
            continue
    end = request.end_date or date.today()
    own = [row for row in matching if row.company_id == company_id and
           (row.valid_from is None or request.start_date is not None and row.valid_from <= request.start_date) and
           (row.valid_to is None or row.valid_to >= end)]
    if not own:
        raise SECIdentityError("Register this company's CIK identifier with validity covering the import range")
    for row in matching:
        if row.company_id != company_id and (row.valid_from is None or row.valid_from <= end) and (
            request.start_date is None or row.valid_to is None or row.valid_to >= request.start_date
        ):
            raise SECIdentityError("CIK is mapped to another company during the requested range")


def _date(value):
    return date.fromisoformat(value) if value else None


def _acceptance(value):
    if not value:
        return None
    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # Preserve unknown precision rather than guessing the timezone of a naive value.
    return value if value.tzinfo is not None else None


def _in_range(filed_date, request):
    return (request.start_date is None or filed_date is not None and filed_date >= request.start_date) and (
        request.end_date is None or filed_date is not None and filed_date <= request.end_date
    )


def parse_submissions(response, cik, *, history=False):
    payload = decode_sec_json(response)
    if not history:
        try:
            if normalize_cik(payload["cik"]) != cik:
                raise SECIdentityError("SEC submissions CIK does not match requested company")
            columns = payload["filings"]["recent"]
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, SECIdentityError):
                raise
            raise ProviderTemporaryError("Malformed SEC submissions response") from error
    else:
        columns = payload
    try:
        count = len(columns["accessionNumber"])
        required = ["accessionNumber", "filingDate", "form"]
        optional = ["reportDate", "acceptanceDateTime", "primaryDocument"]
        for name in required:
            if not isinstance(columns[name], list) or len(columns[name]) != count:
                raise ValueError("Mismatched columns")
        for name in optional:
            if name in columns and (not isinstance(columns[name], list) or len(columns[name]) != count):
                raise ValueError("Mismatched optional columns")
        records = {}
        for index in range(count):
            accession = columns["accessionNumber"][index]
            if not isinstance(accession, str) or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
                raise ValueError("Invalid accession")
            primary = columns.get("primaryDocument", [None] * count)[index]
            document_url = None
            if primary:
                document_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{quote(primary, safe='/')}"
            records[accession] = {
                "accession_number": accession, "form_type": columns["form"][index],
                "filed_date": _date(columns["filingDate"][index]),
                "report_period": _date(columns.get("reportDate", [None] * count)[index]),
                "accepted_at": _acceptance(columns.get("acceptanceDateTime", [None] * count)[index]),
                "document_url": document_url,
            }
        return records, payload
    except (KeyError, TypeError, ValueError) as error:
        raise ProviderTemporaryError("Malformed SEC submissions columns") from error


def _history_overlaps(descriptor, request):
    try:
        start, end = _date(descriptor.get("filingFrom")), _date(descriptor.get("filingTo"))
    except (TypeError, ValueError) as error:
        raise ProviderTemporaryError("Malformed SEC history range") from error
    return not (request.start_date and end and end < request.start_date or
                request.end_date and start and start > request.end_date)


def import_sec_company(database: Session, company_id: uuid.UUID, request: SECImportRequest,
                       *, client=None) -> SECImportResult:
    """Own the request transaction. Fetch before taking the company write lock."""
    verify_company_cik(database, company_id, request)
    client = client or SECClient()
    submissions = client.fetch_submissions(request.cik)
    metadata, top = parse_submissions(submissions, request.cik)
    responses = [submissions]
    metadata_responses = {accession: submissions for accession in metadata}
    descriptors = top.get("filings", {}).get("files", [])
    if not isinstance(descriptors, list) or any(not isinstance(item, dict) or not isinstance(item.get("name"), str)
                                                for item in descriptors):
        raise ProviderTemporaryError("Malformed SEC submissions history list")
    selected = [item for item in descriptors if _history_overlaps(item, request)]
    selected = list({item["name"]: item for item in selected}.values())
    history_complete = not selected
    warnings = []
    if request.include_history:
        history_complete = len(selected) <= settings.sec_max_history_files
        for item in selected[:settings.sec_max_history_files]:
            response = client.fetch_history_file(request.cik, item["name"])
            records, _ = parse_submissions(response, request.cik, history=True)
            responses.append(response)
            for accession, record in records.items():
                if accession in metadata:
                    for name, value in record.items():
                        existing = metadata[accession][name]
                        if existing is not None and value is not None and existing != value:
                            raise ProviderTemporaryError("Conflicting SEC submissions metadata")
                        if existing is None:
                            metadata[accession][name] = value
                else:
                    metadata[accession] = record
                    metadata_responses[accession] = response
    if not history_complete:
        warnings.append("Some requested submissions history files were not fetched")
    facts_response = client.fetch_company_facts(request.cik)
    responses.append(facts_response)
    facts_payload = decode_sec_json(facts_response)
    try:
        if normalize_cik(facts_payload["cik"]) != request.cik:
            raise SECIdentityError("SEC company facts CIK does not match requested company")
        taxonomies = facts_payload["facts"]
        if not isinstance(taxonomies, dict):
            raise TypeError()
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, SECIdentityError):
            raise
        raise ProviderTemporaryError("Malformed SEC company facts response") from error

    selected_metadata = {key: value for key, value in metadata.items()
                         if value["form_type"] in request.forms and _in_range(value["filed_date"], request)}
    grouped = {}
    received = rejected = 0
    for taxonomy, concepts in taxonomies.items():
        if not isinstance(concepts, dict):
            raise ProviderTemporaryError("Malformed SEC fact taxonomy")
        for tag, concept in concepts.items():
            if tag not in request.tags:
                continue
            if not isinstance(concept, dict) or not isinstance(concept.get("units"), dict):
                raise ProviderTemporaryError("Malformed SEC fact units")
            for unit, values in concept["units"].items():
                if not isinstance(values, list):
                    raise ProviderTemporaryError("Malformed SEC fact rows")
                for value in values:
                    if not isinstance(value, dict):
                        received += 1
                        rejected += 1
                        if len(warnings) < 25:
                            warnings.append(f"Rejected {taxonomy}:{tag}: non-object fact")
                        continue
                    if value.get("form") not in request.forms:
                        continue
                    received += 1
                    try:
                        filed_date = _date(value.get("filed"))
                        if filed_date is None and (request.start_date or request.end_date):
                            raise ValueError("Fact has unknown filing date for a bounded import range")
                        if not _in_range(filed_date, request):
                            received -= 1
                            continue
                        accession = value["accn"]
                        if not isinstance(accession, str) or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
                            raise ValueError("Invalid accession")
                        context = {name: str(value[name]) for name in ("fy", "fp", "frame") if value.get(name) is not None}
                        context["scope"] = "entity"
                        fact = RawFactCreate(taxonomy=taxonomy, tag=tag, unit=unit,
                            period_start=_date(value.get("start")), period_end=_date(value.get("end")),
                            value=value["val"], context=context)
                        record = metadata.get(accession) or selected_metadata.get(accession)
                        if record is None:
                            # Company-facts metadata is dated; never pretend fact.end is the report period.
                            record = {"accession_number": accession, "form_type": value["form"],
                                      "filed_date": filed_date, "report_period": None,
                                      "accepted_at": None, "document_url": None}
                            metadata_responses[accession] = facts_response
                            if history_complete and len(warnings) < 25:
                                warnings.append("Some fact filings lack submissions metadata; only fact-supplied dates are available")
                            history_complete = False
                        if record["filed_date"] != filed_date or record["form_type"] != value["form"]:
                            raise ValueError("Fact and submissions filing metadata disagree")
                        FilingCreate(company_id=company_id, source_id=uuid.uuid4(), cik=request.cik,
                                     **record, facts=[fact])
                        selected_metadata[accession] = record
                        grouped.setdefault(accession, []).append(fact)
                    except (KeyError, TypeError, ValueError, ValidationError) as error:
                        rejected += 1
                        if len(warnings) < 25:
                            warnings.append(f"Rejected {taxonomy}:{tag}: {str(error)[:180]}")

    try:
        # Serialize imports for this company, then recheck the explicit identity mapping.
        database.scalar(select(Company).where(Company.id == company_id).with_for_update())
        verify_company_cik(database, company_id, request)
        source_id = _insert(database, DataSource.__table__, {
            "id": uuid.uuid4(), "provider_name": "sec", "dataset_name": "FILING_FACTS",
        }, ["provider_name", "dataset_name"])
        if source_id is None:
            source_id = database.scalar(select(DataSource.id).where(
                DataSource.provider_name == "sec", DataSource.dataset_name == "FILING_FACTS",
            ))
        archive_ids = {}
        artifacts_inserted = 0
        for response in responses:
            artifact_id, created = archive_filing_response(database, company_id, source_id,
                raw_body=response.body, source_url=response.url,
                content_type=response.content_type, fetched_at=response.fetched_at)
            archive_ids[response.url] = artifact_id
            artifacts_inserted += created
        filings_inserted = inserted = existing = 0
        for accession, record in selected_metadata.items():
            response = metadata_responses.get(accession, facts_response)
            result = store_filing(database, FilingCreate(company_id=company_id, source_id=source_id,
                cik=request.cik, **record), raw_body=response.body, source_url=response.url,
                content_type=response.content_type, fetched_at=response.fetched_at,
                artifact_id=archive_ids[response.url])
            filings_inserted += result.filing_created
            if accession in grouped:
                result = store_filing(database, FilingCreate(company_id=company_id, source_id=source_id,
                    cik=request.cik, **record, facts=grouped[accession]),
                    raw_body=facts_response.body, source_url=facts_response.url,
                    content_type=facts_response.content_type, fetched_at=facts_response.fetched_at,
                    artifact_id=archive_ids[facts_response.url])
                inserted += result.facts_inserted
                existing += result.facts_existing
        database.commit()
        return SECImportResult(company_id=company_id, cik=request.cik,
            status="incomplete" if rejected or not history_complete else "completed" if received else "no_facts",
            filings_seen=len(selected_metadata), filings_inserted=filings_inserted,
            facts_received=received, facts_inserted=inserted, facts_existing=existing,
            facts_rejected=rejected, artifacts_inserted=artifacts_inserted,
            metadata_history_complete=history_complete, warnings=warnings)
    except Exception:
        database.rollback()
        raise
