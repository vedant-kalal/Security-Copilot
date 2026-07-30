import { Activity, ExternalLink, Loader2, RefreshCw, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { getStorage } from "@/lib/storage";
import type { RunSummary } from "@/types";

type Label = RunSummary["verdict"]["label"];

function badgeClasses(label: Label): string {
  switch (label) {
    case "dangerous":
      return "bg-threat-critical/10 text-threat-critical";
    case "suspicious":
      return "bg-threat-medium/10 text-threat-medium";
    case "safe":
      return "bg-safe/10 text-safe";
    default:
      return "bg-panel-raised text-fog-dim";
  }
}

function relTime(epochSeconds: number): string {
  const diff = Date.now() / 1000 - epochSeconds;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(epochSeconds * 1000).toLocaleDateString();
}

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; runs: RunSummary[] };

export function AnomalyView() {
  const [state, setState] = useState<State>({ status: "loading" });

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const runs = await api.get<RunSummary[]>("/runs?view=anomaly&limit=30");
      setState({ status: "ready", runs });
    } catch (error) {
      setState({ status: "error", message: error instanceof ApiError ? error.message : "Could not load anomalies." });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function openReport(runId: string) {
    const { apiBaseUrl } = await getStorage();
    chrome.tabs.create({ url: `${apiBaseUrl}/?run=${runId}` });
  }

  return (
    <div>
      {/* Live monitor banner */}
      <div className="mb-3 flex items-center justify-between rounded-lg border border-panel-line bg-panel px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-pulse-glow rounded-full bg-sentinel opacity-70" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-sentinel shadow-glow-sentinel" />
          </span>
          <span className="font-mono text-[11px] text-fog-dim">Network anomalies from the backend monitor</span>
        </div>
        <button
          onClick={() => void load()}
          title="Refresh"
          className="rounded p-1 text-fog-faint transition-colors duration-200 hover:text-fog"
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
      </div>

      {state.status === "loading" && (
        <div className="flex items-center justify-center gap-2 py-8 text-xs text-fog-dim">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading anomalies...
        </div>
      )}

      {state.status === "error" && (
        <div className="flex items-start gap-2.5 rounded-lg border border-threat-critical/30 bg-threat-critical/10 p-3">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-threat-critical" />
          <p className="text-xs leading-relaxed text-threat-critical">{state.message}</p>
        </div>
      )}

      {state.status === "ready" && state.runs.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-10 text-center">
          <Activity className="h-8 w-8 text-fog-faint" />
          <p className="text-sm font-medium text-fog">No anomalies flagged</p>
          <p className="max-w-[280px] text-xs text-fog-faint">
            The backend network monitor hasn't escalated any flows. Anomalies appear here as they're detected.
          </p>
        </div>
      )}

      {state.status === "ready" && state.runs.length > 0 && (
        <div className="space-y-2">
          {state.runs.map((run) => (
            <button
              key={run.id}
              onClick={() => void openReport(run.id)}
              className="group flex w-full flex-col gap-1.5 rounded-lg border border-panel-line bg-panel p-3 text-left transition-all duration-200 hover:border-sentinel/30 hover:bg-panel-raised hover:shadow-glow-sentinel"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="line-clamp-2 font-mono text-[11px] leading-snug text-fog-dim">{run.raw_input}</span>
                <ExternalLink className="h-3 w-3 shrink-0 text-fog-faint opacity-0 transition-opacity group-hover:opacity-100" />
              </div>
              <div className="flex items-center justify-between">
                <span className={`rounded-full px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide ${badgeClasses(run.verdict.label)}`}>
                  {run.verdict.label}
                </span>
                <span className="font-mono text-[10px] text-fog-faint">{relTime(run.created_at)}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
