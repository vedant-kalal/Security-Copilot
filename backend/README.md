# backend/

The security-copilot backend. Flat, one-concern-per-file layout — no
`app/` wrapper, no ORM, no auth. See project memory
`security-copilot-spec` for the full build spec and
`security-copilot-poc-scope` for what's deliberately cut for this POC
(no DB beyond SQLite, no auth, Groq instead of Claude, terminal-first).

## Layout

```
config.py          All settings, one place. Nothing else defines env-driven config.
logger.py           Structured logging setup.
exceptions.py         Typed exception hierarchy for the API's error handler.
cli.py                  Terminal harness — run a case, watch it live, get a report + history entry.
report.py                Per-case markdown report (verdict, every tool call, screenshot, redirect chain).
history.py                  SQLite run history (record_run/list_runs/get_run) — what the UI reads.

agent/                The LangGraph graph (spec section 2).
  state.py              The state shape threaded through every node.
  llm_client.py          Groq chat model factory — the only file that knows about langchain_groq.
  router_node.py           Deterministic fast path: blocklist + cache.
  agent_node.py              Binds all 4 tools, calls the LLM. System prompt lives here.
  output_node.py               Parses VERDICT/CONFIDENCE/REASON/ALTERNATIVES, writes the cache.
  graph.py                       Wires the four nodes together + run_case_traced() (records history).

tools/                 What the agent can call. One file each.
  inspect_website.py      Playwright sandbox browser — screenshot, redirect chain, links, forms.
  domain_reputation.py      WHOIS + VirusTotal.
  content_classifier.py       pirocheto ONNX (URLs) / ealvaradob BERT (text).
  web_search.py                 Keyless DuckDuckGo (ddgs) — finds the real site when brand impersonation is suspected.

cache/                  The router's fast path storage.
  sqlite_cache.py          24h TTL verdict cache, keyed by URL.
  blocklist.py               Static blocklist loader (data/blocklist.txt).

api/                    FastAPI app (spec section 10). One file per route.
  app.py                    CORS + middleware + router mounting + serves the UI. Run this with uvicorn.
  schemas.py                  Request/response models.
  routes_check_links.py         POST /check-links
  routes_check_email.py           POST /check-email
  routes_report_flow.py             POST /report-flow
  routes_runs.py                      GET /runs, GET /runs/{id} — history, for the UI
  routes_health.py                      GET /health

ui/index.html           Single-file history/report viewer — submit a URL, browse past runs, see
                         screenshots inline. Served at http://localhost:8000/ by api/app.py.

network/                Network anomaly detection (spec section 5) — PARTIALLY BUILT.
mitre/                   MITRE ATT&CK mapping + remediation (spec section 6/7) — STUBBED.
middleware/               Rate limiting, request logging, error handling.
utils/                     Shared helpers: validators.py (URL/domain parsing), screenshots.py
                           (save a tool's screenshot to disk), tool_messages.py (extract a tool's
                           full result regardless of content_and_artifact vs plain response format).
data/                       Blocklist, cache.db, history.db, screenshots/, reports/ — all gitignored
                             except blocklist.txt and the bundled playbooks/datasets.
```

Every "not yet built" file says so in its own module docstring, with a
pointer to the relevant spec section — check there before assuming
something is wired up.

## Run it

First time only — or just run `../download_everything.bash` from here, which does all of this:

```bash
cd ..   # repo root — the venv lives there, not inside backend/
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
playwright install chromium          # needed by tools/inspect_website.py
cd backend && cp .env.example .env   # then fill in GROQ_API_KEYS at minimum
```

Every time after that — just activate the venv and cd back in:

```bash
source ../.venv/bin/activate   # if you're already in backend/
```

**Terminal** (fastest way to watch one case run — prints every tool call live, writes a report + history entry):

```bash
python cli.py link https://example.com/login
python cli.py email    # paste text, Ctrl-D to submit
```

**API + UI** (start the server, then open the UI in a browser):

```bash
uvicorn api.app:app --reload --port 8000
```

Then open **http://localhost:8000/** — paste a URL into the box at the
top to check it, click any past run in the sidebar to see its full
report (screenshot, redirect chain, WHOIS/VirusTotal, model scores,
legitimate alternatives if brand impersonation was suspected).

Or hit the API directly:

```bash
curl -X POST localhost:8000/check-links -H 'content-type: application/json' \
  -d '{"urls": ["https://example.com"]}'
```

Both paths (`cli.py` and the API) write to the same `data/history.db`
and `data/reports/` — a case checked from the terminal shows up in the
UI's history list too, and vice versa.

## What's real vs. stubbed right now

| Piece | Status |
|---|---|
| `agent/`, `tools/`, `cache/`, `api/`, `cli.py`, `report.py`, `history.py`, `ui/` | Fully implemented and tested against live services |
| `network/feature_engineering.py`, `isolation_forest.py` | Ported and working, but not yet matching spec 5.1/5.2 exactly — see their docstrings |
| `network/flow_collector.py`, `network/tranad.py` | Stubs — raise `NotImplementedError` |
| `mitre/` (all three files) | Stubs — `lookup.py`'s functions return `None`, safe to call |
| `native-host/` | Stubs/templates only |
| `extension/` (repo root) | Exists but built against the old, now-deleted API — needs a rewrite per spec section 8, not yet started |
