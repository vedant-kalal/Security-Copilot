/** Mirrors backend/agent/state.py's Verdict TypedDict, plus the run_id
 * every route in backend/api/routes_check_*.py adds on top of it. */
export interface LegitimateAlternative {
  title: string;
  url: string;
}

export interface Verdict {
  label: "dangerous" | "suspicious" | "safe" | "inconclusive";
  confidence: number;
  reason: string;
  mitigation: string | null;
  legitimate_alternatives: LegitimateAlternative[];
  run_id: string;
}

/** POST /check-links response (api/schemas.py::CheckLinksResponse) — keyed by the URL that was submitted. */
export interface CheckLinksResponse {
  results: Record<string, Verdict>;
}

/** One Server-Sent Event from POST /check-links-stream
 * (api/routes_check_links_stream.py) — a live play-by-play of the actual
 * agent steps (agent/graph.py's stream_case_traced) instead of one
 * blocking response, so the "Full report" flow can show what's actually
 * happening instead of a static spinner. A stream is one or more
 * "progress" events followed by exactly one "done" event carrying the
 * same shape /check-links' response would have had for this URL. */
export type CheckLinksStreamEvent =
  | { type: "progress"; label: string }
  | { type: "done"; verdict: Omit<Verdict, "run_id">; run_id: string; report_path: string };

/** POST /check-email returns a bare Verdict (api/routes_check_email.py). */
export type CheckEmailResponse = Verdict;

/** One row from GET /runs (history.py::list_runs) — used by the anomaly viewer. */
export interface RunSummary {
  id: string;
  case_type: string;
  raw_input: string;
  created_at: number;
  verdict: {
    label: "dangerous" | "suspicious" | "safe" | "inconclusive";
    confidence: number;
    reason?: string;
  };
}

/** POST /quick-check-url response (api/routes_quick_check.py) — the fast,
 * local pre-check background.ts runs on every navigation — the ONNX URL
 * model, corroborated with a (cached) VirusTotal lookup when the model
 * alone doesn't already say "dangerous" (see routes_quick_check.py's
 * docstring for why: the model alone misses real phishing sites VT already
 * has signal on). No run_id: it never touches history.py, only the full
 * agent does that. */
export interface QuickCheckResponse {
  label: "dangerous" | "suspicious" | "safe" | "unknown";
  confidence: number;
  source: "cache" | "blocklist" | "ml_model" | "virustotal" | "page_signal" | "error";
  detail?: string;
}

/** POST /quick-check-email response (api/routes_quick_check_email.py) —
 * a single BERT text-classification pass, no agent loop, no links
 * investigated. What the popup runs automatically the instant it opens
 * on a recognized webmail tab (see lib/webmail.ts); "Run full scan"
 * escalates to the real agent via RUN_FULL_EMAIL_CHECK below, which does
 * investigate every link. */
export interface QuickCheckEmailResponse {
  label: "dangerous" | "suspicious" | "safe" | "unknown";
  confidence: number;
  source: "ml_model" | "error";
  detail?: string;
}

/** Messages passed between background.ts (which owns navigation events and
 * the backend calls) and content.ts (which owns the in-page banner). */
export type BackgroundToContentMessage =
  | {
      type: "SHOW_BANNER";
      url: string;
      label: "dangerous" | "suspicious" | "safe";
      confidence: number;
      source: QuickCheckResponse["source"];
    }
  | { type: "HIDE_BANNER" }
  | { type: "FULL_CHECK_STARTED" }
  // One per step the agent actually takes (see graph.py's
  // stream_case_traced) — "Opening the page...", "Checking VirusTotal...",
  // etc. Arrives zero or more times between FULL_CHECK_STARTED and
  // FULL_CHECK_DONE/FAILED.
  | { type: "FULL_CHECK_PROGRESS"; label: string }
  | { type: "FULL_CHECK_DONE"; runId: string; label: string; confidence: number }
  | { type: "FULL_CHECK_FAILED"; message: string };

export type ContentToBackgroundMessage =
  // tabId is only set when this comes from the popup — content scripts
  // don't know their own tab id, but the background can read it off
  // sender.tab.id for those; the popup has no sender.tab at all (it's an
  // extension page, not injected into the tab), so it has to say which
  // tab explicitly.
  | { type: "RUN_FULL_CHECK"; url: string; tabId?: number }
  // From the popup — either the automatic webmail quick-check's "Run full
  // scan" button, or the general-purpose "Check page text" button (any
  // page, not just recognized webmail). `links` are real anchor hrefs
  // already extracted from the DOM (see Popup.tsx's extractPageContent) —
  // the same union-with-regex-extraction the backend does for a plain
  // pasted email applies here too, but DOM hrefs catch "click here"-style
  // links a text-only regex never could. `pageUrl` is the tab's URL at
  // the time of the check — reused as the TabVerdict/PendingFullCheck key
  // (see storage.ts) so reopening the popup on the same page restores the
  // result exactly the way a link check's does, and always sent
  // explicitly since this message only ever comes from the popup, which
  // has no sender.tab of its own to fall back on.
  | { type: "RUN_FULL_EMAIL_CHECK"; text: string; links: string[]; pageUrl: string; tabId?: number }
  // Sent only when the content script finds a password field inside a
  // form whose action posts to a different site than the page itself —
  // see content/index.ts's computePageSignals(). Not sent otherwise, so
  // its mere arrival already means something's worth a second look.
  | { type: "PAGE_SIGNALS"; url: string; actionDomain: string }
  // From the popup, right after a successful POST /report — tells
  // background.ts to re-fetch GET /blocklist immediately instead of
  // waiting for its periodic chrome.alarms sync, so the domain just
  // reported is enforced on the very next navigation, not several
  // minutes later.
  | { type: "REFRESH_BLOCKLIST" }
  // From blocked/Blocked.tsx's "Proceed anyway" — background.ts records
  // this exact URL as a one-time exception before Blocked.tsx navigates
  // there itself, so onBeforeNavigate lets that one attempt through
  // instead of immediately redirecting back to the same interstitial.
  | { type: "ALLOW_ONCE"; url: string };

/** POST /report response (backend/api/routes_report.py). */
export interface ReportResponse {
  domain: string;
  added_to_blocklist: boolean;
  virustotal: { reported: boolean; detail: string };
}
