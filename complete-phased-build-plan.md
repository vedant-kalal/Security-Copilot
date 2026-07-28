# security-copilot — complete phased build plan

This supersedes `remaining-work-prompt.md` — that file is now folded
into Phases 2-6 below with nothing lost. This document's goal is that
once every phase is checked off, nothing discussed across this project's
whole design process is left unbuilt or undecided. Phase 0 is context,
not work. Work through the rest in order; confirm each phase's "Done
when" criteria for real (run it) before starting the next one.

## Phase 0 — already built, no action needed

Context so nothing below gets rebuilt by accident: the LangGraph agent
(`router → agent ↔ tools → output`), all 4 tools (`inspect_website`,
`domain_reputation`, `content_classifier`, `web_search`), the router's
blocklist+cache fast path, FastAPI (`/check-links`, `/check-email`,
`/report-flow`, `/runs`, `/health`), the CLI, the web UI, run
history/reports, and the Chrome extension (click-triggered popup — "Check
this URL" / "Check page text", no content script, no background worker)
are all built and working. Don't touch `agent/`, `tools/`, `cache/`,
`api/routes_check_links.py`, `api/routes_check_email.py`, `cli.py`, or
`extension/` in any phase below unless that phase explicitly says to.

## Phase 1 — multi-key Groq resilience

A single Groq API key will not hold up: the agent can make several LLM
calls per case (one per tool-call round trip), and network-anomaly cases
will add more volume on top of link/email traffic. Build key rotation
now, before it becomes a real bottleneck.

**Config:** replace the single `GROQ_API_KEY` setting in `config.py`
with `GROQ_API_KEYS: List[str]`, parsed from a comma-separated env var
(same `_split_cors`-style validator pattern already used for
`CORS_ORIGINS` — reuse that approach). Update `.env.example` and `.env`
to hold all 5 keys: `GROQ_API_KEYS=key1,key2,key3,key4,key5`. Keep
backward compatibility: if only `GROQ_API_KEY` (singular) is set, treat
it as a one-key list rather than breaking.

**Rotation logic, in `agent/llm_client.py`:**
1. Maintain a module-level, thread-safe rotating index (an
   `itertools.cycle` over the key list guarded by a lock, or equivalent)
   so successive calls spread across keys round-robin — this balances
   load proactively instead of only reacting to failures.
2. Wrap the actual `ChatGroq` invocation with a retry loop: on a
   rate-limit error (Groq returns HTTP 429), advance to the next key and
   retry the same request, up to `len(GROQ_API_KEYS)` attempts.
3. If every key is rate-limited, raise a clear, specific exception (not
   a generic one) so `output_node.py`/the API's error handler can surface
   something better than a stack trace — a "suspicious, unresolved,
   temporarily rate-limited" fallback verdict is reasonable, similar in
   spirit to the existing `INCONCLUSIVE_VERDICT` in `graph.py`.
4. Log which key index handled each call at DEBUG level (never log the
   key values themselves) — useful for confirming rotation is actually
   happening during testing.

**Done when:** you can watch (via the DEBUG logs) requests rotating
across all 5 keys across several `cli.py` runs, and a manually-forced
429 (e.g. temporarily using an invalid key first in the list) correctly
falls through to the next key instead of failing the whole case.

## Phase 2 — network flow capture

Build `network/flow_collector.py` per its own module docstring: poll
`psutil.net_connections(kind='inet')` every 1-2 seconds, diff snapshots
to find new/closed connections, attribute each to its owning process via
`psutil.Process(pid).name()`. Aggregate into 60-second-window feature
vectors: connection count, unique destination count, unique port count,
failed/reset connection ratio, cyclical time-of-day encoding
(`sin`/`cos` of the hour), one-hot protocol. Metadata only — never
packet payloads (this is a non-negotiable constraint from the original
spec, not a preference).

Add `psutil` to `backend/requirements.txt` (currently commented out as
"not yet needed" — it's needed now).

**Done when:** running the collector standalone against your own
machine's traffic for a few minutes produces a stream of plausible
feature-vector dicts, one per window, with sane values (not all zeros,
not crashing on a `pid` that exited mid-capture).

## Phase 3 — Isolation Forest rework and retrain

Fix `network/isolation_forest.py` and `feature_engineering.py` per
their own docstrings:

1. **Feature set.** Add a feature function for `flow_collector.py`'s
   windowed output (Phase 2's shape), alongside the existing
   CICIDS2017-CSV-oriented one — keep both, they serve different
   purposes (live scoring vs. training against labeled datasets).
2. **Hyperparameters.** `IsolationForest(n_estimators=200,
   max_samples=256, contamination=0.02, random_state=42)`. `config.py`
   already has the right values in `ISOLATION_FOREST_MAX_SAMPLES` and
   `ISOLATION_FOREST_CONTAMINATION` — wire the model to actually read
   them.
3. **Threshold.** Replace the fixed sigmoid cutoff with the 99th
   percentile of `score_samples()` on held-out normal traffic
   (`ANOMALY_SCORE_THRESHOLD_PERCENTILE` already exists in `config.py`,
   unused). Recompute and persist this threshold every retrain, not just
   the model.

Rerun `scripts/train_isolation_forest.py` against the bundled sample
CSVs to confirm the pipeline still trains cleanly. Those CSVs are
200-row samples — fine for confirming the pipeline works, not enough for
real detection quality. Download the full CICIDS2017
(https://www.unb.ca/cic/datasets/ids-2017.html) or NSL-KDD
(https://www.unb.ca/cic/datasets/nsl.html) and retrain against that for
anything beyond a pipeline smoke test.

**Done when:** the training script runs clean end to end with the new
hyperparameters, persists both the model and its percentile threshold,
and scoring a known-anomalous sample row (versus a known-normal one)
produces a clearly separated score.

## Phase 4 — native helper (POST-based, not Chrome native messaging)

Earlier planning considered Chrome's native-messaging protocol for this;
that was simplified away. Build `native-host/host.py` as a standalone
long-running Python script that talks to the backend over plain HTTP,
the same way the extension already does:

1. Loop: call Phase 2's `collect_flows()`, score each window with Phase
   3's inference function.
2. If the score crosses the persisted threshold, `POST` to the backend's
   existing `/report-flow` endpoint with the flow's destination/port/
   protocol. Below threshold: log locally, no network call.
3. That's the whole file — no stdin/stdout protocol, no OS-specific
   installer, no registry/manifest registration.
   `com.securitycopilot.host.json`, `install.sh`, and `install.ps1`
   describe the old approach — delete them or leave them unused, your
   call, but don't build against them.

Run with `python native-host/host.py` alongside the backend. No
extension changes needed — the extension never talks to this directly.

**Done when:** a deliberately-anomalous flow (see Phase 9's staged
trigger) makes it from the collector through scoring to a real
`/report-flow` call and back with a verdict.

## Phase 5 — MITRE ATT&CK mapping

Build `mitre/build_index.py` and `mitre/lookup.py` per their own
docstrings:

1. Download MITRE ATT&CK technique + mitigation text as STIX data from
   https://github.com/mitre/cti.
2. Embed each technique's description with SecureBERT
   (https://huggingface.co/ehsanaghaei/SecureBERT — pretrained, no
   training required).
3. Store embeddings + metadata (id, name, mitigation text) in a plain
   in-memory numpy array with a sidecar JSON — no hosted vector DB
   needed at this scale. Persist so `lookup.py` doesn't re-embed on
   every process start.

Implement `lookup.py`'s two functions for real: `find_technique(
description)` embeds and returns the nearest technique by cosine
similarity; `get_mitigation_text(technique_id)` returns its mitigation
text.

**Shortcut worth taking:** `backend/data/playbooks/playbooks.json`
already has curated, well-written remediation text mapped to MITRE
technique IDs for common scenarios (phishing, credential theft, etc.).
Check there first in `get_mitigation_text` and only fall through to raw
STIX text if the technique isn't covered — better quality, and it means
this phase demos well even before Phase 5's STIX pipeline is fully
comprehensive.

Add whichever embedding library you use to `backend/requirements.txt`.

**Done when:** `find_technique()` returns a sensible technique for a few
hand-written test descriptions (e.g. "beaconing to a newly registered
domain every 30 seconds" should land somewhere in the
command-and-control or exfiltration techniques, not somewhere random).

## Phase 6 — wire MITRE context into `/report-flow`

Small, mechanical, do after Phase 5 exists: in
`routes_report_flow.py`, call `find_technique()` on the flow's
description and pass the result as `run_case`'s `mitre_technique`
argument, exactly as that file's own docstring already describes.

**Done when:** a `/report-flow` call's resulting verdict/report includes
a named MITRE technique, not just a bare anomaly score.

## Phase 7 — TranAD (stretch goal, build last of the detection work)

Only after Phases 2-6 are fully working end to end. Official repo:
https://github.com/imperial-qore/TranAD, paper:
https://arxiv.org/abs/2201.07284. Scores the *sequence* of windowed
feature vectors (same shape as Phase 2/3's), catching temporal patterns
a single-flow Isolation Forest score misses — beaconing, slow
exfiltration. Unsupervised, same bootstrap-then-personalize training
approach as Isolation Forest. A flow escalates if **either** model flags
it — update Phase 4's loop to check both once this exists.

**Done when:** TranAD trains against the same datasets as Phase 3 and,
run on a synthetic slow-exfiltration sequence (many small, individually
unremarkable transfers), flags it even when Isolation Forest alone
wouldn't.

## Phase 8 — personalize on the user's own traffic

Ongoing, starts once Phase 4 has been running for 2-4 weeks. CICIDS2017/
NSL-KDD model enterprise traffic, not this household's. Retrain
Isolation Forest (and TranAD, once built) on the user's own logged
traffic instead of — or blended with — the public dataset, recomputing
the percentile threshold against it.

1. **Exclude confirmed-malicious flows** from the retraining set — check
   each window against `history.db`'s recorded verdicts before including
   it, so the model doesn't learn a real attack as "normal."
2. **Needs a scheduled trigger**, not a one-off run — a cron job or a
   periodic check inside `host.py`'s loop calling
   `scripts/train_isolation_forest.py --input <fresh traffic>` is
   sufficient; it doesn't need to be sophisticated.

**Done when:** there's a working, even if manually-triggered-for-now,
path to retrain on personal data and have the threshold update
accordingly.

## Phase 9 — demo readiness

Not a code phase so much as a rehearsal pass, but worth doing
deliberately rather than leaving to chance:

1. **A staged trigger you control** — a small script that deliberately
   generates an anomalous-looking flow (a burst upload to an odd port, a
   connection to a throwaway test domain) so the network-anomaly path
   can be demoed live, on cue, without depending on real traffic doing
   something interesting at the right moment.
2. **A replay fallback** — a couple of pre-recorded attack flows from
   CICIDS2017 that can be fed through the pipeline if the live trigger
   has any hiccup, so there's a zero-risk backup.
3. Do one full run through both entry points (a known-bad test URL
   through the extension, and the staged network trigger) end to end,
   confirming both land on the same agent and both produce a full
   report in the web UI's history.

**Done when:** both demo paths have been run at least once, successfully,
by someone other than whoever wrote the code.

## Explicitly out of scope — decided, not forgotten

So "nothing remaining" is accurate rather than something quietly
dropped:

- **LogBERT / CyBERT** (raw enterprise log-text semantic analysis) —
  these need log sources (Windows Event Log, CloudTrail, syslog) this
  project doesn't capture. Real future work, not part of this build.
- **Whole-home-network monitoring** beyond the single machine running
  the native helper — would need router-level infrastructure (a mirror
  port or a Raspberry Pi tap) outside what a local helper process can
  reach. Documented direction, not this build.
- **Automatic per-link badging via a content script** — the extension
  was deliberately simplified to click-triggered only for the POC. Only
  revisit this if you specifically want that UX back; it's not a gap in
  what was planned, it's a decision already made.
