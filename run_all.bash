#!/usr/bin/env bash
# Starts EVERYTHING at once: the FastAPI backend (link/email agent + the
# /report-flow network path) AND the native helper that watches this machine's
# network flows and escalates anomalies to the backend.
#
# On first run it also makes sure the models the network path needs exist —
# the Isolation Forest (per-row + windowed), TranAD, and the SecureBERT + MITRE
# ATT&CK index — training/building any that are missing. Subsequent runs skip
# straight to launching the services (the artifacts are cached on disk).
#
# The Chrome extension is not a process — load extension/dist/ as an unpacked
# extension in chrome://extensions separately (see the README).
#
# Prereqs: run ./download_everything.bash once first (creates .venv at the
# repo root, installs deps + Chromium), then fill in backend/.env with your
# OPENROUTER_API_KEY.
#
# Usage:
#   ./run_all.bash                     # backend + native helper on :8010
#   PORT=8020 ./run_all.bash           # different backend port
#   WITH_NATIVE_HOST=0 ./run_all.bash  # backend only (no live network monitoring)
#   WITH_DASHBOARD=0 ./run_all.bash    # don't start the Next.js dashboard
#   DASHBOARD_PORT=3005 ./run_all.bash # dashboard on a different port
#   SKIP_MITRE=1 ./run_all.bash        # don't build the MITRE index if missing
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
DASHBOARD_DIR="$ROOT_DIR/dashboard"
VENV_DIR="$ROOT_DIR/.venv"
PORT="${PORT:-8010}"
DASHBOARD_PORT="${DASHBOARD_PORT:-3000}"
WITH_NATIVE_HOST="${WITH_NATIVE_HOST:-1}"
WITH_DASHBOARD="${WITH_DASHBOARD:-1}"
SKIP_MITRE="${SKIP_MITRE:-0}"

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$1"; }
die()  { printf '\033[1;31mERROR: %s\033[0m\n' "$1" >&2; exit 1; }

[ -d "$VENV_DIR" ] || die ".venv not found at $VENV_DIR — run ./download_everything.bash first."

cd "$BACKEND_DIR"

[ -f ".env" ] || die "backend/.env not found — run ./download_everything.bash first, then fill in OPENROUTER_API_KEY."

# Resolve the venv's interpreter by absolute path (Windows/git-bash uses
# Scripts/, Linux/macOS bin/) and invoke everything through it. We deliberately
# do NOT rely on `activate` rewriting PATH — it silently no-ops when another
# venv is already active in the parent shell (e.g. a `(.venv)` cmd prompt),
# which then leaves `uvicorn`/`python` pointing at the wrong environment.
if   [ -x "$VENV_DIR/Scripts/python.exe" ]; then VENV_PY="$VENV_DIR/Scripts/python.exe"
elif [ -x "$VENV_DIR/bin/python" ];         then VENV_PY="$VENV_DIR/bin/python"
else die "Could not find the venv Python under $VENV_DIR (looked in Scripts/ and bin/)."
fi

grep -qE '^OPENROUTER_API_KEY=.+' .env || \
  warn "No OPENROUTER_API_KEY set in backend/.env — the agent will fail on every case. Get a key at https://openrouter.ai/keys"

if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
  exec 3>&-
  die "Something is already listening on 127.0.0.1:$PORT. Stop it, or run with PORT=<free-port> ./run_all.bash."
fi

# --- One-time: make sure the network-path models exist -------------------
# These three are fast (seconds). The backend/native helper both fall back to
# a synthetic bootstrap model if an artifact is missing, but training real ones
# gives proper detection quality.
log "Checking network-anomaly models"
# Paths are RELATIVE to backend/ (our cwd) on purpose: on WSL/git-bash the
# venv's python is a Windows .exe that can't read POSIX absolute paths like
# /mnt/e/... — but it resolves relative paths against its (translated) cwd fine.
[ -f "model_artifacts/isolation_forest.joblib" ]        || "$VENV_PY" ../scripts/train_isolation_forest.py
[ -f "model_artifacts/isolation_forest_window.joblib" ] || "$VENV_PY" ../scripts/train_isolation_forest.py --feature-set window
[ -f "model_artifacts/tranad.pt" ]                      || "$VENV_PY" ../scripts/train_tranad.py

