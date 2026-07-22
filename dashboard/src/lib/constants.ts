export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export const ACCESS_TOKEN_STORAGE_KEY = "sentinelai_access_token";
export const REFRESH_TOKEN_STORAGE_KEY = "sentinelai_refresh_token";

export const SEVERITY_LABELS: Record<string, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

export const STATUS_LABELS: Record<string, string> = {
  open: "Open",
  investigating: "Investigating",
  contained: "Contained",
  resolved: "Resolved",
  dismissed: "Dismissed",
};
