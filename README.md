# security-copilot

A personal security assistant: paste a URL or a page's text (via the Chrome extension, a small web UI, or a
terminal), and a [LangGraph](https://github.com/langchain-ai/langgraph) agent investigates it — a real headless
browser sandbox, WHOIS/VirusTotal, two pretrained phishing-classification models, and a web search to find the
real site if brand impersonation is suspected — then returns a plain-English verdict: **dangerous / suspicious /
safe**, with a confidence score, a reason, and (when relevant) links to the legitimate site it thinks you meant
to visit.

This is a from-scratch POC, not a production product — see [Status](#status) for what's real vs. stubbed.

## What it does

- **Investigates, it doesn't just classify.** The agent decides for itself which tools to call and how deep to
  go — a page that looks fine after one look gets a quick "safe"; a page with a login form on an unfamiliar
  domain gets a screenshot, a WHOIS/VirusTotal check, a model score, and sometimes a second look at a suspicious
  link found on the page, before it answers.
- **Explains itself.** Every verdict is a few plain sentences citing what the tools actually showed — not just a
  score.
- **Catches brand impersonation.** If a domain embeds a well-known brand name in a way that isn't that brand's
  real site (`wmw-google-com.loca.lt`), the agent searches for the real company and surfaces its actual site(s)
  alongside the verdict.
- **Every check is recorded.** A local SQLite history + a per-case markdown report (screenshot, redirect chain,
  every tool call) — browsable from the web UI or `GET /runs`.
- **Watches your network too.** A local helper aggregates this machine's connection metadata (never packet
  contents) into 60-second windows and scores each with two unsupervised models — an Isolation Forest (single
  window) and TranAD (the temporal sequence, catching beaconing / slow exfiltration a single window misses). A
  flow that either model flags is mapped to the nearest MITRE ATT&CK technique (SecureBERT embeddings) and sent
  through the *same* agent, so a suspicious flow gets the same explained verdict + remediation as a bad link.

## How it works

```mermaid
flowchart LR
    subgraph Entry["Entry points"]
        EXT["Chrome Extension\n(popup)"]
        UI["Web UI\n(history + reports)"]
        CLI["cli.py\n(terminal)"]
        HOST["native-host/host.py\nflow collector +\nIsolation Forest + TranAD"]
    end

    EXT -- "POST /check-links\nPOST /check-email" --> API
    UI -- "POST /check-links" --> API
    CLI --> RUN
    HOST -- "POST /report-flow\n(+ MITRE technique)" --> API

    API["FastAPI\n(backend/api/)"] --> RUN["run_case_traced()"]

    subgraph Agent["LangGraph agent (backend/agent/)"]
        direction TB
        ROUTER["router_node\nblocklist + 24h cache"]
        AGENT_N["agent_node\nLLM picks the next tool"]
        TOOLS["tools\n(ToolNode)"]
        OUTPUT["output_node\nparse VERDICT / REASON / ...\nwrite cache"]

        ROUTER -- "cache/blocklist hit" --> OUTPUT
        ROUTER -- "unresolved" --> AGENT_N
        AGENT_N -- "tool call" --> TOOLS
        TOOLS -- "result" --> AGENT_N
        AGENT_N -- "final answer, no tool calls" --> OUTPUT
    end

    RUN --> ROUTER

    TOOLS -.-> T1["inspect_website\nheadless Chromium sandbox"]
    TOOLS -.-> T2["domain_reputation\nWHOIS + VirusTotal"]
    TOOLS -.-> T3["content_classifier\nONNX URL model /\nBERT text model"]
    TOOLS -.-> T4["web_search\nDuckDuckGo, keyless"]

    OUTPUT --> HIST[("history.db +\nmarkdown report")]
    OUTPUT --> VERDICT["Verdict\nlabel, confidence, reason,\nlegitimate_alternatives"]
    VERDICT --> EXT
    VERDICT --> UI
    VERDICT --> CLI
```

Full breakdown of every file: [backend/README.md](backend/README.md).

## Quick start

**1. Install** (one-time):

```bash
git clone https://github.com/VatsalMehta-0523/sentinelai-cyber-security.git
cd sentinelai-cyber-security
./download_everything.bash    # venv, Python deps, Playwright's Chromium,
                               # warms the ML model cache, extension npm install + build
```

**2. Add your key** — edit `backend/.env`, set `OPENROUTER_API_KEY` (see below):

```bash
$EDITOR backend/.env
```

**3. Run everything:**

```bash
./run_all.bash                 # backend + native network helper, on http://127.0.0.1:8010
```

On its first run `run_all.bash` also trains the network-anomaly models and builds the MITRE ATT&CK index if
they're missing (the index step downloads ~500MB once — see [below](#network-anomaly-detection-local-traffic)).
Subsequent runs skip straight to launching the services. Prefer the backend alone (no live network monitoring)?
Use the original `./start_all.bash`, or `WITH_NATIVE_HOST=0 ./run_all.bash`.

Open **http://localhost:3000/** for the dashboard (history, reports, live scans), or use the CLI:

```bash
source .venv/bin/activate && cd backend
python cli.py link https://example.com
python cli.py email    # paste text, then Ctrl-D
```

**API keys:**
- `OPENROUTER_API_KEY` — required, the agent's LLM (via OpenRouter, an OpenAI-compatible gateway to many
  models). Get a key at https://openrouter.ai/keys. The default model is `openai/gpt-oss-120b` — reliable at
  tool calling (which the agent needs). Change `OPENROUTER_MODEL` to any tool-calling model at
  https://openrouter.ai/models. If OpenRouter rate-limits the key (429), the case fails safe to a
  low-confidence "suspicious, try again" verdict instead of crashing.
