# SEC import and shares review in the dashboard

This stage adds two company-level controls to the existing dashboard: Import SEC filings and share facts, and Review SEC company-wide shares. Both call the existing backend services. There is no new API route, runtime dependency, or database migration. Existing CSV import and market-cap controls remain available.

## Install and test

Start from the completed dashboard-actions stage. If that stage is not committed yet, use its supplied Git commands first. In the QuantAI PowerShell terminal:

```powershell
git status --short
git switch -c feature/dashboard-sec-workflow
```

Replace these three files:

- app/dashboard/static/index.html
- app/dashboard/static/dashboard.css
- app/dashboard/static/dashboard.js

Add these two files:

- tests/test_dashboard_sec.py
- docs/SEC_DASHBOARD.md

Save whole files at the exact paths. The page needs all three new assets; do not mix old HTML with the new JavaScript. app/main.py and app/dashboard/routes.py do not change. Migration head remains a6d4e2c8f913.

Run:

```powershell
$env:QUANTAI_TEST_DATABASE_URL = python -c "from app.core.config import settings; print(settings.database_url)"
python -m pytest -q tests/test_dashboard.py tests/test_dashboard_actions.py tests/test_dashboard_sec.py
python -m pytest -q
```

Expected with PostgreSQL enabled: 43 targeted passed and 370 full-suite passed. Existing dependency warnings may remain.

Local review: 30 targeted passed/13 PostgreSQL cases skipped; full suite 277 passed/93 PostgreSQL cases skipped. New HTTP integration checks use synthetic SEC responses with real local archive/review storage. They cover company-specific CIK choices, exact-repeat import/review behavior, rejected dates and missing registrations before network access, incomplete metadata-history warnings, rate-limit errors with no partial archive, and a truthful zero-fact review.

DOM integration checked registered CIK selection, operation availability without a listing, invalid ranges, duplicate-submit guards, explicit normalization, incomplete-history warnings, repeat receipts, network/rate-limit errors, no automatic UI retries, stale identity-response suppression, and calculation-preview invalidation on SEC write attempts. Full visual/browser verification remains on your computer. Tests do not insert fixtures into your real database or fetch live SEC data.

## Open the dashboard

Restart the server or start it if stopped:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Open http://127.0.0.1:8010/dashboard and press Ctrl+F5. Select Apple or another existing company. The two new panels work at company level, even when no listing exists.

## Import SEC data

1. Expand Import SEC filings and share facts.
2. Select a registered CIK. A single registration is selected automatically; multiple registrations require an explicit choice. The options show identifier validity dates. The server verifies the registration covers the requested import range and rejects identity conflicts.
3. Enter optional Filed date from/through limits. These filter filing dates, not financial observation/report dates. For your earlier Apple pilot, you can reuse 2019-01-01 through 2025-12-31.
4. Keep Follow older submissions metadata archives checked when you want the importer to follow relevant older metadata files. Unchecking it can produce an incomplete-history receipt with warnings.
5. Click Import SEC data once. Company/listing/source selectors and write forms stay locked while the request is pending. Older metadata downloads can take time. The UI does not automatically retry a write.
6. Read the receipt: status, filings/facts inserted, existing/rejected facts, original-response archives inserted, metadata-history status, and warnings. Expand SEC import receipt for the complete response.
7. Inspect Filings, Raw facts, and SEC archives. The current record tab reloads after a successful import. Importing does not automatically normalize shares, create securities/listings, create a share-scope mapping, or calculate market cap.

This pilot uses the existing backend's default periodic forms and company-wide shares tags. It does not import all statement concepts or establish complete historical shares/price coverage. A completed metadata-history flag describes this import request, not a completed live-data pilot.

An unchanged response/input repeat should add no duplicate filings/facts. New SEC response bytes can create another archive, and newly published or revised data can produce new fact versions. Review the actual receipt rather than assuming every later request must have zero changes.

If there is no registered CIK, the import form stays disabled with an explanation. Register the correct company identifier through POST /identity-resolution/company-identifiers in Swagger, using verified identity/validity information. This UI does not infer an identifier from the company name or ticker. Keep the SEC_USER_AGENT configuration from the earlier SEC import stage; configuration/provider errors appear in the receipt status area. You do not need to share your .env file.

## Review shares explicitly

1. Expand Review SEC company-wide shares.
2. Click Review SEC share facts.
3. Read facts reviewed, accepted/excluded/conflicting counts, reviews inserted/updated, and rule version. A company with no applicable facts returns a zero-fact receipt; the page does not manufacture data.
4. Open Reviewed shares and click Inspect on a row to see its observation/known dates, status/reason, raw-fact reference, and rule version.
5. Repeating an unchanged review should insert/update zero reviews. New facts or changed conflicts can change review decisions on a later run. The original raw facts remain intact and previously saved market-cap snapshots retain their captured manifests.

Reviewed candidates are not a security/date winner. A verified company-wide shares mapping to the appropriate common security is still required by SEC share selection. This stage does not create that mapping. Review dates/statuses and resolve mapping prerequisites before calculating.

A SEC import or share-review attempt invalidates any calculation preview and unchecks split confirmation, including when the outcome is uncertain. Check eligible inputs again before saving a market-cap snapshot. These operations do not calculate anything automatically.

## Errors and manual checks

- Try a reversed filing-date range: it must show an error without submitting an import.
- A company without a registered CIK should have a disabled SEC import form, while its review button remains available.
- During an import or review, repeated clicks must not submit another write or change the company selection.
- A provider rejection should display its error and unlock the controls, with no successful receipt shown.
- On a lost response/network failure, inspect the stored filings/facts or reviews before retrying. A missing response does not establish that the write failed.
- Switching companies clears SEC forms/receipts and loads the new company's CIKs. Switching listings retains company-level SEC fields and receipts.
- Check expanded panels in a narrow browser window and keyboard navigation.

The real-data pilot remains pending until an actual evidence-backed price/share calculation and its captured inputs have been reviewed. A successful import or normalization receipt alone does not complete it.

## Commit after verification

```powershell
git add app/dashboard/static/index.html app/dashboard/static/dashboard.css app/dashboard/static/dashboard.js tests/test_dashboard_sec.py docs/SEC_DASHBOARD.md
git diff --cached --stat
git commit -m "Add dashboard SEC import and audited share review controls"
Remove-Item Env:\QUANTAI_TEST_DATABASE_URL -ErrorAction SilentlyContinue
```

Next stage: an evidence-backed share-scope mapping form, followed by real pilot validation. Financial-statement normalization, scheduled coverage, historical universe/ranking validation, and reproducible dataset exports remain later Part One work. ML/backtesting stays deferred.
