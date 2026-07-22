/**
 * Shared TypeScript types mirroring the backend's Pydantic schemas
 * (see backend/app/schemas/). Kept as plain interfaces (no runtime
 * validation library) since the API is fully typed and controlled by
 * this same monorepo — see shared/types for the cross-package source.
 */

export type IncidentSeverity = "low" | "medium" | "high" | "critical";
export type IncidentStatus = "open" | "investigating" | "contained" | "resolved" | "dismissed";

export type EventType =
  | "page_navigation"
  | "url_visit"
  | "file_download"
  | "form_submission"
  | "login_attempt"
  | "network_flow"
  | "network_flow_replay"
  | "network_flow_upload";

export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface Device {
  device_id: string;
  user_id: string;
  browser: string;
  os: string;
  last_seen: string;
}

export interface EvidenceEntry {
  evidence_id: string;
  incident_id: string;
  event_id: string;
  reason: string;
  score: number;
  event?: {
    event_id: string;
    device_id: string;
    timestamp: string;
    event_type: EventType;
    payload_json: Record<string, unknown>;
  } | null;
}

export interface AIResponseEntry {
  response_id: string;
  incident_id: string;
  summary: string;
  recommendation: string;
  generated_at: string;
}

export interface Incident {
  incident_id: string;
  user_id: string;
  title: string;
  severity: IncidentSeverity;
  confidence: number;
  mitre: string[];
  status: IncidentStatus;
  summary: string;
  created_at: string;
}

export interface IncidentDetail extends Incident {
  evidence_entries: EvidenceEntry[];
  ai_responses: AIResponseEntry[];
}

export interface SeverityBreakdown {
  low: number;
  medium: number;
  high: number;
  critical: number;
}

export interface DashboardSummary {
  devices_protected: number;
  security_score: number;
  incidents_today: number;
  open_incidents: number;
  severity_breakdown: SeverityBreakdown;
  recent_incidents: Incident[];
}

export interface Playbook {
  id: string;
  title: string;
  mitre_techniques: string[];
  content: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface PhishingCheckResult {
  url: string;
  is_phishing: boolean;
  confidence: number;
  risk_label: "low" | "medium" | "high";
  reasons: string[];
  threat_intel_hit: boolean;
  incident_id: string | null;
}

export interface NetworkUploadResult {
  rows_ingested: number;
  anomalies_detected: number;
  incidents_created: number;
  incident_ids: string[];
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
    request_id: string;
  };
}
