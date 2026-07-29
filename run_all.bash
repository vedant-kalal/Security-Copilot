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
# GROQ_API_KEYS.
#
# Usage:
#   ./run_all.bash                     # backend + native helper on :8010
#   PORT=8020 ./run_all.bash           # different port
#   WITH_NATIVE_HOST=0 ./run_all.bash  # backend only (no live network monitoring)
#   SKIP_MITRE=1 ./run_all.bash        # don't build the MITRE index if missing
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_DIR="$ROOT_DIR/.venv"
PORT="${PORT:-8010}"
WITH_NATIVE_HOST="${WITH_NATIVE_HOST:-1}"
SKIP_MITRE="${SKIP_MITRE:-0}"

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$1"; }
die()  { printf '\033[1;31mERROR: %s\033[0m\n' "$1" >&2; exit 1; }

[ -d "$VENV_DIR" ] || die ".venv not found at $VENV_DIR — run ./download_everything.bash first."

cd "$BACKEND_DIR"

[ -f ".env" ] || die "backend/.env not found — run ./download_everything.bash first, then fill in GROQ_API_KEYS."

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

grep -qE '^GROQ_API_KEYS?=.+' .env || \
  warn "No GROQ_API_KEYS (or GROQ_API_KEY) set in backend/.env — the agent will fail on every case. Get free keys at https://console.groq.com/keys"

if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
  exec 3>&-
  die "Something is already listening on 127.0.0.1:$PORT. Stop it, or run with PORT=<free-port> ./run_all.bash."
fi

# --- One-time: make sure the network-path models exist -------------------
# These three are fast (seconds). The backend/native helper both fall back to
# a synthetic bootstrap model if an artifact is missing, but training real ones
# gives proper detection quality.
log "Checking network-anomaly models"
[ -f "model_artifacts/isolation_forest.joblib" ]        || python "$ROOT_DIR/scripts/train_isolation_forest.py"
[ -f "model_artifacts/isolation_forest_window.joblib" ] || python "$ROOT_DIR/scripts/train_isolation_forest.py" --feature-set window
[ -f "model_artifacts/tranad.pt" ]                      || python "$ROOT_DIR/scripts/train_tranad.py"

# The MITRE index is the slow one (first run downloads ~500MB SecureBERT + the
# ATT&CK STIX bundle). Without it, /report-flow still works — flows just aren't
# tagged with a technique.
if [ ! -f "data/mitre/technique_index.json" ]; then
  if [ "$SKIP_MITRE" = "1" ]; then
    warn "MITRE index missing and SKIP_MITRE=1 — flows won't be tagged with an ATT&CK technique."
  else
    log "Building MITRE ATT&CK index (one-time, downloads ~500MB SecureBERT + STIX — grab a coffee)"
    python -m mitre.build_index
  fi
fi

# --- Launch services -----------------------------------------------------
cleanup() {
  log "Shutting down"
  [ -n "${BACKEND_PID:-}" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "${HOST_PID:-}" ]    && kill "$HOST_PID"    2>/dev/null || true
}
trap cleanup INT TERM EXIT

log "Starting backend on http://127.0.0.1:$PORT"
uvicorn api.app:app --host 127.0.0.1 --port "$PORT" &
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
  python "$ROOT_DIR/native-host/host.py" --backend-url "http://127.0.0.1:$PORT" &
  HOST_PID=$!
else
  warn "Native helper disabled (WITH_NATIVE_HOST=0) — backend only."
fi

cat <<EOF

  UI / history:      http://127.0.0.1:$PORT/
  Health check:      http://127.0.0.1:$PORT/health
  Extension:         load extension/dist/ as an unpacked extension in chrome://extensions
  Demo triggers:     python scripts/staged_flow_trigger.py post --backend-url http://127.0.0.1:$PORT
                     python scripts/replay_attack_flow.py --backend-url http://127.0.0.1:$PORT
  Stop everything:   Ctrl+C
EOF

# Wait on the backend; the trap tears down the helper too on exit.
wait "$BACKEND_PID"