- `VT_API_KEY` — optional, VirusTotal lookups in `domain_reputation`. Degrades gracefully if unset. Free:
  https://www.virustotal.com/gui/join-us

### Manual setup (if you'd rather not run the scripts)

```bash
python3 -m venv .venv && source .venv/bin/activate   # venv lives at the repo root
pip install torch --index-url https://download.pytorch.org/whl/cpu   # or the cu128 index for a CUDA GPU
pip install -r backend/requirements.txt
playwright install chromium
cd backend && cp .env.example .env   # then fill in OPENROUTER_API_KEY
uvicorn api.app:app --reload --port 8010
```

### Startup scripts, at a glance

| Script | What it does |
|---|---|
| `download_everything.bash` | One-time setup: repo-root venv, Python deps, Chromium, ML model cache, extension build. |
| `run_all.bash` | Starts **everything**: backend + native network helper. Trains models / builds the MITRE index on first run. |
| `start_all.bash` | Starts **just the backend** (link/email agent + web UI). No network monitoring. |

All three expect the venv at `.venv/` in the repo root (not inside `backend/`) — that's what `download_everything.bash` creates.

## Load the Chrome extension

1. Make sure the backend is running first (`./start_all.bash`, or the manual steps above).
2. `cd extension && npm install && npm run build` (already done for you by `download_everything.bash`).
3. Open `chrome://extensions`, enable **Developer mode** (top right).
4. Click **Load unpacked**, select `extension/dist/`.
5. On any `http(s)://` page, click the security-copilot icon in the toolbar:
   - **Check this URL** — checks the current page's URL.
   - **Check page text** — grabs the visible page text and checks it (works on any webapp — an email client, a
     login page, anything with text on screen).
6. Click **Full report** on a verdict to open it in the web UI (screenshot, redirect chain, every tool call).

There's no sign-in and nothing runs automatically in the background — every check is a deliberate click. If your
backend isn't on `http://127.0.0.1:8010`, change it in the extension's Settings (gear icon in the popup).
Extension-specific details: [extension/README.md](extension/README.md).

## Network anomaly detection (local traffic)

The native helper (`native-host/host.py`) is a plain long-running Python process — no Chrome native-messaging
protocol, it just POSTs to the backend like everything else. Its loop:

1. **Collect** (`backend/network/flow_collector.py`) — polls `psutil.net_connections` every ~2s, diffs snapshots,
   and aggregates connection **metadata only** (never payloads) into 60-second feature-vector windows.
2. **Score** — each window through two unsupervised models:
   - **Isolation Forest** (`backend/network/isolation_forest.py`) — scores a single window; escalates above the
     99th-percentile-of-normal threshold.
   - **TranAD** (`backend/network/tranad.py`) — a transformer that scores the *sequence*, catching temporal
     patterns (beaconing, slow exfiltration) whose individual windows look normal.
   A window escalates if **either** model flags it.
