#!/usr/bin/env bash
# Starts the security-copilot backend (the only long-running process this
# project has — the extension isn't a process, it's loaded into Chrome
# separately, see extension/README.md). Run ./download_everything.bash
# first if you haven't set anything up yet.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_DIR="$ROOT_DIR/.venv"

# Ports 8000/8001 are commonly already taken by other local projects — this
# project defaults to 8010 for exactly that reason. Override with:
#   PORT=8020 ./start_all.bash
PORT="${PORT:-8010}"

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
die()  { printf '\033[1;31mERROR: %s\033[0m\n' "$1" >&2; exit 1; }

[ -d "$VENV_DIR" ] || die ".venv not found at $VENV_DIR — run ./download_everything.bash first."

cd "$BACKEND_DIR"

[ -f ".env" ] || die "backend/.env not found — run ./download_everything.bash first, then fill in OPENROUTER_API_KEY."

# Resolve the venv's interpreter by absolute path and invoke uvicorn through it
# (Windows/git-bash uses Scripts/, Linux/macOS bin/). We don't rely on `activate`
# rewriting PATH — it silently no-ops when another venv is already active in the
# parent shell (e.g. a `(.venv)` cmd prompt).
if   [ -x "$VENV_DIR/Scripts/python.exe" ]; then VENV_PY="$VENV_DIR/Scripts/python.exe"
elif [ -x "$VENV_DIR/bin/python" ];         then VENV_PY="$VENV_DIR/bin/python"
else die "Could not find the venv Python under $VENV_DIR (looked in Scripts/ and bin/)."
fi

if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
  exec 3>&-
  die "Something is already listening on 127.0.0.1:$PORT (likely an unrelated project — this repo defaults to 8010 to avoid the usual 8000/8001 collisions). Stop it first, or run with PORT=<free-port> ./start_all.bash."
fi

if ! grep -qE '^OPENROUTER_API_KEY=.+' .env; then
  printf '\033[1;33m!! No OPENROUTER_API_KEY set in backend/.env — the agent will fail on every case. Get a key at https://openrouter.ai/keys\033[0m\n'
fi

log "Starting security-copilot backend on http://127.0.0.1:$PORT"
cat <<EOF
  UI / history:      http://127.0.0.1:$PORT/
  Health check:       http://127.0.0.1:$PORT/health
  Extension:          load extension/dist/ as an unpacked extension in chrome://extensions
                       (run 'cd extension && npm run build' first if you haven't)
  Stop this server:   Ctrl+C
EOF

exec "$VENV_PY" -m uvicorn api.app:app --host 127.0.0.1 --port "$PORT" --reload
