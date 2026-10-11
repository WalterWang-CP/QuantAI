# Dashboard CSV import and SEC calculation controls

This stage adds explicit CSV import and SEC market-cap forms to the existing local dashboard. It uses the existing write APIs, schema validation, transaction handling, and immutable archives/snapshots. There is no new backend route, database migration, Python dependency, Node setup, or paid provider requirement.

The live-data pilot remains pending until a real import and evidence-backed calculation are reviewed. Tests use synthetic fixtures; the dashboard does not create demonstration data in your database.

## Install

Start from your committed inspection-dashboard stage. In your QuantAI PowerShell terminal:

```powershell
git status --short
git switch -c feature/dashboard-actions
```

Replace these five files:

- app/dashboard/static/index.html
- app/dashboard/static/dashboard.css
- app/dashboard/static/dashboard.js
- tests/test_dashboard.py
- docs/INSPECTION_DASHBOARD.md

Add these two files:

- tests/test_dashboard_actions.py
- docs/DASHBOARD_ACTIONS.md

Save the whole contents at those exact paths. HTML, CSS, and JavaScript are all needed; an old asset can break the new controls. app/main.py and app/dashboard/routes.py do not change. Database head remains a6d4e2c8f913.

## Test

```powershell
$env:QUANTAI_TEST_DATABASE_URL = python -c "from app.core.config import settings; print(settings.database_url)"
python -m pytest -q tests/test_dashboard.py tests/test_dashboard_actions.py
python -m pytest -q
```

Expected with PostgreSQL enabled: 36 targeted passed; 363 full-suite passed. Existing dependency warnings may remain.

Local review: 23 targeted passed/13 PostgreSQL cases skipped; full suite 270 passed/93 PostgreSQL cases skipped. HTTP checks cover exact UTF-8 archives and SHA-256, import repeat/correction behavior, validation failures with no partial rows, explicit CSV source selection, selected-shares preview, calculation repeat, captured snapshot inspection, and missing mappings/stale prices.

DOM integration used real local HTTP APIs with synthetic data. It checked confirmations, duplicate submission guards, company/selection locking during writes, BOM/CRLF preservation, preview interval, preview invalidation, invalid UTF-8 and oversize files, displayed backend errors, stored result and repeat, archive links, and selection reset. The file-picker boundary was simulated because the DOM test environment does not implement the browser file picker. Full visual/browser verification remains the manual check below.

## Open

Restart your server, or start it if it is stopped:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Open http://127.0.0.1:8010/dashboard. Use Ctrl+F5 to reload all browser assets after replacing them.

Select a company. The listing and price-source controls now stay above the record tabs. Expand either operation panel. Changing company or listing clears the operation forms and receipts; refreshing records also resets them. Browsing record tabs does not submit anything.

## Import a real CSV

1. Select the correct listing. Its ticker and currency populate the import form and cannot be edited there. Select another listing if either is wrong.
2. Expand Import a raw-price CSV and choose a nonempty UTF-8 CSV no larger than 2 MB. Its six columns must be date,open,high,low,close,volume. Backend validation still enforces up to 20,000 rows, valid dates within listing lifetime, unadjusted OHLC schema, consistent high/low, numeric precision, nonnegative integer volume, and no duplicate or future dates.
3. Enter a stable lowercase source name such as historical_export. Reuse that name for later exports or corrections from the same dataset. Use the actual source URL and explain the export, any transformations, and evidence for unadjusted prices in the note (20–2000 characters). Do not use fixture evidence for real records.
4. Confirm that prices are unadjusted. This records your declaration; it does not independently establish the vendor's price basis.
5. Click Import prices. The forms and company/listing/source selectors are locked while the write is pending. There are no automatic retries.
6. Read the receipt: rows inserted/updated, source ID, artifact IDs, dates, and SHA-256. The dashboard selects the returned source for viewing and calculation after success. Download captured CSV returns the archived bytes. The browser decoder rejects invalid UTF-8 and preserves BOM and line endings in a valid UTF-8 file.
7. Repeating the identical file and declaration should say the import already exists with no changed prices. A changed file creates another archive and updates only supplied dates in that named source. Previous archives/snapshots remain. An old-file repeat that would revert corrected prices is rejected with 409.

