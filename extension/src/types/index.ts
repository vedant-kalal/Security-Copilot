export interface PhishingCheckResult {
  url: string;
  is_phishing: boolean;
  confidence: number;
  risk_label: "low" | "medium" | "high";
  reasons: string[];
  threat_intel_hit: boolean;
  incident_id: string | null;
}

export interface EventIngestResponse {
  accepted: number;
  incident_id: string | null;
  incident_created: boolean;
}

/** Messages passed between the content script, background service
 * worker, and popup/options UI via chrome.runtime messaging. */
export type RuntimeMessage =
  | { type: "FORM_SUBMISSION"; url: string; hasPasswordField: boolean }
  | { type: "GET_ACTIVE_TAB_VERDICT" }
  | { type: "AUTH_STATE_CHANGED" };
