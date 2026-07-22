/**
 * Canonical API types shared across the dashboard and extension.
 *
 * This file is the single source of truth for the shape of SentinelAI's
 * HTTP API from a TypeScript consumer's point of view — it mirrors the
 * backend's Pydantic schemas in `backend/app/schemas/` field-for-field.
 * `dashboard/src/types/index.ts` and `extension/src/types/index.ts`
 * currently maintain their own local copies (each package only needs a
 * subset, and keeping them dependency-free simplifies each package's
 * build); if the two projects are ever unified under a single
 * TypeScript project/workspace, importing directly from this file is
 * the intended next step. See docs/DEVELOPER_GUIDE.md, "Shared Types".
 */

// ---------------------------------------------------------------------------
// Enums (must stay in sync with backend/app/models/*.py)
// ---------------------------------------------------------------------------

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

export type ThreatIntelSource = "virustotal" | "abuseipdb" | "phishtank";

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface UserRegisterRequest {
  email: string;
  password: string;
}

export interface UserLoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface User {
  id: string;
  email: string;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Devices
// ---------------------------------------------------------------------------

export interface DeviceRegisterRequest {
  browser: string;
  os: string;
}

export interface Device {
  device_id: string;
  user_id: string;
  browser: string;
  os: string;
  last_seen: string;
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

export interface EventCreateRequest {
  device_id: string;
  event_type: EventType;
  payload: Record<string, unknown>;
  timestamp?: string;
}

export interface EventIngestResponse {
  accepted: number;
  incident_id: string | null;
  incident_created: boolean;
}

// ---------------------------------------------------------------------------
// Phishing detection
// ---------------------------------------------------------------------------

export interface PhishingCheckRequest {
  url: string;
  page_title?: string;
  page_text_snippet?: string;
  device_id?: string;
}

export interface PhishingCheckResponse {
  url: string;
  is_phishing: boolean;
  confidence: number;
  risk_label: "low" | "medium" | "high";
  reasons: string[];
  threat_intel_hit: boolean;
  incident_id: string | null;
}

// ---------------------------------------------------------------------------
// Network anomaly detection
// ---------------------------------------------------------------------------

export interface NetworkUploadResponse {
  rows_ingested: number;
  anomalies_detected: number;
  incidents_created: number;
  incident_ids: string[];
}

export interface ReplayStartRequest {
  dataset: "cicids2017" | "unsw-nb15";
  device_id?: string;
  max_rows?: number;
  speed?: number;
}

export interface ReplayStartResponse {
  replay_id: string;
  dataset: string;
  rows_scheduled: number;
  status: string;
}

// ---------------------------------------------------------------------------
// Incidents
// ---------------------------------------------------------------------------

export interface EvidenceEntry {
  evidence_id: string;
  incident_id: string;
  event_id: string;
  reason: string;
  score: number;
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

export interface IncidentUpdateRequest {
  status?: IncidentStatus;
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Playbooks
// ---------------------------------------------------------------------------

export interface Playbook {
  id: string;
  title: string;
  mitre_techniques: string[];
  content: string;
}

// ---------------------------------------------------------------------------
// Common envelopes
// ---------------------------------------------------------------------------

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
    request_id: string;
  };
}
