# SEC-based USD market-cap reconstruction

This stage connects selected, mapped SEC shares to stored raw daily closes and split adjustments. It saves versioned calculations with captured input manifests in sec_market_cap_snapshots. Earlier snapshots and legacy market_cap_observations remain unchanged. These pilot snapshots are not automatically approved ranking inputs.

## Install and test

Stop Uvicorn. Save all nine supplied files at the exact matching paths.

```powershell
python -m alembic heads
python -m alembic upgrade head
python -m alembic current
python -m alembic check
$env:QUANTAI_TEST_DATABASE_URL = python -c "from app.core.config import settings; print(settings.database_url)"
python -m pytest -q tests/test_sec_market_cap.py tests/test_database_migrations.py
python -m pytest -q
```

Expected head: 8c3f1a6e9b42. Expected schema check: No new upgrade operations detected. With PostgreSQL enabled: 31 targeted tests, 293 full-suite tests. Local validation: 221 passed, 72 PostgreSQL tests skipped; SQLite migration schema checks and round trip passed. Existing deprecation warnings remain.

## Required inputs for the live test

You need the previous stage's Apple common_stock security UUID, an evidence-backed share-scope mapping covering your selected observation and valuation date, normalization reviews, a USD listing, raw daily price data with an archive record, and reviewed split coverage. Company UUID: 9a4e920d-3bf7-440a-8f79-5a3a853d1b05.

Start:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Open http://127.0.0.1:8010/docs.

1. Under Filings, GET /filings/companies/{company_id}/securities to find Apple's common-stock security UUID. Use the previous stage's guide if the security/mapping does not yet exist.
2. Under Market Cap, GET /market-cap/securities/{security_id}/listings. Reuse the correct listing. If none exists, POST /identity/listings with the example below; replace security_id with the actual common-stock UUID. This bounds the pilot listing period rather than claiming a verified full listing history.

```json
{
  "security_id": "PASTE_APPLE_COMMON_STOCK_UUID",
  "ticker": "AAPL",
  "exchange_code": "NASDAQ",
  "currency_code": "USD",
  "start_date": "2019-01-01",
  "end_date": null,
  "is_primary": true
}
```

3. Use the existing daily-price read endpoint under Market Data to inspect the listing's available trading dates. If prices are missing, POST /market-data/listings/{listing_id}/daily/import using your configured provider. Check its status and returned date coverage. Requesting full_history does not guarantee provider entitlement or historical coverage. Use an available date covered by your share mapping. If the required historical price is unavailable, send the import response and coverage before buying data; a documented CSV ingestion path is planned next.
4. Under Filings, GET /filings/securities/{security_id}/selected-shares using the intended valuation_date. Resolve a missing mapping, unreviewed fact, conflict, or stale observation before reconstruction.
5. Review split evidence for the interval between selected shares observation_date and selected price trading_date. If no split occurred, record that evidence rather than treating an empty table as proof. If splits occurred, import their factors using the existing corporate-action workflow. Duplicate equal factors on one date are counted once; different factors on the same date block calculation.

## Calculate

Under Market Cap, POST /market-cap/listings/{listing_id}/reconstruct-sec. Use the listing UUID and fill this JSON with actual evidence:

```json
{
  "valuation_date": "2025-12-31",
  "max_share_age_days": 400,
  "max_price_age_days": 7,
  "confirm_split_coverage": true,
  "split_evidence_url": "PASTE_REVIEWED_SPLIT_HISTORY_OR_FILING_URL",
  "split_evidence_note": "Describe the reviewed split history and whether any splits occurred between the share observation and the selected raw price date."
}
```

Change valuation_date if necessary to a date supported by your price data and mapping. The API records the coverage assertion but does not independently fetch and validate that URL. Do not confirm coverage without reviewing it.

The response contains snapshot_id, created, input_hash, and manifest. In manifest inspect:

- shares_selection: original shares count, observation_date, known_date, normalized/raw fact IDs, filing and mapping IDs.
- shares_fact: raw fact hash and filing archive SHA-256 references.
- mapping: bounded validity period and original evidence.
- price: actual raw close, trading date, source, ingestion run, and archive reference.
- splits: effective dates, factors, sources, and ingestion runs used.
- split_coverage: operator assertion, independently_verified=false, and the actual adjustment interval.
- fx: USD to USD rate 1; non-USD listings are refused in this pilot.
- result: shares_on_price_date, local_market_cap, market_cap_usd, serialized as exact decimal strings.

Market cap = raw close multiplied by shares adjusted to the raw close's split basis. Splits effective on the observation or price date are treated as already reflected in that date's input. Calculations use decimal precision 80. Prices come from the existing alpha_vantage/TIME_SERIES_DAILY raw-close source. Other providers and explicit non-USD FX selection are subsequent work.

The captured input manifest records the values used and archive references. The API checks that the price archive record belongs to the price's listing/source, but does not reread its local file or reparse its contents. Source record corrections can change the current calculation; old manifests remain available.

## Repeat and inspect versions

Repeat the same POST. Unchanged inputs and evidence should return the same snapshot_id and input_hash with created=false. New or corrected inputs/evidence produce a new version rather than overwriting the earlier calculation.

GET /market-cap/listings/{listing_id}/sec-snapshots lists the versions and their input manifests. This endpoint has limit/offset pagination.

404: listing or required price/shares/mapping missing. 409: non-USD listing, stale price/shares, invalid listing/mapping period, missing/mismatched price archive, conflicting share/split input, or another blocked prerequisite. 422: invalid request schema, including missing split confirmation/evidence.

This reconstructs historical economic/publication dates from the current stored source inventory. It does not prove complete historical universe coverage, original provider publication timestamps for prices/actions, frozen past database contents, or readiness for global rankings. Snapshot storage supplies a concrete audit trail for the pilot calculation.

## Git checkpoint

After tests and the live check:

```powershell
git add app/db/models/sec_market_cap.py app/db/models/__init__.py migrations/env.py app/market_cap/sec_service.py app/market_cap/routes.py migrations/versions/8c3f1a6e9b42_add_sec_market_cap_snapshots.py tests/test_sec_market_cap.py tests/test_database_migrations.py docs/SEC_MARKET_CAP.md
git diff --cached --stat
git commit -m "Add versioned USD market-cap reconstruction from SEC shares"
Remove-Item Env:\QUANTAI_TEST_DATABASE_URL -ErrorAction SilentlyContinue
```

Next: complete the real-data pilot (including a provider-independent CSV input path if needed), then add the early website UI to inspect imports, review decisions, mappings, and calculation provenance.
