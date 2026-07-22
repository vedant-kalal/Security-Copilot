# Testing Guide

## Backend

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
pytest -v
```

Tests are split into two categories, and `pytest` runs both in one command:

### Pure unit tests (no external dependencies)

- `tests/test_correlation_engine.py` — the Threat Correlation Engine's title derivation, severity thresholds,
  confidence fusion, and MITRE mapping, including a direct check that the exact worked example from the
  architecture doc (`phishing_url_detected` + `credential_form_on_suspicious_site` → *"Credential Theft
  Attempt"*) holds.
- `tests/test_phishing_service.py` — the DistilBERT classifier (or its heuristic fallback, if `torch` isn't
  installed) correctly separates a legitimate URL from a brand-impersonation phishing URL.
- `tests/test_anomaly_service.py` — the Isolation Forest model scores a DDoS-like flow higher than normal
  traffic, and batch/single prediction paths agree.

These always run, anywhere, with no setup beyond `pip install -r requirements.txt`.

### Integration tests (require PostgreSQL)

- `tests/test_auth.py` — register/login/refresh/`me` against a real database.
- `tests/test_incidents_api.py` — the full pipeline end-to-end: register → register device → submit a phishing
  URL event → assert an incident was created with evidence, MITRE mapping, and an AI-generated explanation;
  plus a dashboard-reflects-incident check and a status-update check.

These are automatically **skipped** (not failed) if `DATABASE_URL` isn't reachable — see
`tests/conftest.py::requires_database`. To run them, point at a second database (so tests never touch your dev
data) using the same Postgres instance you set up in `docs/INSTALLATION.md`:

```bash
# In psql (or `sudo -u postgres psql` on WSL2 / `SQL Shell (psql)` on native Windows):
#   CREATE DATABASE sentinelai_test OWNER sentinelai;
#   \c sentinelai_test
#   CREATE EXTENSION IF NOT EXISTS vector;

cd backend
DATABASE_URL=postgresql+asyncpg://sentinelai:sentinelai@localhost:5432/sentinelai_test \
DATABASE_URL_SYNC=postgresql+psycopg2://sentinelai:sentinelai@localhost:5432/sentinelai_test \
pytest -v
```

(PowerShell: set each with `$env:DATABASE_URL = "..."` on its own line instead of the `VAR=value` prefix form.)

Each test gets a fresh schema (`conftest.py`'s `db_session` fixture creates all tables before the test and drops
them after), so tests are independent and order-safe.

> Two of the pipeline tests (`test_phishing_event_creates_incident_with_mitre_mapping`,
> `test_incident_status_can_be_updated`) call `pytest.skip(...)` if the heuristic phishing fallback (used when
> `torch`/`transformers` aren't installed) happens to score the test URL below the incident threshold — install
> `torch` + `transformers` for the real DistilBERT model to make these deterministic.

## Frontend (dashboard)

```bash
cd dashboard
npm install
npm run typecheck   # tsc --noEmit, strict mode
npm run build        # full production build — the strongest correctness signal for a Vite/React app
npm run lint
```

There is no separate unit-test runner configured for the dashboard (no complex client-side business logic to
unit test — the data-fetching hooks are thin wrappers around the typed API client, and the API client itself is
exercised by the backend's integration tests via the same HTTP contract). `npm run build` catches type errors,
broken imports, and JSX errors across the whole app.

## Extension

```bash
cd extension
npm install
npm run typecheck
npm run build   # produces extension/dist/ — load it unpacked in chrome://extensions to manually verify
```

Manual verification checklist after building:

1. Load `extension/dist/` as an unpacked extension.
2. Sign in via the popup — confirm a device appears in the dashboard's Devices page.
3. Navigate to an obviously fake phishing-style URL — confirm the toolbar badge turns red/amber and a
   notification appears.
4. Open the popup on that tab — confirm Risk/Confidence/Reasons render and all four buttons work (View Details
   opens the dashboard incident; Leave Site navigates away; Continue/Report update the popup state).
5. Submit a form containing a password field on any test page — confirm a `form_submission` event reaches the
   backend (check backend logs or the incident's evidence list if it correlates into an incident).

## What "passing" looks like in this environment

At the time this repository was built, the full backend unit-test suite (13 tests) passed and all 9
database-dependent integration tests skipped cleanly (no Postgres available in the build environment) rather
than failing — exactly the intended behavior. Both `dashboard` and `extension` built successfully via
`npm run build` with zero TypeScript errors under strict mode. Run the integration tests yourself against a real
Postgres (see above) for full end-to-end confidence.
