# Raw historical price CSV pilot

This stage imports raw, unadjusted daily OHLC prices and volume from a UTF-8 CSV you already have. It retains the exact UTF-8 text received by the API, including BOM and line endings, in PostgreSQL. It does not fetch a vendor export or independently establish whether prices are unadjusted. Source and price-basis declarations are operator assertions.

## Install and verify

Save all eleven supplied files at their listed project paths. This stage depends on the preceding SEC share mapping and SEC market-cap files and migration 8c3f1a6e9b42. Do not delete earlier migrations.

From your active PowerShell virtual environment:

```powershell
git status --short
git switch -c feature/csv-price-ingestion
python -m alembic upgrade head
python -m alembic current
python -m alembic check
$env:QUANTAI_TEST_DATABASE_URL = python -c "from app.core.config import settings; print(settings.database_url)"
python -m pytest -q tests/test_csv_prices.py tests/test_database_migrations.py
python -m pytest -q
```

Expected migration head: a6d4e2c8f913. Expected targeted count: 44 passed with PostgreSQL enabled. Expected full count: 327 passed with PostgreSQL enabled, assuming all preceding stage files are installed. Existing dependency deprecation warnings may remain.

Local review: 34 targeted passed, 10 PostgreSQL cases skipped; migration upgrade/downgrade/schema comparison verified in SQLite. PostgreSQL and your live CSV import require your results.

## CSV format

Exactly these six columns, any order; header case/outer spaces tolerated:

```csv
date,open,high,low,close,volume
```

Rows require YYYY-MM-DD dates, positive unadjusted OHLC prices, consistent high/low bounds, and nonnegative integer volume. No adjusted-close columns, duplicate dates, or future dates. Prices have at most eight decimal places and sixteen integer digits; volume must fit a signed 64-bit integer. Maximum received size 2 MB and 20,000 rows. All dates must fall within the selected listing lifetime. The whole import is rejected if any row fails validation.

Use the actual ticker/currency of the listing. Do not declare adjusted data to be raw. If your export uses different column names, prepare a separate six-column UTF-8 file and explain the transformation in source_note. The archive is that submitted file, not the untouched vendor original.

## Live import

Start the server in another PowerShell terminal:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Find the correct listing UUID using GET /market-cap/securities/{security_id}/listings in http://127.0.0.1:8010/docs. A company UUID is not a listing UUID.

Edit every placeholder below. source_name is a stable lowercase name identifying this dataset; reuse it for corrections to that dataset. source_url must be the real source page, and source_note must explain the export, transformations, and evidence that prices are unadjusted.

```powershell
$listingId = "YOUR-LISTING-UUID"
$csvPath = "C:\Users\wangz\Desktop\YOUR-RAW-PRICE-FILE.csv"
$utf8 = [System.Text.UTF8Encoding]::new($false, $true)
$csvText = $utf8.GetString([System.IO.File]::ReadAllBytes($csvPath))
$priceRequest = @{
    csv_text = $csvText
    source_name = "historical_export"
    source_url = "https://YOUR-ACTUAL-SOURCE-PAGE"
    source_note = "REPLACE WITH YOUR ACTUAL EXPORT AND UNADJUSTED-PRICE EVIDENCE"
    symbol = "AAPL"
    currency_code = "USD"
    confirm_unadjusted_prices = $true
} | ConvertTo-Json -Depth 5
$import = Invoke-RestMethod -Uri "http://127.0.0.1:8010/market-data/listings/$listingId/daily/import-csv" -Method Post -ContentType "application/json" -Body ($utf8.GetBytes($priceRequest))
$import | Format-List
```

First import: created=true, rows_inserted matches your row count, rows_updated=0. Repeat the identical Invoke-RestMethod command: created=false and both changes=0. Save the returned source_id and csv_artifact_id.

GET /market-data/csv-artifacts/{csv_artifact_id} downloads the archived bytes. GET /market-data/listings/{listing_id}/price-sources lists available datasets. GET /market-data/listings/{listing_id}/daily/by-source?source_id=... reads this source explicitly (paginated, maximum 500 rows per request).

## Calculate with these prices

In Swagger POST /market-cap/listings/{listing_id}/reconstruct-sec, use the preceding stage's verified split-coverage evidence and add:

```json
"price_source_id": "SOURCE-UUID-RETURNED-BY-THE-CSV-IMPORT"
```

Keep the other required fields: valuation_date, confirm_split_coverage=true, split_evidence_url, and split_evidence_note. The valuation date must be covered by your eligible SEC shares, share mapping, listing lifetime, and price freshness limit. This pilot remains USD only. Raw-price confirmation does not establish split coverage: review the relevant interval separately.

Omitting price_source_id retains the previous Alpha Vantage default. Sources are never silently merged. The selected price's CSV archive ID, SHA-256, and source declaration are captured in the immutable calculation manifest. Stored CSV body integrity is checked before calculation. An exact repeated calculation returns the existing snapshot.

A changed file under the same source_name creates another archive and updates that source's overlapping daily bars. Earlier archives and market-cap snapshots remain. Re-importing an old archived file after its prices were corrected is rejected with 409; it cannot silently revert later corrections. Source note/evidence changes also create a distinct import. Partial files update only supplied dates.

This is a current-inventory reconstruction with public SEC availability cutoffs, not a frozen replay of which vendor prices were locally known on a historical date. It does not establish global coverage, independently validate source prices or split evidence, promote ranking snapshots, or finish Part One.

## Commit after checks pass

```powershell
git add app/db/models/csv_prices.py app/db/models/__init__.py migrations/env.py app/market_data/csv_service.py app/market_data/routes.py app/market_cap/price_service.py app/market_cap/sec_service.py migrations/versions/a6d4e2c8f913_add_csv_price_archives.py tests/test_csv_prices.py tests/test_database_migrations.py docs/CSV_PRICES.md
git diff --cached --stat
git commit -m "Add archived raw-price CSV ingestion for SEC market-cap pilot"
Remove-Item Env:\QUANTAI_TEST_DATABASE_URL -ErrorAction SilentlyContinue
```

Next: verify one real company end to end, then add a small inspection UI for filings, share mappings, imported prices, and calculation provenance. Extend statements, coverage scheduling, and historical universe/ranking validation after the pilot is inspectable.