# The MITRE index is the slow one (first run downloads ~500MB SecureBERT + the
# ATT&CK STIX bundle). Without it, /report-flow still works — flows just aren't
# tagged with a technique.
if [ ! -f "data/mitre/technique_index.json" ]; then
  if [ "$SKIP_MITRE" = "1" ]; then
    warn "MITRE index missing and SKIP_MITRE=1 — flows won't be tagged with an ATT&CK technique."
  else
    log "Building MITRE ATT&CK index (one-time, downloads ~500MB SecureBERT + STIX — grab a coffee)"
    "$VENV_PY" -m mitre.build_index
  fi
fi

# --- Launch services -----------------------------------------------------
cleanup() {
  log "Shutting down"
  [ -n "${BACKEND_PID:-}" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "${HOST_PID:-}" ]    && kill "$HOST_PID"    2>/dev/null || true
  [ -n "${DASH_PID:-}" ]    && kill "$DASH_PID"    2>/dev/null || true
}
trap cleanup INT TERM EXIT

# Let the dashboard's browser origin (:3000) call the API. This overrides
# config.py's default CORS list, which has no :3000 entry; the extension is
# still covered by the chrome-extension:// regex in api/app.py, so it doesn't
# need to be listed here.
export CORS_ORIGINS="${CORS_ORIGINS:-http://localhost,http://127.0.0.1,http://localhost:$DASHBOARD_PORT,http://127.0.0.1:$DASHBOARD_PORT}"

log "Starting backend on http://127.0.0.1:$PORT"
"$VENV_PY" -m uvicorn api.app:app --host 127.0.0.1 --port "$PORT" &
BACKEND_PID=$!

# Wait for the backend to accept connections before starting the helper.
printf "Waiting for backend"
for _ in $(seq 1 60); do
  if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then exec 3>&-; break; fi
  printf "."; sleep 1
done
printf " ready.\n"

if [ "$WITH_NATIVE_HOST" = "1" ]; then
  log "Starting native helper (watching local network flows -> /report-flow)"
  "$VENV_PY" ../native-host/host.py --backend-url "http://127.0.0.1:$PORT" &
  HOST_PID=$!
else
  warn "Native helper disabled (WITH_NATIVE_HOST=0) — backend only."
fi

# --- Dashboard (Next.js dev server) --------------------------------------
# NEXT_PUBLIC_API_BASE_URL points the dashboard at THIS backend's port (we run
# on 8010, not the dashboard's built-in :8000 default). A URL set in the
# dashboard's Settings page (localStorage) still overrides it per-browser.
if [ "$WITH_DASHBOARD" = "1" ]; then
  if command -v pnpm >/dev/null 2>&1; then
    if [ ! -d "$DASHBOARD_DIR/node_modules" ]; then
      log "Installing dashboard dependencies (first run)"
      (cd "$DASHBOARD_DIR" && pnpm install)
    fi
    log "Starting dashboard on http://localhost:$DASHBOARD_PORT (API -> http://localhost:$PORT)"
    (cd "$DASHBOARD_DIR" && NEXT_PUBLIC_API_BASE_URL="http://localhost:$PORT" pnpm dev --port "$DASHBOARD_PORT") &
    DASH_PID=$!
  else
    warn "pnpm not found — skipping the dashboard. Install pnpm (https://pnpm.io), or run it yourself: cd dashboard && NEXT_PUBLIC_API_BASE_URL=http://localhost:$PORT pnpm dev"
  fi
else
  warn "Dashboard disabled (WITH_DASHBOARD=0) — backend only."
fi

cat <<EOF

  Dashboard:         http://localhost:$DASHBOARD_PORT/   (the UI)
  Health check:      http://127.0.0.1:$PORT/health
  Extension:         load extension/dist/ as an unpacked extension in chrome://extensions
  Demo triggers      (run from the repo root in another terminal):
    "$VENV_PY" scripts/staged_flow_trigger.py post --backend-url http://127.0.0.1:$PORT
    "$VENV_PY" scripts/replay_attack_flow.py --backend-url http://127.0.0.1:$PORT
  Stop everything:   Ctrl+C
EOF

# Wait on the backend; the trap tears down the helper too on exit.
wait "$BACKEND_PID"
