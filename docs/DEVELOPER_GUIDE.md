# Developer Guide

## Repository layout

```
sentinelai/
├── backend/            FastAPI application (see below)
├── dashboard/           React + Vite + TypeScript investigation UI
├── extension/            Chrome Manifest V3 extension
├── shared/                Cross-package TypeScript type reference
├── database/               Generated SQL schema + sample seed SQL
├── scripts/                  Training, seeding, schema-export utilities
├── docs/                       This documentation
└── .gitignore
```

See `docs/FOLDER_STRUCTURE.md` for the fully expanded tree with a one-line description of every file.

## Backend architecture (Clean Architecture layering)

```
app/api/v1/*.py        → routers: parse request, call a service, return a schema. No business logic.
app/services/*.py      → business logic. Orchestrates repositories, ML modules, external clients.
app/repositories/*.py  → the only layer that touches SQLAlchemy queries directly.
app/models/*.py        → SQLAlchemy ORM models (the schema).
app/schemas/*.py        → Pydantic request/response contracts (never expose ORM models directly).
app/ml/*.py                → model loading + inference, no FastAPI/DB dependency.
app/core/*.py                → config, security, logging, database session, exception types.
```

Dependency direction is strictly top-to-bottom: routers depend on services, services depend on
repositories/ML/external clients, repositories depend on models. Nothing below the service layer imports FastAPI.

**Adding a new endpoint**: add/extend a Pydantic schema in `app/schemas/`, add the logic to the relevant service
in `app/services/` (or create a new one), add a thin router function in `app/api/v1/`, register it in
`app/api/v1/router.py`.

**Adding a new detection signal**: add a new `Signal` name, add its title-rule to `_TITLE_RULES` and MITRE
mapping to `SIGNAL_TO_TECHNIQUES` (`app/utils/mitre_mappings.py`), and produce it from the relevant
`_signals_from_*` method in `app/services/incident_service.py`.

## Frontend architecture (dashboard)

```
src/lib/api-client.ts   → typed fetch wrapper, JWT attach + refresh-on-401
src/context/            → AuthContext (global auth state)
src/hooks/               → data-fetching hooks (useDashboard, useIncidents)
src/components/ui/         → restyled shadcn-pattern primitives (button, card, dialog, tabs, select, table...)
src/components/{dashboard,incidents,network,layout}/  → feature components
src/pages/                    → route-level components, composed from the above
src/router.tsx                  → react-router route table
```

State management is deliberately simple: React state + hooks, no Redux/Zustand — the app's data needs
(dashboard summary, incident list/detail, device list) don't justify a global store beyond `AuthContext`.

### Design system — "Night Watch"

A deep-navy security-operations-room palette with a teal "sentinel" signal color (all-clear / monitoring state)
and an amber→red severity ramp, defined as Tailwind theme tokens in `dashboard/tailwind.config.ts`:

- **Typography**: Space Grotesk (display/headings), Inter (body), IBM Plex Mono (data — timestamps, confidence
  percentages, MITRE technique IDs, JSON-like content) — a technical-but-legible three-face system distinct from
  generic default sans-only UI.
- **Signature element**: the Security Score gauge (`components/dashboard/SecurityScoreGauge.tsx`) renders as a
  radar/sonar dial with a slow rotating sweep, rather than a generic donut chart — reflecting the product's
  "always-watching sentinel" concept. The same ambient radar-ring motif echoes on the login page background.
- **Severity color coding** (`threat.low/medium/high/critical` in the Tailwind config) is used consistently
  across badges, the severity breakdown bars, and the security-operations alert banner.

## Extension architecture

See `extension/README.md` for the full breakdown (background service worker / content script / popup / options,
and why the content script is built as a separate IIFE pass).

## Environment variables

Each of `backend/`, `dashboard/`, and `extension/` has a `.env.example` — copy each to `.env` in place. There is
no shared root `.env`; every service reads its own local one (see `docs/INSTALLATION.md`).

## Code style

- **Python**: type hints everywhere (`from __future__ import annotations` + PEP 604 unions), Google-style
  docstrings on every public function/class, `ruff`/`black`-compatible formatting (4-space indent, double
  quotes, ~110 col soft limit).
- **TypeScript**: strict mode (`tsconfig.app.json` / `tsconfig.json`), no `any`, functional components +
  hooks only, path alias `@/` for `src/`.
- **Commits/PRs**: keep business logic in services/hooks, not in routers/components, so it stays testable
  without spinning up the web framework.

## Common tasks

| Task | Command |
|---|---|
| Run backend locally | `cd backend && uvicorn app.main:app --reload` |
| Create a new migration | `cd backend && alembic revision -m "description"` (then hand-edit like `0001_initial_schema.py`, or use `--autogenerate` against a running DB) |
| Regenerate `database/schema.sql` | `python scripts/export_schema.py` |
| Retrain the anomaly model | `python scripts/train_isolation_forest.py --input path/to/real_baseline.csv` |
| Reseed playbooks + demo data | `python scripts/seed_db.py` |
| Run backend tests | `cd backend && pytest -v` |
| Typecheck dashboard | `cd dashboard && npm run typecheck` |
| Typecheck extension | `cd extension && npm run typecheck` |
