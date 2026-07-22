/** Canonical display labels, shared across dashboard and extension. */

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

export const SEVERITY_ORDER = ["critical", "high", "medium", "low"] as const;
