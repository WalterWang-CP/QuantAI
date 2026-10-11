# Local inspection dashboard

This stage adds a read-only dashboard at http://127.0.0.1:8010/dashboard. It displays stored company data and captured SEC market-cap calculation evidence. It does not import data, normalize shares, create mappings, or calculate new snapshots. The real-data pilot remains pending.

## Files

Save these complete files at their exact project paths:

- app/main.py (replace)
- app/dashboard/__init__.py (new)
- app/dashboard/routes.py (new)
- app/dashboard/static/index.html (new)
- app/dashboard/static/dashboard.css (new)
- app/dashboard/static/dashboard.js (new)
- tests/test_dashboard.py (new)
- docs/INSPECTION_DASHBOARD.md (new)

There are no new Python runtime dependencies, no Node/npm setup, and no new database migration. The existing migration head remains a6d4e2c8f913. Browser assets are served by your existing FastAPI app, using relative same-origin URLs. The root JSON response and existing API routes remain available.

## Install and test

From C:\Users\wangz\Desktop\QuantAI with your virtual environment active, before copying the files:

```powershell
git status --short
git switch -c feature/inspection-dashboard
New-Item -ItemType Directory -Force app/dashboard/static | Out-Null
```

Save all eight files. __init__.py belongs in app/dashboard, not app/db/models. The new routes.py belongs in app/dashboard, not app/market_data.

Then:

```powershell
$env:QUANTAI_TEST_DATABASE_URL = python -c "from app.core.config import settings; print(settings.database_url)"
python -m pytest -q tests/test_dashboard.py
python -m pytest -q
```

Expected with PostgreSQL tests enabled: 28 targeted passed and 355 full-suite passed, assuming all preceding stage files are present. Existing dependency warnings may remain.

Local review: targeted 15 passed/13 PostgreSQL cases skipped; full suite 262 passed/93 PostgreSQL cases skipped. API tests cover asset delivery, bounded pagination, literal company search, company boundaries, decimal price text, date filters, archive download, and immutable snapshot inspection. DOM integration checked category navigation, price source selection, date filters, captured evidence, CSV download links, empty views, escaped company names, search, and late-response suppression. Full browser visual/layout verification was unavailable in the review environment; complete the manual check below on your computer.

## Open and inspect

Start or restart the server:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Open http://127.0.0.1:8010/dashboard. If you already have a server running in the terminal, stop it with Ctrl+C first, then start it again. Refresh the browser after saving all files.

1. Search for Apple and select the company. The selected company UUID appears under its name; company search matches literal text and does not interpret SQL wildcard characters.
2. Inspect Filings: confirm the imported SEC filings are visible. Click Inspect to see IDs, publication dates, and source artifact references.
3. Inspect Reviewed shares: accepted, excluded, and conflict candidates remain visible with reasons and rule versions. These are reviewed candidates, not a statement that a security/date winner has been selected.
4. Inspect Share mappings, Securities, and Listings: confirm the company/security/listing relationships and validity dates. An empty mapping tab is a pending mapping step, not a dashboard failure.
5. Inspect Prices: choose a listing, then explicitly choose the price source. Each source shows stored row count and first/last dates. Date range alone is not evidence of complete market-calendar coverage. Prices display exact database decimal strings, and sources are never merged.
6. Apply From/Through dates. Try an empty range and a reversed range to verify the messages. Previous/Next page through stored rows; there are 50 per record page, newest dates first where applicable.
7. Inspect Market-cap snapshots: click Inspect to read the stored calculation manifest. This fetches the captured inputs and result without recalculating. A CSV-backed snapshot provides a Download captured CSV link.
8. Inspect SEC archives, Raw facts, and CSV archives: metadata and IDs connect records to their original sources. Raw fact inspection includes the stored context. CSV archive inspection includes source declarations and downloads the captured bytes. SEC archive inspection shows metadata only, not the archived body.
9. Switch companies or categories while a request is loading. Older results must not replace the new selection. Refresh records clears the previous evidence selection and reloads listing choices; it resets the date filters.
10. Resize the page to a narrow window. The company picker moves above the workspace and tables scroll horizontally. Inspect buttons, tab buttons, search, and selects support keyboard navigation.

If no snapshots or CSV prices exist yet, those views should explicitly show no stored records. This does not complete the live-data pilot. No demonstration data is inserted into your database by the dashboard.

The Record evidence panel retains exact identifiers and captured fields for auditing. It is intentionally an inspection tool. Imports, evidence-backed mappings, and calculations stay in the existing APIs until a later UI controls stage.

## Commit after verification

```powershell
git add app/main.py app/dashboard/__init__.py app/dashboard/routes.py app/dashboard/static/index.html app/dashboard/static/dashboard.css app/dashboard/static/dashboard.js tests/test_dashboard.py docs/INSPECTION_DASHBOARD.md
git diff --cached --stat
git commit -m "Add read-only company data inspection dashboard"
Remove-Item Env:\QUANTAI_TEST_DATABASE_URL -ErrorAction SilentlyContinue
```

Next stage: CSV import and calculation controls in the dashboard, using the existing validation services. Then complete the real-data pilot before treating the data as validated. Statement normalization, scheduled coverage, historical universe validation, and reproducible dataset exports remain later Part One work. ML/backtesting is still deferred.
