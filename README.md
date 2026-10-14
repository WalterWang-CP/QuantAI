# QuantAI Data Engine

Part One builds a historical financial data engine. The current backend includes
company/security/listing identities, manual and provider ingestion, price coverage,
corporate actions, shares and FX observations, market-cap reconstruction, ranking
snapshots, tracking policies, and retrieval jobs with retries and quota controls.
The website UI, full global historical universe, and other planned datasets remain
under development. ML, backtesting, and live trading belong to Part Two.

## Windows setup

Use Python 3.11 or newer and PostgreSQL 16. Run PowerShell from the project root.
For an existing installation, retain your virtual environment and `.env`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

`requirements.txt` contains the direct runtime packages; `requirements-dev.txt`
also installs pytest. These retain the project's existing direct package versions,
but do not lock every transitive dependency.

For a new installation only:

```powershell
Copy-Item .env.example .env
notepad .env
```

Create an empty `quantai` PostgreSQL database through pgAdmin, then set
`DATABASE_URL` to your real database URL. Use the `postgresql+psycopg` driver.
Percent-encode special characters in the username/password portions of the URL.
A provider API key is only required for live provider requests. Leave full-history
retrieval disabled unless your provider access supports it.

Apply migrations and start the API:

```powershell
python -m alembic upgrade head
python -m alembic current
python -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/docs> for the interactive API documentation.
`GET /` reports the running application. `GET /health` checks database connectivity:
HTTP 200 means healthy, and HTTP 503 means the database is unavailable. This check
does not verify migration readiness or provider availability.

Run commands from the project root so `.env` and the policy configuration resolve.
Keep real credentials in `.env`, outside version control.

## Tests

```powershell
python -m pytest -q
```

The normal suite uses isolated SQLite test databases and skips eight PostgreSQL
concurrency cases. To enable those cases with your running PostgreSQL instance:

```powershell
$env:QUANTAI_TEST_DATABASE_URL = python -c "from app.core.config import settings; print(settings.database_url)"
python -m pytest -q tests/test_retrieval_execution_safety.py tests/test_retrieval_concurrency.py
python -m pytest -q
Remove-Item Env:\QUANTAI_TEST_DATABASE_URL
```

The PostgreSQL concurrency fixture creates a unique temporary schema and drops it
after each case; the test account needs permission to create schemas. It does not
apply application migrations or modify application tables. Migration verification
is a separate check.

## Development workflow

Create a branch for each repair, replace the specified files, run the tests, review
the staged diff, and commit. Include explicit paths in `git add`. Keep virtual
environments, credentials, local archives, and generated databases out of commits.
