# SentinelAI — Architecture

This document explains how the pieces fit together. For the original product spec, see the two source-of-truth
files this implementation was built from: `SentinelAI_Project_Context_and_Knowledge_Transfer.md` and
`SentinelAI_Solution_Architecture_and_Technical_Design.md`.

## System overview

```
 Browser Extension (MV3)          React Dashboard
        │  events, JWT                  │  REST/JSON, JWT
        ▼                               ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                        FastAPI Backend                       │
 │                                                               │
 │  Threat Intel   DistilBERT       Isolation Forest             │
 │  (VT/AbuseIPDB/  Phishing         Anomaly Detector             │
 │   PhishTank)     Classifier                                   │
 │        │             │                  │                     │
 │        └─────────────┴────────┬─────────┘                     │
 │                                ▼                               │
 │                  Threat Correlation Engine                     │
 │                                │                                │
 │                                ▼                                │
 │                            Incident ◄── MITRE mapping            │
 │                                │                                │
 │                                ▼                                │
 │                   RAG Service ──► playbooks (pgvector)           │
 │                                │                                │
 │                                ▼                                │
 │                        Gemini (LLM)                             │
 └─────────────────────────────────┬─────────────────────────────┘
                                    ▼
                     PostgreSQL + pgvector
```

## The Incident-centered design

Per the source spec's closing statement: *"Every component exists to answer one question: 'What happened, why
did it happen, how serious is it, and what should the user do next?' That answer is represented by the Incident
object."*

Concretely, `backend/app/models/incident.py` is the hub every other table points at:

- `events` — raw telemetry (what happened, at the lowest level)
- `evidence` — links specific `events` to an `incident`, with a `reason` and `score` (why it matters)
- `incidents.severity` / `incidents.confidence` — how serious
- `ai_responses` — Gemini's plain-English summary + numbered remediation (what to do next)
- `incidents.mitre` — the MITRE ATT&CK techniques the activity maps to

## Core workflow, mapped to code

| # | Step (from the spec) | Implementation |
|---|---|---|
| 1-2 | Install extension, login (JWT) | `extension/src/popup/`, `POST /auth/login`, `backend/app/core/security.py` |
| 3-4 | Extension monitors events → sent to FastAPI | `extension/src/background/index.ts` → `POST /events`, `POST /phishing/check` |
| 5 | Threat intelligence lookup | `backend/app/services/threat_intel_service.py` (VirusTotal, AbuseIPDB, PhishTank, cached in `threat_cache`) |
| 6 | Phishing detection | `backend/app/ml/phishing_model.py` (DistilBERT) + `backend/app/services/phishing_service.py` |
| 7 | Isolation Forest anomaly detection | `backend/app/ml/anomaly_model.py`, trained via `scripts/train_isolation_forest.py` |
| 8 | Threat Correlation Engine groups related events | `backend/app/services/correlation_service.py` |
| 9 | Incident is created | `IncidentService.ingest_and_correlate` in `backend/app/services/incident_service.py` |
| 10 | MITRE mapping | `backend/app/utils/mitre_mappings.py` |
| 11 | RAG retrieves playbooks | `backend/app/services/rag_service.py` + `playbooks` table (pgvector cosine search) |
| 12 | LLM generates response | `backend/app/services/llm_service.py` (Gemini) |
| 13 | Dashboard updates | `dashboard/src/hooks/useDashboard.ts`, `useIncidents.ts` polling `GET /dashboard`, `GET /incidents` |

## The Threat Correlation Engine

The heart of the product (`backend/app/services/correlation_service.py`). For each ingested event, the pipeline
(`IncidentService._build_signals`) produces zero or more typed `Signal`s:

| Signal | Triggered by |
|---|---|
| `phishing_url_detected` | DistilBERT classifies a visited URL as phishing |
| `malicious_domain_reputation` | VirusTotal/PhishTank flags the domain |
| `suspicious_file_download` | A download with an executable extension, especially from a flagged source |
| `credential_form_on_suspicious_site` | A password-field form is submitted on a flagged domain |
| `repeated_login_attempts` | 5+ failed logins from the same device within 10 minutes |
| `network_anomaly_high_volume` / `_port_scan` / `_beaconing` | Isolation Forest flags a network flow, sub-classified by which features drove the anomaly |

`ThreatCorrelationEngine.process_signals`:

