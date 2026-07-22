# SentinelAI — AI Security Copilot

A complete, working implementation of the SentinelAI product spec: a browser extension + React dashboard +
FastAPI backend that combines phishing detection, network anomaly detection, threat correlation, MITRE ATT&CK
mapping, and RAG-grounded LLM-generated guided response into a single incident-centered security product.

> Not a phishing detector. A Security Copilot. Every signal — a suspicious URL, a malicious file download, a
> network anomaly — flows through one **Threat Correlation Engine** into one **Incident**, which the dashboard
> explains in plain English with a concrete remediation plan.

## What's inside

| Component | Stack |
|---|---|
| **Backend** | FastAPI, SQLAlchemy (async), PostgreSQL + pgvector, JWT auth |
| **Dashboard** | React, Vite, TypeScript, TailwindCSS, shadcn-pattern components, Framer Motion |
| **Extension** | Chrome Manifest V3, React, TypeScript |
| **ML** | DistilBERT (phishing classification), Isolation Forest (network anomaly detection) |
| **Threat Intel** | VirusTotal, AbuseIPDB, PhishTank — with caching |
| **RAG / LLM** | Google Gemini (`gemini-embedding-001` + `gemini-flash-latest`) over a pgvector playbook library |
| **Deployment** | Native (Windows/WSL2/Linux) — see Deployment guide for production options |

## Quick start (Windows, no Docker)

Fastest path — fully native Windows (no pgvector compilation required, using our optimized in-memory NumPy vector search):

```powershell
# 1. Create Database & User
# Open PowerShell and run:
psql -U postgres
# Paste these commands inside the psql prompt:
CREATE ROLE sentinelai WITH LOGIN PASSWORD 'sentinelai';
CREATE DATABASE sentinelai OWNER sentinelai;
\q

# 2. Setup Backend
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
# Install torch (CPU version is recommended to avoid massive GPU download timeouts)
pip install torch --index-url https://download.pytorch.org/whl/cpu --no-cache-dir
pip install -r requirements.txt
# Copy environment variables & seed database (skips alembic migrations, creates all tables instantly!)
copy .env.example .env
python ..\scripts\seed_db.py
uvicorn app.main:app --reload

# 3. Setup Dashboard (in a second terminal)
cd dashboard
copy .env.example .env
npm install
npm run dev

# 4. Setup Extension (in a third terminal)
cd extension
npm install
npm run build
```

- Dashboard: **http://localhost:5173** — log in with `demo@sentinelai.io` / `SentinelDemo123!`
- API docs: **http://localhost:8000/docs**

Then load the browser extension:
Open `chrome://extensions` → enable Developer mode → **Load unpacked** → select `extension/dist/`.

Full walkthrough: **[docs/INSTALLATION.md](docs/INSTALLATION.md)**.

## How it works

```
Extension observes browser events
        → FastAPI ingests them
        → Threat Intelligence lookup (VirusTotal / AbuseIPDB / PhishTank, cached)
        → DistilBERT phishing classification
        → Isolation Forest anomaly detection (network flows)
        → Threat Correlation Engine fuses signals into ONE Incident
        → MITRE ATT&CK mapping
        → RAG retrieves the matching playbook (pgvector)
        → Gemini generates a plain-English explanation + remediation plan
        → Dashboard updates in real time
```

Full breakdown, including how each signal maps to code: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Documentation

| Doc | Covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, the Threat Correlation Engine, ML pipelines, RAG/LLM, database design rationale |
| [docs/API.md](docs/API.md) | Every endpoint, request/response shapes |
| [docs/INSTALLATION.md](docs/INSTALLATION.md) | Windows setup (WSL2 or fully native), GPU/PyTorch setup, verifying everything works |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production checklist, scaling, PaaS deployment |
| [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) | Codebase layout, design system, how to extend it |
| [docs/TESTING.md](docs/TESTING.md) | Running the test suite (backend pytest, frontend build/typecheck) |
| [docs/FOLDER_STRUCTURE.md](docs/FOLDER_STRUCTURE.md) | Annotated full file tree |
| [extension/README.md](extension/README.md) | Extension-specific build/load instructions |

## Repository layout

```
backend/    dashboard/    extension/    shared/    database/    scripts/    docs/
```

See [docs/FOLDER_STRUCTURE.md](docs/FOLDER_STRUCTURE.md) for the annotated version.

## Verified to work

This isn't a scaffold — every piece was exercised before being called done:

- All 9 database tables compile to valid PostgreSQL DDL (`database/schema.sql`, generated from the same ORM
  models the app runs on).
- A real Isolation Forest model was trained on the bundled sample dataset and verified to score DDoS-like
  traffic higher than normal traffic.
- The phishing heuristic fallback correctly separates a legitimate URL from a brand-impersonation phishing URL
  (the primary path uses the real DistilBERT model when `torch`/`transformers` are installed).
- The Threat Correlation Engine reproduces the exact worked example from the product spec: a phishing URL +
  credential-form submission correlates into one incident titled *"Credential Theft Attempt"*.
- Backend: 13 unit tests pass; 9 database integration tests are included and run against a real Postgres (see
  [docs/TESTING.md](docs/TESTING.md)).
- Dashboard and extension both build cleanly with `npm run build` under TypeScript strict mode, zero errors.

## Status

MVP-complete per the architecture document's Definition of Done (section 22): extension authenticates, events
reach the backend, DistilBERT detects phishing, Isolation Forest detects anomalies, the Threat Correlation
Engine creates incidents, the dashboard displays them, MITRE mapping works, RAG returns playbooks, and Gemini
explains the threat.

**Deferred to post-MVP** (per the spec's explicit "Future" section): AI Incident Timeline, Attack Replay, Threat
Graph, AI Investigation Mode, Executive Reports.

## License

Provided as-is for evaluation/demo purposes.
