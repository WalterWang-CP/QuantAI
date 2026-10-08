# QuantAI data-source and completion plan

Reviewed 2026-10-08. This is a development proposal, not a purchased-data decision.
The last user-verified stage has 117 passing tests, including PostgreSQL migrations
and concurrency tests. GitHub Actions execution has not yet been verified.

## Product goal

Keep the configurable policy: yearly global Top 1,000; ever-Top-100 companies get
up to 20 years of historical reconstruction; continue tracking dropouts for five
years. A small US pilot validates the implementation, but does not satisfy global
coverage. Part Two ML, backtesting, and trading remains deferred.

## What the current code actually supports

| Area | Present foundation | Remaining work |
| --- | --- | --- |
| Provider registry | Alpha Vantage TIME_SERIES_DAILY scheduled importer | Company-scoped datasets and additional importers |
| Identity | Company, security, listing, identifiers, lifecycle events | Historical candidate discovery and automated reconciliation |
| Prices | Raw daily bars, archives, quality issues, coverage checks | Wider provider coverage and non-US calendars |
| Shares | Manual observations with observation/known dates | Filing provenance, class-aware mapping, immutable revisions |
| Corporate actions | Splits/dividends and adjustments | Scheduled ingestion and lifecycle coverage |
| FX | Observation storage and valuation lookup | Historical automatic import and currency-unit checks |
| Market cap | Split-aware reconstruction | Share-class aggregation, ADR ratios, stale-input policy |
| Rankings | Reconstructed/manual snapshots and approval | Historically complete candidate pools and coverage reports |
| Tracking/retrieval | Policy decisions, input fingerprints, retries, quota locks | Dataset-specific coverage, orchestration, operational visibility |
| Financial statements | No complete statement ingestion pipeline | Raw facts, filing versions, normalized statement views |
| Website | API documentation | User-facing dashboard and inspection flows |

## Source assessment

These are documented capabilities, not a guarantee for every company, exchange,
subscription, or historical date. Actual samples must establish usable coverage.

| Source | Proposed role | Documented limit or unresolved issue |
| --- | --- | --- |
| Alpha Vantage | Keep existing price importer; evaluate listing discovery | Daily compact is latest 100 points; full history requires premium access. US listing-status date lookup supports dates after 2010-01-01. That leaves early years of a 20-year universe unresolved. |
| SEC EDGAR | First new adapter: filing metadata and company facts | Public APIs need no API key. XBRL was first required in 2009; aggregated APIs exclude custom-taxonomy and non-entity-wide facts. Earlier and class-specific data need filing-level work. |
| EODHD | Evaluate global price/fundamental and delisted coverage | Historical equity market cap is US NYSE/NASDAQ only, weekly from 2021-07-09. Delisted non-US prices are documented as mostly the latest 6-7 years. It cannot by itself establish the full target universe. |
| FMP | Alternative vendor sample for statements, market cap, and identity | Documentation lists relevant endpoints; per-market history, restatement behavior, historical identity, and plan access still need validation. |

Do not subscribe based on an advertised endpoint alone. Compare actual examples,
oldest usable dates, historical identity coverage, and usable filing versions.

## Immediate implementation sequence

### 1. Filing provenance and version storage

Add filing records and raw fact records before inserting SEC facts into the shares
table. Store company/CIK, accession number, form, report period, filing date,
acceptance timestamp when available, source URL, archived response, ingestion time,
taxonomy, tag, unit, period start/end, value, and normalization status. An amended
filing becomes another version. Re-importing the same source fact is idempotent.
Unknown availability stays unknown. A report-period end is never substituted for
a public filing date. If only a filing date is known, timestamp-sensitive exports
must apply a documented conservative rule rather than inventing an exact time.

Deliverable: model/schema/migration plus tests preserving repeated and revised facts.

### 2. SEC submissions and company-facts adapter

Configure an identifying User-Agent supplied locally by the user, explicit timeout,
shared request-rate control, caching, retries, and raw archiving. Start conservatively
below the SEC's documented 10 requests/second maximum. Follow older submissions
files when needed. Resolve by CIK rather than assuming a current ticker is a permanent
company identity. The current retrieval importer is listing-scoped; add a separate
company-scoped job path or generalize targets with backwards-compatible migration
and tests before scheduling SEC jobs through it.

