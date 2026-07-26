#!/usr/bin/env bash
# Starts the security-copilot backend (the only long-running process this
# project has — the extension isn't a process, it's loaded into Chrome
# separately, see extension/README.md). Run ./download_everything.bash
# first if you haven't set anything up yet.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

# Ports 8000/8001 are commonly already taken by other local projects — this
# project defaults to 8010 for exactly that reason. Override with:
#   PORT=8020 ./start_all.bash
PORT="${PORT:-8010}"

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
die()  { printf '\033[1;31mERROR: %s\033[0m\n' "$1" >&2; exit 1; }

cd "$BACKEND_DIR"

[ -d ".venv" ] || die ".venv not found — run ./download_everything.bash first."
[ -f ".env" ]  || die "backend/.env not found — run ./download_everything.bash first, then fill in GROQ_API_KEY."

# shellcheck disable=SC1091
source .venv/bin/activate

if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
  exec 3>&-
  die "Something is already listening on 127.0.0.1:$PORT (likely an unrelated project — this repo defaults to 8010 to avoid the usual 8000/8001 collisions). Stop it first, or run with PORT=<free-port> ./start_all.bash."
fi

if ! grep -q '^GROQ_API_KEY=.\+' .env; then
  printf '\033[1;33m!! GROQ_API_KEY looks empty in backend/.env — the agent will fail on every case. Get a free key at https://console.groq.com/keys\033[0m\n'
fi

log "Starting security-copilot backend on http://127.0.0.1:$PORT"
cat <<EOF
  UI / history:      http://127.0.0.1:$PORT/
  Health check:       http://127.0.0.1:$PORT/health
  Extension:          load extension/dist/ as an unpacked extension in chrome://extensions
                       (run 'cd extension && npm run build' first if you haven't)
  Stop this server:   Ctrl+C
EOF

exec uvicorn api.app:app --host 127.0.0.1 --port "$PORT" --reload
