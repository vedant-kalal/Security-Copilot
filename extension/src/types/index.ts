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
