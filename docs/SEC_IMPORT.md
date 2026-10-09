# SEC import: local verification

This stage adds manual SEC downloads and filing/raw-fact inspection. The default
import selects two shares-related tags. Facts remain pending normalization; the
import does not create market-cap-ready shares observations.

## Configuration

Append the following to your existing `.env`, replacing the contact email:

```dotenv
SEC_USER_AGENT="QuantAI Walter your-real-email@example.com"
```

Retain your existing database URL and provider keys. The new `.env.example` shows
optional SEC settings; replacing the real `.env` is unnecessary. The default
request interval is 0.5 seconds, timeout 30 seconds, and maximum attempts three.
A short in-memory cache avoids repeated downloads. Request slots, cooldowns, and
cache are shared across threads in one Python process. For this pilot, use one
server process; coordination across processes/machines is a later worker feature.
The SEC's published maximum is 10 requests/second across a user's machines.

## Tests

Run from your QuantAI folder with `.venv` activated and PostgreSQL running:

```powershell
python -m alembic check
$env:QUANTAI_TEST_DATABASE_URL = python -c "from app.core.config import settings; print(settings.database_url)"
python -m pytest -q tests/test_sec_provider.py tests/test_sec_ingestion.py
python -m pytest -q
```

Expected: 52 passed for the new tests, then 210 passed for the full suite. No new
migration or dependency is required in this stage. Without PostgreSQL enabled,
the full suite has 169 passed and 41 skipped. HTTP download tests use mocked
responses; the following manual check verifies actual SEC access.

## Live import through API documentation

Start the server after setting the contact email:

```powershell
python -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs.

1. Under Identity, run `GET /identity/companies`. Choose the existing Apple Inc.
   company and copy its UUID. If it does not exist, use `POST /identity/companies`:

```json
{
  "legal_name": "Apple Inc.",
  "country_code": "US",
  "website": "https://www.apple.com"
}
```

2. Under Identity Resolution, inspect
   `GET /identity-resolution/companies/{company_id}/identifiers`.
   If the correct CIK mapping already exists, use it. Otherwise run
   `POST /identity-resolution/company-identifiers`, inserting Apple's UUID:

```json
{
  "company_id": "REPLACE_WITH_APPLE_COMPANY_UUID",
  "scheme": "CIK",
  "value": "0000320193",
  "valid_from": null,
  "valid_to": null,
  "is_primary": true
}
```

Use an unbounded mapping only when it applies throughout the import range.
The importer rejects missing or overlapping mappings to a different company.
Do not attach Apple's CIK to another company's local record.

3. Under Filings, run `POST /filings/companies/{company_id}/import-sec` using
   the same Apple UUID and this body:

```json
{
  "cik": "0000320193",
  "start_date": "2019-01-01",
  "end_date": "2025-12-31",
  "include_history": true
}
```

The endpoint downloads submissions, relevant older submissions files, and company
facts. It archives each response once by company/source/content hash. Metadata-only
filings are retained. Exact decimal fact values and reported filing versions are
preserved. Facts with missing submissions metadata retain their available
fact-supplied filing date; report period and acceptance time remain unknown.

4. Inspect the returned summary. `completed` means the selected import completed
   without reported rejected facts or missing submissions metadata/history.
   `incomplete` includes warnings to inspect. `no_facts` means no selected facts
   were found. None of these statuses certify full financial-statement coverage,
   historical universe completeness, or suitability of shares for valuation.

5. Run `GET /filings/companies/{company_id}`. Copy a filing UUID and call
   `GET /filings/{filing_id}/facts`. Raw fact rows show tag, unit, period, exact
   value text, source artifact, and normalization status.

6. Download original source bytes with
   `GET /filings/artifacts/{artifact_id}` using a returned artifact UUID.

7. Repeat the same import. With unchanged source responses, expect zero newly
   inserted filings/facts/artifacts and existing facts counted separately. A changed
   SEC response may create another archived artifact even when selected facts
   remain unchanged. This preserves the downloaded evidence.

Return the pytest results and the live import summary for review. If SEC returns
HTTP 403, check the identifying User-Agent and network access. A 429 response means
retry after the cooldown. Long Retry-After intervals fail the synchronous request
rather than issuing another request before that interval.

## Git checkpoint

```powershell
git add app/core/config.py app/main.py app/providers/sec.py app/filings/schemas.py app/filings/service.py app/filings/sec_service.py app/filings/routes.py .env.example tests/test_sec_provider.py tests/test_sec_ingestion.py docs/SEC_IMPORT.md
git diff --cached --stat
git commit -m "Add SEC filing downloads and manual company fact ingestion"
Remove-Item Env:\QUANTAI_TEST_DATABASE_URL
```

## Primary references

- SEC public API formats: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC access guidelines: https://www.sec.gov/about/developer-resources
- Apple CIK evidence: https://www.sec.gov/Archives/edgar/data/320193/000032019323000020/0000320193-23-000020-index.htm
