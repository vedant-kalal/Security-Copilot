# Installation Guide (Windows, no Docker)

This guide sets up SentinelAI directly on a Windows machine — no Docker anywhere. Two paths, pick one:

- **Path A — WSL2 (recommended)**: run Postgres+pgvector and the backend inside Windows Subsystem for Linux.
  Fastest to get working, best NVIDIA GPU support, and side-steps every Windows-specific build headache below.
  WSL2 is a Windows feature, not a container platform — this is still "no Docker."
- **Path B — Fully native Windows**: everything runs directly in PowerShell/cmd. More steps (pgvector has to be
  compiled with Visual Studio), but no Linux subsystem involved at all.

Either way, the browser extension is always loaded into Chrome on Windows normally — that part doesn't change.

## Your GPU (RTX 5060, 8GB VRAM)

Good news, with two caveats:

1. **You don't strictly need it for this project.** The phishing classifier is DistilBERT-base (~66M
   parameters) — it runs in single-digit-to-low-double-digit milliseconds on CPU. The Isolation Forest anomaly
   detector is scikit-learn, which is CPU-only regardless. GPU acceleration is a nice-to-have here, not a
   bottleneck — don't let GPU setup block you from just running the project on CPU first (`pip install torch`,
   no index URL, and skip straight to "Verify everything works" below) and coming back to this later.