1. Fuses signal scores with a **noisy-OR** combination (`_aggregate_confidence`) — independent evidence
   compounds, so two medium-confidence signals produce higher combined confidence than either alone, matching
   the "Credential Theft Attempt" worked example in the architecture doc (phishing URL + credential form → high
   confidence, not just the max of the two).
2. Looks for an existing `open`/`investigating` incident for the same user within
   `CORRELATION_WINDOW_MINUTES` (default 30) — if found, the new evidence is attached there instead of creating
   a duplicate incident ("less alert fatigue").
3. Otherwise creates a new `Incident`, with its title chosen by pattern-matching the signal combination against
   `_TITLE_RULES` (e.g. `{phishing_url_detected, credential_form_on_suspicious_site}` → *"Credential Theft
   Attempt"*, the exact example from the architecture doc).
4. Computes severity from confidence thresholds (`derive_severity`) and MITRE techniques from the signal names
   (`techniques_for_signals`).
5. Triggers RAG + Gemini to generate the `ai_responses` row for the incident.

## Machine learning

### Phishing detection — DistilBERT

`backend/app/ml/phishing_model.py` loads `cybersectony/phishing-email-detection-distilbert_v2.4.1` from Hugging
Face (inference only — the project spec explicitly says not to retrain). The model is a 4-way classifier over
`{legitimate_email, phishing_url, legitimate_url, phishing_url_alt}`; the phishing probability is the sum of the
two phishing-labeled classes. If `transformers`/`torch` are not installed or the model can't be downloaded, a
heuristic fallback (brand-impersonation, suspicious TLDs, IP-literal URLs, excessive hyphenation) keeps the
endpoint functional — this is a safety net, not the primary path.

### Network anomaly detection — Isolation Forest

`backend/app/ml/anomaly_model.py`. Unlike DistilBERT, Isolation Forest has no pretrained weights — it must be
*fit* on a baseline of normal traffic. `scripts/train_isolation_forest.py` does this (using the bundled sample
CICIDS2017 dataset by default, or a real dataset export you supply via `--input`) and persists the fitted
estimator + `StandardScaler` to `backend/model_artifacts/`. If no artifact is present, the backend bootstraps a
small default model from a synthetic baseline distribution at first use, logging a warning to re-run the real
training script.

`backend/app/ml/feature_engineering.py` defines the 10-feature vector (`duration`, packet counts, byte counts,
rate, destination port, etc.) used consistently at both training and inference time, with aliases so it accepts
CICIDS2017-style, UNSW-NB15-style, or generic field names.

## RAG + Gemini

- **Embeddings**: `gemini-embedding-001` via the `google-genai` SDK, stored in the `playbooks.embedding` column
  (pgvector `Vector(768)`), searched with cosine distance (`Playbook.embedding.cosine_distance(...)`).
- **Generation**: `gemini-flash-latest`, prompted with the incident's title/severity/MITRE mapping/evidence and
  the retrieved playbook(s), constrained to a `SUMMARY: ... RECOMMENDATION: ...` format that the backend parses.
- **Fallback**: if `GEMINI_API_KEY` is not set (or a call fails), both paths degrade gracefully — retrieval falls
  back to MITRE technique-ID overlap search, and generation falls back to a deterministic templated explanation
  — so the demo never breaks on a missing API key or quota limit.

## Database

See `docs/API.md` for the endpoint reference and `database/schema.sql` for the generated DDL. Nine tables total:
the eight from the architecture spec (`users`, `devices`, `sessions`, `events`, `incidents`, `evidence`,
`ai_responses`, `threat_cache`) plus one addition, `playbooks`, needed to give the RAG pipeline somewhere to
store playbook content + embeddings (the spec describes *"RAG retrieves playbooks"* but doesn't define a table
for them).

## Why each technology choice (beyond what the spec already states)

- **Noisy-OR signal fusion** over simple max/average: it's the standard way to combine independent evidence of
  a binary "is this malicious" event without letting a single weak signal cap the whole incident's confidence
  ceiling, while still requiring genuinely corroborating evidence (not just one very confident single detector)
  to reach `critical`.
- **In-memory rate limiting instead of Redis**: the target deployment (see `docs/DEPLOYMENT.md`) is a single
  backend process;
  `backend/app/middleware/rate_limit.py` documents the Redis migration path for horizontal scaling.
- **Separate Vite build pass for the content script**: MV3 content scripts need to run as classic scripts for
  broad compatibility, while the popup/options/background can safely be ES modules — see `extension/README.md`.
