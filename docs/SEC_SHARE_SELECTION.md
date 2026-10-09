# Security mapping and point-in-time SEC shares selection

This stage records evidence-backed mappings for a bounded single-common-share-class period and previews a deterministic SEC shares selection. It does not write legacy shares observations or market-cap rows. Prices, split adjustments, and market-cap provenance are the next stage.

## Install

Stop Uvicorn. Save all nine supplied files to their matching project paths. Create the new migration file with its exact .py filename.

```powershell
python -m alembic heads
python -m alembic upgrade head
python -m alembic current
python -m alembic check
$env:QUANTAI_TEST_DATABASE_URL = python -c "from app.core.config import settings; print(settings.database_url)"
python -m pytest -q tests/test_share_selection.py tests/test_database_migrations.py
python -m pytest -q
```

Expected head: 7a2d6f9c4e81. Expected targeted tests with PostgreSQL enabled: 43 passed. Expected full suite: 272 passed. Local suite: 209 passed, 63 PostgreSQL tests skipped. SQLite migration upgrade/check/downgrade/re-upgrade/check and offline PostgreSQL SQL generation passed. PostgreSQL execution must be verified on your machine. Existing deprecation warnings are unchanged.

## Apple: finish normalization and inspect evidence

Start the server:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Open http://127.0.0.1:8010/docs. Under Filings:

1. POST /filings/companies/{company_id}/normalize-shares with Apple UUID 9a4e920d-3bf7-440a-8f79-5a3a853d1b05. There is no JSON body. Repeat it; unchanged input should give reviews_inserted=0 and reviews_updated=0.
2. GET /filings/companies/{company_id}/normalized-shares with that UUID and as_of=2025-12-31. It returns accepted candidates available by that date. Select a recent observation and record observation_date, known_date, shares_outstanding, and raw_fact_id. These are candidates; the selector below chooses the winning revision.
3. GET /filings/companies/{company_id}, find the filing that contains the chosen raw_fact_id using GET /filings/{filing_id}/facts, and open its document_url. The filing's cover page/share-capital disclosures should support the common share class and the interval you will assert. If there is no suitable evidence, keep the mapping unregistered and send the candidate and filing responses for review.

## Find or create the common-stock security

GET /filings/companies/{company_id}/securities lists existing securities. Reuse the appropriate common_stock UUID. If the list is empty, POST /identity/securities:

```json
{
  "company_id": "9a4e920d-3bf7-440a-8f79-5a3a853d1b05",
  "name": "Apple Inc. Common Stock",
  "security_type": "common_stock",
  "isin": null,
  "start_date": null,
  "end_date": null
}
```

Copy the returned security id. If another overlapping security already exists, this initial single-class rule will refuse the mapping; separate class/ADR rules are needed. The API records your explicit assertion and evidence. It does not fetch or independently validate the evidence URL.

## Register a bounded mapping

POST /filings/companies/{company_id}/share-scope. Enter Apple's company UUID. Fill this template with actual values from your reviewed filing:

```json
{
  "security_id": "PASTE_COMMON_STOCK_UUID",
  "valid_from": "YYYY-MM-DD",
  "valid_to": "2025-12-31",
  "known_date": "YYYY-MM-DD",
  "evidence_url": "PASTE_THE_REVIEWED_FILING_DOCUMENT_URL",
  "evidence_note": "Describe the filing and the evidence that one common share class accounts for the company-wide share count throughout this bounded period.",
  "confirm_single_common_class": true
}
```

valid_from must be on or before the share observation you want to use, and must reflect the interval actually supported by the evidence. known_date is the first daily date when that mapping evidence was publicly usable; for a filing, use the next UTC day after publication (and the later date when relying on later evidence). Do not substitute today's review date for the historical public-known date. Start with one evidenced interval, not a claim about the entire 20-year history. valid_to is inclusive. known_date must be on or after valid_from.

Repeat the exact POST: it returns the same mapping id. Changed or overlapping assertions return 409 instead of overwriting original evidence. GET /filings/companies/{company_id}/share-scopes lists the mappings.

## Preview the selected shares

GET /filings/securities/{security_id}/selected-shares:

- security_id: the common-stock UUID.
- valuation_date: 2025-12-31 (must be covered by the mapping).
- max_age_days: 400 (default; explicit policy limit, configurable per request).

A successful response includes exact shares_outstanding, observation_date, known_date, mapping_id, normalized_fact_id, raw_fact_id, filing_id, artifact_id, accession_number, and equivalent_raw_fact_ids. Repeating the same query should give the same response when source data is unchanged.

The share count remains on its observation-date split basis. This is not yet a count adjusted to a selected price date. No market-cap row is created by this endpoint.

## Selection policy

1. Require an available, date-valid mapping and a common_stock security. Refuse other overlapping securities. Mapping evidence can be missing even if shares exist.
2. Recompute fact eligibility from original raw facts and filing metadata at the requested daily cutoff. Every eligible fact must have a current-rule normalization review; otherwise return 409 and request normalization again.
3. Prefer the newest observation date. For that date, prefer the latest available filing publication date. When all same-day contenders have exact acceptance timestamps, prefer the latest UTC acceptance timestamp. Date-only ties with different counts are conflicts.
4. Refuse conflicting latest filing values; never silently fall back to an older value. Identical counts can share the winning provenance and are ordered deterministically.
5. Preserve amendments as distinct filing versions. Future publications do not supersede an earlier cutoff. Refuse observations older than max_age_days.

This reconstructs public-known daily availability from the currently stored source inventory. It is not a frozen reconstruction of what your local database contained at a past ingestion time; dataset manifests and historical metadata versions remain future work.

404 means missing company/security, missing mapping, or no eligible shares at the requested cutoff. 409 means a conflicting mapping/value, unreviewed input, unsupported security scope, or stale observation. A schema-invalid request returns 422.

## Git checkpoint

After tests and the live check:

```powershell
git add app/db/models/share_scope.py app/db/models/__init__.py migrations/env.py app/filings/share_selection.py app/filings/routes.py migrations/versions/7a2d6f9c4e81_add_company_share_scopes.py tests/test_share_selection.py tests/test_database_migrations.py docs/SEC_SHARE_SELECTION.md
git diff --cached --stat
git commit -m "Add evidence-backed security mapping and SEC shares selection"
Remove-Item Env:\QUANTAI_TEST_DATABASE_URL -ErrorAction SilentlyContinue
```