2. **When you do want it**: RTX 50-series cards (Blackwell architecture, compute capability `sm_120`) need
   **CUDA 12.8+** wheels. PyTorch has shipped native `sm_120` support in stable releases since 2.7.0 (current
   stable is 2.11.0 as of this writing). Install with:

   ```powershell
   pip install torch --index-url https://download.pytorch.org/whl/cu128
   ```

   Do **not** run plain `pip install torch` if you want GPU support — the default PyPI wheel is CPU-only on
   Windows. You also don't need to separately install the full NVIDIA CUDA Toolkit — the `cu128` wheel bundles
   its own CUDA runtime; you only need a reasonably recent NVIDIA driver (anything from mid-2025 onward
   supports CUDA 12.8 — update via the NVIDIA app or [nvidia.com/drivers](https://www.nvidia.com/drivers) if
   unsure). Verify it worked:

   ```powershell
   python -c "import torch; print(torch.__version__, '| CUDA available:', torch.cuda.is_available(), '|', torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
   ```

   You should see something like `2.11.0+cu128 | CUDA available: True | NVIDIA GeForce RTX 5060`. The backend
   auto-detects this — `PHISHING_MODEL_DEVICE=auto` in `.env` (the default) picks the GPU automatically once
   it's available; you don't need to change any application code.

   This same command (and the same wheel index) works identically inside WSL2 — `pip` will fetch the Linux
   `cu128` wheel instead of the Windows one automatically. NVIDIA's Windows driver already provides CUDA
   passthrough into WSL2, so no separate Linux driver install is needed there either.

## Prerequisites (both paths)

- **Python 3.11 or 3.12** — [python.org/downloads](https://www.python.org/downloads/) (check "Add python.exe to PATH" during install)
- **Node.js 20 LTS+** — [nodejs.org](https://nodejs.org/)
- **Git for Windows** — [git-scm.com](https://git-scm.com/download/win)
- **Google Chrome** (to load the extension)
- Optional but recommended free API keys — every feature works without these (graceful fallbacks throughout),
  but real threat intel and LLM output make for a far more convincing demo:
  - [VirusTotal](https://www.virustotal.com/gui/join-us), [AbuseIPDB](https://www.abuseipdb.com/register) (threat intelligence)
  - [Gemini](https://aistudio.google.com/apikey) (RAG playbook retrieval + incident explanations)

---

## Path A — WSL2 (recommended)

### 1. Install WSL2 + Ubuntu

In an **administrator** PowerShell:

```powershell
wsl --install
```

Reboot if prompted. This installs Ubuntu by default. Open "Ubuntu" from the Start menu and finish the one-time
Linux username/password setup.

### 2. Postgres + pgvector (inside the Ubuntu/WSL2 terminal)

```bash
sudo apt update
sudo apt install -y curl ca-certificates
sudo install -d /usr/share/postgresql-common/pgdg
sudo curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc --fail \
  https://www.postgresql.org/media/keys/ACCC4CF8.asc
sudo sh -c 'echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo $VERSION_CODENAME)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
sudo apt update
sudo apt install -y postgresql-16 postgresql-16-pgvector

sudo service postgresql start
sudo -u postgres psql -c "CREATE ROLE sentinelai WITH LOGIN PASSWORD 'sentinelai';"
sudo -u postgres psql -c "CREATE DATABASE sentinelai OWNER sentinelai;"
sudo -u postgres psql -d sentinelai -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Postgres now listens on `localhost:5432` — reachable both from other WSL2 processes and from Windows itself
(WSL2 forwards `localhost` both directions by default).

> Every time you reopen Ubuntu, Postgres won't auto-start — run `sudo service postgresql start` again (or set
> it up with `systemd` if your WSL version supports it: `sudo systemctl enable postgresql`).

### 3. Backend (inside WSL2)

```bash
cd /mnt/c/Users/<you>/path/to/sentinelai/backend    # or wherever you cloned/extracted it
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

# CPU-only, fastest way to get running:
pip install torch
# — OR, for GPU acceleration (see "Your GPU" above) —
pip install torch --index-url https://download.pytorch.org/whl/cu128

pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`: set `JWT_SECRET_KEY` (generate one with
`python3 -c "import secrets; print(secrets.token_urlsafe(64))"`). The default `DATABASE_URL`/`DATABASE_URL_SYNC`
already match what step 2 created.

```bash
alembic upgrade head
python ../scripts/train_isolation_forest.py   # optional — a bootstrap fallback model works out of the box
python ../scripts/seed_db.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend running at http://localhost:8000 (docs at `/docs`) — reachable from Windows browsers/tools too.

> **Tip**: working from `/mnt/c/...` (your Windows filesystem, mounted into WSL2) is convenient but slower for
> heavy file I/O (like `npm install`). If `npm install` feels sluggish in step 4, `git clone` the repo directly
> into your Linux home directory instead (`~/sentinelai`) and it'll be noticeably faster.

### 4. Dashboard (inside WSL2, a second terminal)

```bash
cd sentinelai/dashboard
cp .env.example .env      # defaults to http://localhost:8000/api/v1 — correct as-is
npm install
npm run dev
```

Dashboard at http://localhost:5173, reachable from Windows Chrome.

### 5. Extension

Build it inside WSL2 (Node is already set up there):

```bash
cd sentinelai/extension
cp .env.example .env
npm install
npm run build
```

Then, in **Windows** Chrome:

1. Open `chrome://extensions` → enable **Developer mode** → **Load unpacked**.
2. Browse to `\\wsl.localhost\Ubuntu\home\<you>\sentinelai\extension\dist` (or wherever you cloned it — WSL2's
   filesystem is reachable from any Windows file picker via the `\\wsl.localhost\` path). If you cloned under
   `/mnt/c/...` instead, just use the regular `C:\...` path to `extension\dist`.
3. Click the SentinelAI icon → sign in (`demo@sentinelai.io` / `SentinelDemo123!`, or create a new account) —
   or open the Options page to change the API URL if needed.

---

## Path B — Fully native Windows

### 1. PostgreSQL

Download the Windows installer from
[postgresql.org/download/windows](https://www.postgresql.org/download/windows/) (EDB installer, version 16 or
17). During setup, remember the password you set for the `postgres` superuser, and leave the port at `5432`.

### 2. pgvector (build from source with Visual Studio)

pgvector doesn't ship a Windows installer — it has to be compiled against your Postgres install. This needs
**Visual Studio Build Tools** with the C++ workload:

1. Install [Visual Studio Build Tools](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio)
   (the free "Build Tools" installer is enough — you don't need the full IDE). In the installer, check
   **"Desktop development with C++"**.
2. Open **"x64 Native Tools Command Prompt for VS 2022"** (search for it in the Start menu) **as Administrator**.
3. Run:

   ```bat
   set "PGROOT=C:\Program Files\PostgreSQL\16"
   cd %TEMP%
   git clone --branch v0.8.5 https://github.com/pgvector/pgvector.git
   cd pgvector
   nmake /F Makefile.win
   nmake /F Makefile.win install
   ```

   Adjust `PGROOT` to match your installed Postgres version/path if different.

4. Create the database and enable the extension. Open **SQL Shell (psql)** (installed alongside Postgres, in
   the Start menu) and connect as `postgres` with the password from step 1, then:

   ```sql
   CREATE ROLE sentinelai WITH LOGIN PASSWORD 'sentinelai';
   CREATE DATABASE sentinelai OWNER sentinelai;
   \c sentinelai
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

> If the Visual Studio build step is more friction than you want right now, switch to **Path A (WSL2)** —
> `apt install postgresql-16-pgvector` replaces this entire section with one command.

### 3. Backend

In PowerShell:

```powershell
cd sentinelai\backend
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip

# CPU-only, fastest way to get running:
pip install torch
# — OR, for GPU acceleration (see "Your GPU" above) —
pip install torch --index-url https://download.pytorch.org/whl/cu128

pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` in a text editor: set `JWT_SECRET_KEY` (generate one with
`python -c "import secrets; print(secrets.token_urlsafe(64))"`). The default `DATABASE_URL`/`DATABASE_URL_SYNC`
already match what step 2 created.

```powershell
alembic upgrade head
python ..\scripts\train_isolation_forest.py   # optional — a bootstrap fallback model works out of the box
python ..\scripts\seed_db.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend running at http://localhost:8000 (docs at `/docs`).

> **Note on `torch`/`transformers`**: PyTorch is a large download (1-3 GB depending on CPU/GPU variant). The
> backend works without it too — the phishing classifier automatically falls back to a heuristic detector
> (brand-impersonation patterns, suspicious TLDs, etc.) and logs a warning if `torch` isn't installed at all.
> Install it for the real DistilBERT model.

### 4. Dashboard

In a second PowerShell window:

```powershell
cd sentinelai\dashboard
copy .env.example .env
npm install
npm run dev
```

Dashboard at http://localhost:5173.

### 5. Extension

```powershell
cd sentinelai\extension
copy .env.example .env
npm install
npm run build
```

In Chrome: `chrome://extensions` → **Developer mode** → **Load unpacked** → select `sentinelai\extension\dist`.
Sign in with `demo@sentinelai.io` / `SentinelDemo123!` (or create a new account).

---

## Verifying everything works

Same checklist regardless of which path you took:

1. Dashboard home page loads and shows a Security Score (100 if no incidents yet).
2. Sign in via the extension popup — a device should appear under **Devices** in the dashboard within a few
   seconds.
3. Navigate to a URL like `http://amaz0n-login-security-verify.tk` (not a real site — detection runs on the URL
   string itself, it doesn't need to resolve). A browser notification and toolbar badge should appear, and an
   incident should show up under **Investigation** in the dashboard within a couple of seconds.
4. On the **Network** page, click **Start Replay** to replay the bundled sample dataset and watch anomaly-driven
   incidents appear.

If something doesn't work, check the `uvicorn` terminal for errors first (most issues are a wrong
`DATABASE_URL`, a missing `JWT_SECRET_KEY`, or Postgres not running), then see `docs/TESTING.md` for the
automated test suite, which exercises this exact flow end-to-end.

## Running everything again later

Once set up, day-to-day startup is just (three terminals, whichever path you chose):

```
Terminal 1:  cd backend    && [venv activate] && uvicorn app.main:app --reload
Terminal 2:  cd dashboard  && npm run dev
Terminal 3:  (only when you change extension code) cd extension && npm run build, then reload it in chrome://extensions
```

Postgres runs as a background service (WSL2: `sudo service postgresql start`; native Windows: it's already
registered as a Windows Service and starts automatically on boot — check **Services** app if unsure, look for
"postgresql-x64-16").