A rejected import shows the server's error and keeps the form available for correction. If a network failure makes the outcome uncertain, inspect stored archives/rows before retrying; do not assume the write failed just because its response was lost.

## Save a market-cap snapshot

Prerequisites: SEC filings have been imported, shares normalized, and an evidence-backed single-common-class share mapping exists for the security and relevant period. USD listing prices and split records/evidence must also be available. This stage does not create those mappings, import SEC filings, or retrieve corporate actions.

1. Select a USD listing and explicitly choose a supported raw-price source: CSV RAW_DAILY_CSV or Alpha Vantage TIME_SERIES_DAILY. Sources are not silently merged and the calculator never falls back to another source.
2. Expand Save an SEC market-cap snapshot. Enter the valuation date and age limits (defaults: shares 400 days, price 7 days).
3. Click Check eligible inputs. This read-only preview uses the existing selected-shares API and the latest selected-source price on or before the valuation date. It displays the share observation/known dates, exact share count, price date/close, and the share-to-price split-check interval. Missing mappings, unreviewed/conflicting facts, or unavailable/stale prices show an error. Preview does not independently validate split coverage, archive integrity, or all final-calculation constraints.
4. Review real split-coverage evidence for the displayed interval, enter its URL and explanation (20–2000 characters), and explicitly confirm coverage. Your assertion is recorded with independently_verified=false; it does not import missing split rows. If a split exists in the interval, store its correct factor through the existing corporate-action API before saving.
5. Click Save market-cap snapshot. The backend selects and validates inputs again, applies stored split factors, checks price/archive conditions, and captures the actual inputs used. The preview is a guide, not a frozen input reservation. Review the saved interval/input dates if data changed between preview and save.
6. The result shows market cap in USD and whether a new snapshot was saved or an identical snapshot already existed. Expand Captured calculation evidence for its manifest. Inspect saved snapshot reads the stored record in the existing evidence panel. A CSV-backed result also offers Download captured CSV.
7. Changing listing, price source, valuation date, or age limits invalidates the preview and unchecks split confirmation. Check eligible inputs again before saving. Missing evidence blocks submission. A backend rejection creates no successful result receipt.

Saving a snapshot does not approve a ranking, establish historical completeness, freeze what vendor prices were locally known on the valuation date, or finish the live-data pilot.

## Manual verification

- Confirm both forms appear and ticker/currency match the selected listing.
- Select an actual CSV, but leave confirmation unchecked: no import should submit.
- Verify the chosen CSV import and its exact-repeat receipt, then inspect its Prices and CSV archives tabs.
- In the calculator, change a date after preview: the save button must disable and split confirmation clear.
- Check a date without eligible shares/prices: the error must be visible and no snapshot created.
- Complete a real evidence-backed calculation only once its prerequisites are verified. Inspect its captured source, dates, share count, split inputs, USD result, and archive reference.
- Repeating unchanged inputs should reuse the snapshot.
- Check the expanded panels in a narrow browser window and keyboard navigation through fields/buttons.

If prerequisites or real data are not ready, verify the page and its error behavior and leave the live pilot pending. Do not manufacture a share mapping or evidence solely to obtain a successful result.

## Commit

After tests and the UI check pass:

```powershell
git add app/dashboard/static/index.html app/dashboard/static/dashboard.css app/dashboard/static/dashboard.js tests/test_dashboard.py tests/test_dashboard_actions.py docs/INSPECTION_DASHBOARD.md docs/DASHBOARD_ACTIONS.md
git diff --cached --stat
git commit -m "Add dashboard CSV import and SEC market-cap controls"
Remove-Item Env:\QUANTAI_TEST_DATABASE_URL -ErrorAction SilentlyContinue
```

Next: improve SEC import/normalization and evidence-backed mapping workflows in the UI so a real pilot is easier to complete. After real validation, continue to financial-statement normalization, coverage scheduling, historical universe/ranking validation, and reproducible dataset exports. ML/backtesting remains deferred.
