#!/usr/bin/env bash
# One-time setup for a fresh clone of security-copilot: backend venv +
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

# CPU-only by default (matches requirements.txt's guidance — swap this if
# you have a CUDA GPU and want the matching wheel instead):
#   TORCH_INDEX_URL=https://download.pytorch.org/whl/cu128 ./download_everything.bash
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cpu}"

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$1"; }

command -v python3 >/dev/null 2>&1 || { echo "python3 is required but not found." >&2; exit 1; }
command -v node    >/dev/null 2>&1 || { echo "node is required but not found (needed for the extension)." >&2; exit 1; }
command -v npm     >/dev/null 2>&1 || { echo "npm is required but not found (needed for the extension)." >&2; exit 1; }

# --- Backend: venv + Python deps -----------------------------------------
log "Backend: setting up Python virtualenv"
cd "$BACKEND_DIR"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  echo "Created .venv"
else
  echo ".venv already exists, reusing it"
fi

# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip

log "Backend: installing torch (CPU wheel — override with TORCH_INDEX_URL for GPU)"
pip install torch --index-url "$TORCH_INDEX_URL"

log "Backend: installing requirements.txt"
pip install -r requirements.txt

log "Backend: installing Playwright's Chromium (used by the inspect_website tool)"
playwright install chromium
warn "If the sandbox fails to launch later with a missing-library error, also run:"
warn "  cd backend && source .venv/bin/activate && playwright install --with-deps chromium"
warn "(needs sudo — installs OS-level libraries, not run automatically by this script)"

# --- Backend: .env scaffolding -------------------------------------------
if [ ! -f ".env" ]; then
  cp .env.example .env
  log "Created backend/.env from .env.example — fill in GROQ_API_KEYS before running the agent"
else
  echo ".env already exists, leaving it alone"
fi

# --- Backend: warm the ML model cache ------------------------------------
# Pre-downloads the two content_classifier models (see tools/content_classifier.py)
# into the standard Hugging Face cache (~/.cache/huggingface) so the first
# real check doesn't pay this cost mid-investigation.
log "Backend: pre-downloading ML models (this is the slow step — a few hundred MB)"
python3 - <<'PY'
from huggingface_hub import hf_hub_download
from transformers import pipeline

print("Downloading pirocheto/phishing-url-detection (ONNX)...")
hf_hub_download(repo_id="pirocheto/phishing-url-detection", filename="model.onnx")

print("Downloading ealvaradob/bert-finetuned-phishing...")
pipeline("text-classification", model="ealvaradob/bert-finetuned-phishing")

print("Models cached.")
PY

deactivate

# --- Extension: npm deps + first build -----------------------------------
log "Extension: installing npm dependencies"
cd "$EXTENSION_DIR"
npm install

log "Extension: building extension/dist (load unpacked in chrome://extensions)"
npm run build

log "Setup complete."
cat <<EOF

Next steps:
  1. Fill in backend/.env (GROQ_API_KEYS is required, VT_API_KEY is optional
     but recommended — see backend/README.md for where to get both).
  2. Run ./run_all.bash to start the backend + network helper (or ./start_all.bash
     for just the backend). The first run also trains the network models and
     builds the MITRE index (~500MB download, one-time).
  3. Load extension/dist/ as an unpacked extension in chrome://extensions.
EOF
