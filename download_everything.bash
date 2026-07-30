#!/usr/bin/env bash
# One-time setup for a fresh clone of security-copilot: a repo-root venv +
# Python deps, Playwright's Chromium, a warm cache of the two ML models
# (so the first real request isn't the one paying the download cost),
# backend/.env scaffolding, and the extension's npm deps + a first build.
#
# Safe to re-run — it never overwrites an existing .venv or .env, it
# just makes sure everything is present.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
EXTENSION_DIR="$ROOT_DIR/extension"
VENV_DIR="$ROOT_DIR/.venv"

# CPU-only by default (matches requirements.txt's guidance — swap this if
# you have a CUDA GPU and want the matching wheel instead):
#   TORCH_INDEX_URL=https://download.pytorch.org/whl/cu128 ./download_everything.bash
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cpu}"

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$1"; }

command -v python3 >/dev/null 2>&1 || { echo "python3 is required but not found." >&2; exit 1; }
command -v node    >/dev/null 2>&1 || { echo "node is required but not found (needed for the extension)." >&2; exit 1; }
command -v npm     >/dev/null 2>&1 || { echo "npm is required but not found (needed for the extension)." >&2; exit 1; }

# --- Python virtualenv, at the repo root (shared by backend/ + scripts/ + native-host/) ---
log "Setting up Python virtualenv at $VENV_DIR"

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
  echo "Created .venv"
else
  echo ".venv already exists, reusing it"
fi

# Use the venv's interpreter by absolute path (Windows/git-bash uses Scripts/,
# Linux/macOS bin/) instead of relying on `activate` rewriting PATH — it silently
# no-ops when another venv is already active in the parent shell.
if   [ -x "$VENV_DIR/Scripts/python.exe" ]; then VENV_PY="$VENV_DIR/Scripts/python.exe"
elif [ -x "$VENV_DIR/bin/python" ];         then VENV_PY="$VENV_DIR/bin/python"
else echo "Could not find the venv Python under $VENV_DIR (Scripts/ or bin/)." >&2; exit 1
fi
"$VENV_PY" -m pip install --upgrade pip

log "Installing torch (CPU wheel — override with TORCH_INDEX_URL for GPU)"
"$VENV_PY" -m pip install torch --index-url "$TORCH_INDEX_URL"

log "Installing backend/requirements.txt"
"$VENV_PY" -m pip install -r "$BACKEND_DIR/requirements.txt"

log "Installing Playwright's Chromium (used by the inspect_website tool)"
"$VENV_PY" -m playwright install chromium
warn "If the sandbox fails to launch later with a missing-library error, also run:"
warn "  \"$VENV_PY\" -m playwright install --with-deps chromium"
warn "(needs sudo — installs OS-level libraries, not run automatically by this script)"

# --- Backend: .env scaffolding -------------------------------------------
cd "$BACKEND_DIR"
if [ ! -f ".env" ]; then
  cp .env.example .env
  log "Created backend/.env from .env.example — fill in OPENROUTER_API_KEYS before running the agent"
else
  echo "backend/.env already exists, leaving it alone"
fi

# --- Warm the ML model cache ----------------------------------------------
# Pre-downloads the two content_classifier models (see backend/tools/content_classifier.py)
# into the standard Hugging Face cache (~/.cache/huggingface) so the first
# real check doesn't pay this cost mid-investigation.
log "Pre-downloading ML models (this is the slow step — a few hundred MB)"
"$VENV_PY" - <<'PY'
from huggingface_hub import hf_hub_download
from transformers import pipeline

print("Downloading pirocheto/phishing-url-detection (ONNX)...")
hf_hub_download(repo_id="pirocheto/phishing-url-detection", filename="model.onnx")

print("Downloading ealvaradob/bert-finetuned-phishing...")
pipeline("text-classification", model="ealvaradob/bert-finetuned-phishing")

print("Models cached.")
PY

# --- Extension: npm deps + first build -----------------------------------
log "Extension: installing npm dependencies"
cd "$EXTENSION_DIR"
npm install

log "Extension: building extension/dist (load unpacked in chrome://extensions)"
npm run build

log "Setup complete."
cat <<EOF

Next steps:
  1. Fill in backend/.env (OPENROUTER_API_KEYS is required, VT_API_KEY is optional
     but recommended — see backend/README.md for where to get both).
  2. Run ./run_all.bash (backend + network monitoring) or ./start_all.bash
     (backend only) to start it.
  3. Load extension/dist/ as an unpacked extension in chrome://extensions.
EOF
