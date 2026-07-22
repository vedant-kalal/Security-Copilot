# Deployment Guide

This project runs as plain processes — a Python (Uvicorn) process, a static file bundle for the dashboard, and
a PostgreSQL server. No container runtime is required anywhere in this guide; see `docs/INSTALLATION.md` for
local Windows/WSL2 setup, and use the same building blocks below to run it somewhere persistent.

## Production checklist

- **`JWT_SECRET_KEY`**: generate a long random value (`python -c "import secrets; print(secrets.token_urlsafe(64))"`)
  and never reuse the example value. Rotating it invalidates all existing tokens.
- **`ENVIRONMENT=production`, `DEBUG=false`**: switches structured JSON logging on (`app/core/logging.py`) and
  tightens the in-memory rate limiter to 120 req/min/IP (`app/middleware/rate_limit.py`).
- **`CORS_ORIGINS`**: set to your actual dashboard origin(s); do not leave it as `localhost` in production.
- **Database backups**: back up your PostgreSQL data directory with your normal tooling (`pg_dump`, WAL
  archiving, or your cloud provider's managed Postgres backups).
- **Model artifacts**: `backend/model_artifacts/*.joblib` (the fitted Isolation Forest) must persist across
  deploys — keep it on persistent disk, not an ephemeral container filesystem. Re-run
  `scripts/train_isolation_forest.py` whenever you have a better traffic baseline.
- **Rate limiting**: `backend/app/middleware/rate_limit.py` is in-memory, sized for a single backend process. If
  you run multiple backend processes/instances behind a load balancer, replace it with a Redis-backed limiter
  (the interface is a drop-in `BaseHTTPMiddleware` — see the module's docstring).
- **Secrets**: every credential (`JWT_SECRET_KEY`, `VIRUSTOTAL_API_KEY`, `ABUSEIPDB_API_KEY`, `GEMINI_API_KEY`)
  is read from environment variables only — never hardcoded. Inject these via your platform's secret manager or
  process supervisor's environment config rather than a plain `.env` file sitting on a production disk.

## Running the backend as a persistent service

### Windows Server / Windows machine acting as a server

Use [NSSM](https://nssm.cc/) (Non-Sucking Service Manager) to wrap the Uvicorn process as a real Windows
Service that survives reboots and restarts on crash:

```powershell
nssm install SentinelAIBackend "C:\path\to\sentinelai\backend\.venv\Scripts\uvicorn.exe" "app.main:app --host 0.0.0.0 --port 8000"
nssm set SentinelAIBackend AppDirectory "C:\path\to\sentinelai\backend"
nssm start SentinelAIBackend
```

Serve the dashboard's production build (`npm run build` in `dashboard/`, output in `dashboard/dist/`) with IIS,
or any static file server pointed at that folder — just make sure unknown routes fall back to `index.html` (it's
a client-side-routed SPA), and set `VITE_API_BASE_URL` at build time to wherever the backend ends up.

### Linux server (including a WSL2 instance you keep running, or a real VM/VPS)

Use `systemd`:

```ini
# /etc/systemd/system/sentinelai-backend.service
[Unit]
Description=SentinelAI backend
After=postgresql.service

[Service]
User=sentinelai
WorkingDirectory=/opt/sentinelai/backend
Environment="PATH=/opt/sentinelai/backend/.venv/bin"
EnvironmentFile=/opt/sentinelai/backend/.env
ExecStart=/opt/sentinelai/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now sentinelai-backend
```

Build the dashboard (`npm run build`) and serve `dashboard/dist/` with nginx or Caddy, with a fallback route to
`index.html` for client-side routing, and a reverse-proxy rule forwarding `/api/` (or however you split it) to
the Uvicorn process. Terminate TLS at nginx/Caddy — Uvicorn itself doesn't handle certificates in this setup.

## Scaling beyond one machine

- **Backend**: stateless aside from the in-memory rate limiter (see above) — run multiple Uvicorn
  processes/machines behind a load balancer once that's swapped for Redis.
- **Database**: PostgreSQL is the single stateful component. Use a managed Postgres with the `pgvector`
  extension available (Amazon RDS, Google Cloud SQL, Supabase, Neon, etc. all support it), or self-host with
  replication.
- **ML inference**: `PhishingClassifier` and `AnomalyDetector` are process-local singletons
  (`@lru_cache`-wrapped factory functions) — each backend process loads its own copy of the model. For high
  throughput, consider splitting inference into a dedicated service behind an internal API, but this is not
  necessary at the scale this project targets.

## Deploying to a PaaS (Render, Railway, Fly.io, etc.)

Each has slightly different conventions, but the shape is the same:

1. **Database**: provision a managed Postgres instance with `pgvector` enabled (check the provider's docs for
   `CREATE EXTENSION vector` support — most modern Postgres offerings support it).
2. **Backend**: deploy `backend/` as a Python web service (most PaaS providers auto-detect
   `requirements.txt` and let you set a custom start command). Start command:
   `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Set the environment variables
   from `backend/.env.example` (`DATABASE_URL`, `JWT_SECRET_KEY`, etc.) in the platform's dashboard.
3. **Dashboard**: `npm run build` in `dashboard/`, then serve `dashboard/dist/` as a static site (Vercel,
   Netlify, Cloudflare Pages, S3+CloudFront all work well for a Vite SPA). Set `VITE_API_BASE_URL` to your
   deployed backend's public URL at build time.
4. **Extension**: see below — it isn't deployed to a server at all.

## The browser extension is not "deployed" the same way

Chrome extensions are either:

- **Loaded unpacked** for development/demo (`chrome://extensions` → Developer mode → Load unpacked →
  `extension/dist/`), or
- **Published to the Chrome Web Store** for real distribution (`npm run build` in `extension/`, then zip the
  contents of `extension/dist/` and follow the
  [Chrome Web Store developer dashboard](https://chrome.google.com/webstore/devconsole) flow — outside the scope
  of this repo, since it requires a Google developer account and review process).

Either way, make sure the extension's configured API URL (Options page) points at your deployed backend, not
`localhost`.

## If you want Docker later

Nothing in the application code depends on containers — `backend/` is a plain Python app and `dashboard/` is a
plain static build, so writing a `Dockerfile` for either (or a `docker-compose.yml` tying them together with a
`pgvector/pgvector` Postgres image) is a standard, mechanical exercise if/when you want it. It's just not
included in this build, per your setup preference.
