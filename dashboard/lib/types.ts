/**
 * Backend response shapes for the Security Copilot dashboard.
 *
 * Canonical source is the extension's `extension/src/types/index.ts` and the
 * backend endpoint contract — these mirror it (Verdict, RunSummary, the
 * /check-links-stream events). Only fields the backend actually returns are
 * modelled here; run detail is intentionally loose because the backend serves
 * it as an untyped dict (backend/history.py::get_run).
 */
export type VerdictLabel = 'dangerous' | 'suspicious' | 'safe' | 'inconclusive'

export interface LegitimateAlternative {
  title: string
  url: string
}

/** POST /check-email, and the per-URL values of POST /check-links. */
export interface Verdict {
  label: VerdictLabel
  confidence: number
  reason: string
  mitigation: string | null
  legitimate_alternatives: LegitimateAlternative[]
  run_id: string
}

/** One row from GET /runs (backend/history.py::list_runs). */
export interface RunSummary {
  id: string
  case_type: string
  raw_input: string
  created_at: number
  verdict: {
    label: VerdictLabel
    confidence: number
    reason?: string
  }
}

/**
 * GET /runs/{run_id} (backend/history.py::get_run). The stored verdict predates
 * the run_id wrapper the live routes add, and may be the "inconclusive" default,
 * so every verdict field is treated as optional here.
 */
export interface RunDetail {
  id: string
  case_type: string
  raw_input: string
  created_at: number
  verdict: {
    label?: VerdictLabel
    confidence?: number
    reason?: string
    mitigation?: string | null
    legitimate_alternatives?: LegitimateAlternative[]
  }
  tool_calls: unknown[]
  report_path: string | null
}

/** One Server-Sent Event from POST /check-links-stream. */
export type CheckLinksStreamEvent =
  | { type: 'progress'; label: string }
  | { type: 'done'; verdict: Omit<Verdict, 'run_id'>; run_id: string; report_path: string }
