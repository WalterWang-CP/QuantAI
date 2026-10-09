# SEC shares normalization review

This stage reviews imported SEC share facts in a separate `normalized_share_facts` table. It does not populate market-cap inputs or assert that company-wide shares belong to a particular security. Original facts, archives, and existing shares observations stay unchanged.

## Install and test

Stop Uvicorn with Ctrl+C. Save all nine supplied files to their matching project paths, then run:

```powershell
python -m alembic upgrade head
python -m alembic current
python -m alembic check
$env:QUANTAI_TEST_DATABASE_URL = python -c "from app.core.config import settings; print(settings.database_url)"
python -m pytest -q tests/test_share_normalization.py tests/test_database_migrations.py
python -m pytest -q
```

Expected revision: `4e9a2b7c1d63 (head)`. Expected schema check: `No new upgrade operations detected.` With PostgreSQL enabled, expect 39 targeted tests and 239 full-suite tests. Local verification without PostgreSQL: 190 passed, 49 skipped; SQLite migration round trip and schema checks passed. Do not downgrade your real database as a test.

## Apple smoke test

Start:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Open http://127.0.0.1:8010/docs. Under Filings select POST `/filings/companies/{company_id}/normalize-shares`, click Try it out, and enter `9a4e920d-3bf7-440a-8f79-5a3a853d1b05`. No request body is needed. Click Execute.

The response reports facts_reviewed, reviews_inserted, reviews_updated, accepted, excluded, and conflicts. These three decision counts must sum to facts_reviewed. Do not assume all 84 imported facts will be accepted. Repeat the normalization: if input facts and filing metadata are unchanged, reviews_inserted and reviews_updated must both be zero.

Then GET `/filings/companies/{company_id}/normalized-shares` with the same UUID. Leave as_of empty to see every review, including exclusions and conflicts. Each review has raw_fact_id, observation_date, known_date, shares_outstanding, status, and reason. Follow raw_fact_id through the existing filing facts API to its filing and source artifact.

Providing as_of returns accepted candidates with known_date and observation_date on or before that date. It returns all eligible filing versions; it does not select a winning revision or source. These are current review decisions, not frozen historical dataset versions. Re-reviewing contradictory newly downloaded data can change an old candidate's decision. Dataset manifests and revision selection are later stages.

## Rules and limits

- Only SEC source facts with dei/EntityCommonStockSharesOutstanding or us-gaap/CommonStockSharesOutstanding are reviewed. Weighted-average EPS share denominators are left for other normalization rules.
- Only shares units, instant periods, supported periodic forms, and explicitly entity-scoped contexts are eligible. Unknown dimensions/scope are excluded.
- Counts must be positive whole numbers below 10^26; fractional shares are excluded under this initial conservative rule. Exact decimal text is used for storage, avoiding SQLite numeric rounding.
- known_date is the next day after the later of filed_date and the UTC acceptance date. Missing both excludes the fact. This is conservative daily availability, not intraday availability.
- Distinct values for the same filing and observation date are all marked conflict, including previously accepted rows. Equivalent contexts and two recognized tags reporting the same count can each retain their own source links.
- Amendments retain separate candidates and publication dates. A later stage must choose revisions explicitly.
- Normalization and SEC import serialize their writes using the company row lock on PostgreSQL.
- Company-wide entity scope does not establish a single share class, ADR ratio, listing, or security. No market-cap calculation consumes these candidates yet.

## Git checkpoint

```powershell
git add app/db/models/share_normalization.py app/db/models/__init__.py migrations/env.py app/filings/share_normalization.py app/filings/routes.py migrations/versions/4e9a2b7c1d63_add_share_normalization.py tests/test_share_normalization.py tests/test_database_migrations.py docs/SEC_SHARE_NORMALIZATION.md
git diff --cached --stat
git commit -m "Add audited SEC company-wide shares normalization"
Remove-Item Env:\QUANTAI_TEST_DATABASE_URL -ErrorAction SilentlyContinue
```

The next stage adds explicit security mapping and revision selection before connecting reviewed candidates to market-cap reconstruction.
