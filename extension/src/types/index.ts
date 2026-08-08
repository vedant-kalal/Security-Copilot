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
  source: "cache" | "blocklist" | "ml_model" | "virustotal" | "error";
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
  | { type: "FULL_CHECK_DONE"; runId: string; label: string; confidence: number }
  | { type: "FULL_CHECK_FAILED"; message: string };

export type ContentToBackgroundMessage = { type: "RUN_FULL_CHECK"; url: string };