Deliverable: fetch/parse/import endpoints, deterministic fixtures, and optional live smoke run.

### 3. Normalize suitable share facts

Use dated outstanding-share counts suitable for valuation. Weighted-average basic
or diluted EPS denominators are a different measurement and must not be silently
used as instantaneous shares outstanding. Preserve conflicting tags, units, filing
versions, and unresolved class scope for review. Only unambiguous facts feed the
existing shares/market-cap pipeline. Replay must exclude later-filed revisions at
an earlier as-of cutoff.

Deliverable: audited raw-to-normalized mapping and replay tests.

### 4. Small real-data pilot and first UI

Proposed pilot: approximately ten SEC-filing companies, starting with single-class
cases, then a multi-class issuer, a split, and a delisted/renamed issuer. Examine
2019-2025 filings, plus recent price coverage available with the user's current
access. Older price reconstruction requires an available historical provider or
explicit source-backed manual input; compact prices cannot cover those years.

For each company report requested range, actual range, missing facts, date certainty,
identity conflicts, raw sources, and reconstruction readiness. Do not label this
sample a global ranking. Validate at least one archived import, repeated import,
revision replay, split reconstruction, missing-input case, and identity conflict.

Build an early website once these flows work: dashboard, companies, source inspection,
ingestion status, retrieval jobs, and coverage. Keep the UI useful during later expansion.

## Remaining stages to Part One completion

| Order | Stage | Completion evidence |
| --- | --- | --- |
| 5 | Normalize income, balance-sheet, and cash-flow facts | Period/unit/context mappings; annual/quarterly separation; amendment replay |
| 6 | Add required provider datasets and worker orchestration | Dataset-specific jobs, quota policy, retries, resume, coverage outcomes |
| 7 | Validate historical global source coverage | Market-by-market and year-by-year sample report; explicit unsupported cells |
| 8 | Build candidate universe and identity history | Listed and delisted candidates at each cutoff; reviewed corporate transitions |
| 9 | Complete global valuation | Calendars, FX, quote units, share classes, ADR ratios, stale-input controls |
| 10 | Generate historical company rankings | Candidate completeness evidence; one company per rank; dated inputs and approval |
| 11 | Apply tracking policies and expand Layer 1 | Top-N, elite backfill, dropout intervals; preserved missing/incomplete outcomes |
| 12 | Complete Layer 1 website | End-to-end configuration, ingestion, inspection, ranking, tracking, job and coverage flows |
| 13 | Versioned dataset manifests and exports | Reproducible as-of selection, input identity, provenance, quality and coverage summaries |
| 14 | Layer 2 filing/document context | Source-linked text, versioned extraction, grounded summaries and review UI |
| 15 | Operational release | Installation, migration/backup/restore checks, CI run, monitoring, tested restart/recovery |

Completion means a working presentable application, reproducible data exports,
source-linked context, and measured coverage matching the agreed scope. Any
unresolved global historical coverage prevents claiming the full global goal is
complete. Scope changes require the user's decision, not silent relabeling.

## Git workflow

Use one branch per stage. Deliver exact file destinations, migrations when required,
and test commands. Review the staged diff and commit after local checks pass.
Push/merge when the user chooses, and inspect the CI result. Keep source credentials
and fetched private/licensed datasets out of Git. No functional code changes are
included in this planning stage, so no test rerun is required for this document.

## Primary references

- Alpha Vantage: https://www.alphavantage.co/documentation/
- SEC data APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC developer guidance: https://www.sec.gov/about/developer-resources
- EODHD market cap: https://eodhd.com/financial-apis/historical-market-capitalization-api
- EODHD delisted prices: https://eodhd.com/financial-academy/financial-faq/historical-stock-prices-for-delisted-companies
- FMP endpoint catalogue: https://site.financialmodelingprep.com/developer/docs

Provider capabilities must be rechecked before a purchase or major backfill.