3. **Report** — the flow's description is mapped to the nearest MITRE ATT&CK technique
   (`backend/mitre/lookup.py`, SecureBERT embeddings) and POSTed to `/report-flow`, which runs it through the
   same agent and returns an explained verdict + remediation (curated playbook text where available).

`run_all.bash` starts this helper for you. To run it on its own (backend must already be up):

```bash
source .venv/bin/activate
python native-host/host.py --backend-url http://127.0.0.1:8010
```

### Training the models / building the index

`run_all.bash` does this automatically on first run; to (re)build them by hand:

```bash
source .venv/bin/activate && cd backend

# Isolation Forest — per-row (labeled datasets) and windowed (live scoring):
python ../scripts/train_isolation_forest.py                       # csv/per-row model
python ../scripts/train_isolation_forest.py --feature-set window  # windowed model
# TranAD temporal model:
python ../scripts/train_tranad.py
# MITRE ATT&CK index (SecureBERT embeddings — downloads ~500MB the first time):
python -m mitre.build_index
```

The bundled sample CSVs (`backend/data/network_datasets/`) are 200-row smoke-test samples. For real detection
quality, retrain against the full [CICIDS2017](https://www.unb.ca/cic/datasets/ids-2017.html) or
[NSL-KDD](https://www.unb.ca/cic/datasets/nsl.html) via `--input <your.csv>`.

### Demo triggers

Generate a network anomaly on cue instead of waiting for real traffic to do something interesting:

```bash
source .venv/bin/activate
# Guaranteed: POST one hand-crafted anomalous flow straight to /report-flow
python scripts/staged_flow_trigger.py post --backend-url http://127.0.0.1:8010
# Live: open a burst of failed outbound connections for the running helper to catch
python scripts/staged_flow_trigger.py live
# Replay pre-recorded CICIDS2017 attack flows through the pipeline
python scripts/replay_attack_flow.py --backend-url http://127.0.0.1:8010
```

## Repository layout

```
backend/        FastAPI + LangGraph agent, network models (network/), MITRE mapping (mitre/). Flat, one file
                per concern — see backend/README.md for the full tree.
extension/      Chrome MV3 extension (React popup + options page, no background worker, no content script).
native-host/    The local network helper (host.py) — collects flows, scores with Isolation Forest + TranAD,
                POSTs anomalies to /report-flow.
scripts/        Utilities: train_isolation_forest.py, train_tranad.py, and the demo triggers
                (staged_flow_trigger.py, replay_attack_flow.py).
download_everything.bash   One-time setup: venv, deps, Playwright, ML model cache, extension build.
run_all.bash               Starts everything: backend + native helper (trains models / builds MITRE on 1st run).
start_all.bash             Starts just the backend (port-safe — refuses to clobber something already listening).
```

## Status

**Real and tested end-to-end:** the agent (all 4 tools), the router's blocklist/cache fast path, the CLI, the
FastAPI + web UI, run history + markdown reports, and the Chrome extension — all verified against live services
(OpenRouter, VirusTotal, WHOIS, DuckDuckGo, real phishing test sites) and, for the extension, loaded into real Chrome.

**Also built and verified:**
- `backend/network/` — flow collection (`flow_collector.py`), the Isolation Forest (per-row + windowed, with a
  persisted percentile threshold), and TranAD temporal detection. Verified: TranAD flags a synthetic
  slow-exfiltration / beaconing sequence the Isolation Forest misses, with no false positives on normal traffic.
- `backend/mitre/` — SecureBERT + MITRE ATT&CK index (`build_index.py`) and nearest-technique lookup
  (`lookup.py`), with curated playbook remediation text preferred over raw STIX.
- `native-host/host.py` — the local network helper, POSTing anomalies to `/report-flow`.

**Not built (by design):** per-user personalization — periodically retraining the models on *your* logged
traffic (excluding confirmed-malicious flows) instead of the public datasets. This is an ongoing task that only
begins after the helper has been running for a few weeks; see the phased plan for details.

## License

Provided as-is for evaluation/demo purposes.
