# Evidence-backed share mapping in the dashboard

This stage adds a company-level form mapping company-wide SEC shares to an existing common-stock security for a bounded interval. It calls the existing share-scope API and preserves its validation. It does not create securities, infer share classes, edit mappings, or calculate market cap automatically.

## Install

Start from the completed dashboard SEC workflow stage. Commit that stage first if you have not already done so.

```powershell
git status --short
git switch -c feature/dashboard-share-mapping
```

Replace:

- app/dashboard/static/index.html
- app/dashboard/static/dashboard.js

Add:

- tests/test_dashboard_mapping.py
- docs/DASHBOARD_SHARE_MAPPING.md

Save whole files at those exact paths. Your existing dashboard.css is reused. No main.py, backend route, dependency, or migration changes are required. Database head remains a6d4e2c8f913.

## Tests

```powershell
$env:QUANTAI_TEST_DATABASE_URL = python -c "from app.core.config import settings; print(settings.database_url)"
python -m pytest -q tests/test_dashboard.py tests/test_dashboard_actions.py tests/test_dashboard_sec.py tests/test_dashboard_mapping.py
python -m pytest -q
```

Expected with PostgreSQL enabled: 52 targeted passed and 379 full-suite passed. Existing dependency warnings may remain.

Local review: nine new mapping HTTP tests passed. Full suite: 286 passed/93 PostgreSQL cases skipped. HTTP integration verifies saving and exact repeat, scoped inspection, eligible share selection, overlap rejection without overwriting evidence, foreign-company security rejection, unsupported ADRs/overlapping securities, invalid dates, explicit confirmation, and security lifetime limits.

DOM checks use synthetic API responses and cover common-stock filtering, multiple-security explicit choice, operation without a listing, confirmation, date/lifetime validation, duplicate guards, save/repeat receipts, server conflict display, calculation-preview invalidation, and stale-response suppression. These checks do not establish the truth of real share-class evidence. Visual/browser verification remains on your computer.

## Use the form

Restart the server if needed:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Open http://127.0.0.1:8010/dashboard and press Ctrl+F5.

1. Select a company and expand Map company-wide shares to a security.
2. Choose an existing common_stock security. The dropdown is scoped to the selected company and loads all security pages. Multiple options require an explicit choice. A single option is selected automatically, but still requires your evidence and confirmation. ADRs and other security types are excluded from choices.
3. Enter Valid from and Valid through dates covering the interval established by your evidence. Both bounds are required. The interval must fit the security lifetime; do not use a guessed start date merely to cover your entire dataset.
4. Enter Evidence publicly known on: the actual public availability date of the mapping evidence. It must be on or after Valid from. This is not the date you run the software or a date to invent for historical eligibility. Selection requires the known date to be on or before the valuation date. Evidence published later can therefore prevent earlier calculations even if the mapping interval includes them.
5. Enter the actual share-class evidence URL and a 20–2000 character explanation identifying the security, the one-common-class basis, and the complete validity interval. Current class information alone does not establish a decades-long historical interval.
6. Confirm that company-wide shares correspond to this single common-share class throughout the interval. The confirmation is an operator assertion; the backend does not independently read or verify your source page. Stored identity data also cannot prove that an unrecorded second class never existed.
7. Click Save share mapping. The server verifies company ownership, common-stock type, lifetime, other securities overlapping the interval, and existing mappings. All write forms/company selection are locked while the request is pending.
8. Read Mapping available and its UUID, then expand Saved mapping evidence. The response has no created flag, so this receipt does not claim whether the row was newly inserted. An exact repeat of every field returns the same mapping ID.
9. Open Share mappings and Inspect the stored row. Existing evidence is never overwritten: changed evidence/dates overlapping an existing interval return 409. The form provides no edit/delete controls. Use a separately reviewed correction workflow if historical mapping evidence needs correction.

Changing security, dates, evidence URL, or note unchecks confirmation. Switching listings retains company-level mapping fields/receipt; switching companies or refreshing records clears them and loads new choices. A write attempt invalidates the market-cap input preview and split confirmation, including when its outcome is uncertain.

If there is no common-stock security, the form is disabled with an explanation. Create the verified company/security identity through the existing identity API first. A filing import does not create that identity. This pilot also rejects other overlapping securities, including other types; selecting one dropdown option does not bypass that policy.

## Check calculation eligibility

After a valid mapping exists, review SEC share facts if needed, select a USD listing and raw-price source, and use Check eligible inputs in the calculator. The existing selector checks the mapping's known date/validity alongside the SEC fact's observation/publication dates. Mapping alone does not provide shares, prices, split coverage, or a validated market cap.

Do not submit a mapping with synthetic or guessed evidence just to make the calculator succeed. Use the Prices/Filings/Securities inspection views and actual public records to establish the mapping. The real-data pilot remains pending until a real price/share calculation and its captured evidence have been reviewed.

## Manual check and commit

- Confirm only the selected company's common-stock securities appear.
- Missing security data should disable the form rather than infer an identity.
- Leave confirmation unchecked: saving must not submit.
- Try reversed dates or a known date before Valid from: an error must appear.
- With verified real evidence, save once and inspect the recorded fields.
- Repeat identical fields: the mapping ID should stay the same.
- A changed overlapping declaration should be rejected while the original evidence remains.
- Check keyboard navigation and the expanded panel in a narrow window.

After tests and UI verification:

```powershell
git add app/dashboard/static/index.html app/dashboard/static/dashboard.js tests/test_dashboard_mapping.py docs/DASHBOARD_SHARE_MAPPING.md
git diff --cached --stat
git commit -m "Add evidence-backed share mapping controls to dashboard"
Remove-Item Env:\QUANTAI_TEST_DATABASE_URL -ErrorAction SilentlyContinue
```

Next milestone: validate one real company end to end using SEC shares, verified mapping, raw prices, and split evidence. Subsequent Part One work covers financial-statement normalization, scheduled coverage, historical universe/ranking validation, and reproducible dataset exports. ML/backtesting remains deferred.
