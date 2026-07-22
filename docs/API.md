# SentinelAI — API Reference

Base URL: `http://localhost:8000/api/v1` (configurable via `VITE_API_BASE_URL` / the extension's Options page).

Interactive docs (Swagger UI) are always available at `http://localhost:8000/docs` while the backend is running,
generated automatically from the FastAPI route definitions — treat this document as a companion overview, and
`/docs` as the source of truth for exact request/response schemas.

All endpoints except `POST /auth/register`, `POST /auth/login`, and `POST /auth/refresh` require:

```
Authorization: Bearer <access_token>
```

Errors are returned as:

```json
{
  "error": {
    "code": "not_found",
    "message": "Incident ... not found",
    "details": {},
    "request_id": "..."
  }
}
```

---

## Authentication

### `POST /auth/register`
Create an account. Body: `{ "email": string, "password": string (min 8 chars) }`.
Returns `TokenResponse` (`access_token`, `refresh_token`, `token_type`, `expires_in`). **201**.

### `POST /auth/login`
Body: `{ "email": string, "password": string }`. Returns `TokenResponse`. **200**.

### `POST /auth/refresh`
Body: `{ "refresh_token": string }`. Returns a new `TokenResponse`. **200**.

### `GET /auth/me`
Returns the authenticated user's profile (`id`, `email`, `created_at`).

---

## Devices

### `POST /devices`
Register a device for the current user. Body: `{ "browser": string, "os": string }`. **201**.
Called once by the extension after sign-in (architecture doc: *"Backend registers a Device"*).

### `GET /devices`
List all devices for the current user.

### `POST /devices/{device_id}/heartbeat`
Updates `last_seen`. Called periodically by the extension's background worker.

---

## Events

### `POST /events`
Ingest a single telemetry event and run it through the full detection + correlation pipeline synchronously.

```json
{
  "device_id": "uuid",
  "event_type": "url_visit",
  "payload": { "url": "http://example.com" },
  "timestamp": "2026-07-19T12:00:00Z"
}
```

`event_type` is one of: `page_navigation`, `url_visit`, `file_download`, `form_submission`, `login_attempt`,
`network_flow`, `network_flow_replay`, `network_flow_upload`. `payload` shape depends on `event_type` — see
`backend/app/services/incident_service.py` (`_signals_from_*` methods) for exactly which payload keys each event
type reads (e.g. `file_download` reads `filename` and `source_url`; `login_attempt` reads `success`).

Response: `{ "accepted": 1, "incident_id": "uuid" | null, "incident_created": bool }`. **201**.

### `POST /events/batch`
Same as above but accepts `{ "events": [ ... ] }` for a buffered flush; all events must share one `device_id`.

---

## Phishing detection

### `POST /phishing/check`
Real-time URL classification, used by the extension popup on every navigation.

```json
{ "url": "http://amaz0n-login.tk", "page_title": "Sign in", "device_id": "uuid" }
```

Response:

```json
{
  "url": "http://amaz0n-login.tk",
  "is_phishing": true,
  "confidence": 0.87,
  "risk_label": "high",
  "reasons": ["DistilBERT classified input as 'phishing_url' with 84% probability", "virustotal: 12 vendors flagged as malicious"],
  "threat_intel_hit": true,
  "incident_id": "uuid"
}
```

If `device_id` is supplied, the check is also recorded as a `url_visit` event and correlated into an incident.

---

## Network anomaly detection

### `POST /network/upload` (multipart/form-data)
Fields: `device_id` (form field), `file` (`.csv`). Every row is featurized and scored by Isolation Forest
immediately. Response: `{ "rows_ingested": int, "anomalies_detected": int, "incidents_created": int, "incident_ids": [uuid] }`. **201**.

Expected CSV columns follow common CICIDS2017/UNSW-NB15 flow-export names (see
`backend/app/ml/feature_engineering.py` for the full alias list) — e.g. `Flow Duration`, `Total Fwd Packets`,
`Flow Bytes/s`, `Destination Port`, or their UNSW-NB15 equivalents (`dur`, `spkts`, `rate`, `dport`). Unknown
columns are ignored; missing columns fall back to sane defaults.

### `POST /network/replay/start`
Body: `{ "dataset": "cicids2017" | "unsw-nb15", "device_id": "uuid" (optional), "max_rows": int (default 200), "speed": float (rows/sec, default 10) }`.
Schedules a background replay of the bundled sample dataset as if it were live telemetry. Returns immediately
with `{ "replay_id": uuid, "dataset": string, "rows_scheduled": int, "status": "started" }`. **202**.
Watch `GET /incidents` or the dashboard for incidents appearing as the replay progresses.

---

## Dashboard

### `GET /dashboard`
Returns the home-page summary:

```json
{
  "devices_protected": 2,
  "security_score": 76,
  "incidents_today": 3,
  "open_incidents": 2,
  "severity_breakdown": { "low": 1, "medium": 2, "high": 1, "critical": 0 },
  "recent_incidents": [ /* Incident[] */ ]
}
```

`security_score` = `100 - (low×2 + medium×5 + high×12 + critical×25)`, floored at 0, over unresolved incidents.

---

## Incidents

### `GET /incidents?status=open&page=1&page_size=20`
Paginated list. `status` is optional (`open`, `investigating`, `contained`, `resolved`, `dismissed`).
Response: `{ "items": Incident[], "total": int, "page": int, "page_size": int }`.

### `GET /incidents/{incident_id}`
Full detail, including `evidence_entries[]` and `ai_responses[]`.

### `PATCH /incidents/{incident_id}`
Body: `{ "status": "resolved" }`. Updates status; returns the full incident detail.

---

## Playbooks

### `GET /playbooks/{incident_id}`
Returns the guided-response playbook(s) retrieved via RAG for that incident (`Playbook[]`, each with `id`,
`title`, `mitre_techniques`, `content`).

---

## System

### `GET /health`
Liveness probe: `{ "status": "ok", "service": "SentinelAI", "environment": "..." }`. No auth required.
