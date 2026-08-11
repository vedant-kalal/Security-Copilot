import {
  Activity,
  AlertTriangle,
  Ban,
  ExternalLink,
  FileText,
  Fish,
  Link2,
  Loader2,
  RotateCcw,
  Settings,
  ShieldAlert,
  ShieldCheck,
  ShieldHalf,
  ShieldQuestion,
} from "lucide-react";
import { useEffect, useState } from "react";

import { AnomalyView } from "@/popup/AnomalyView";
import { ThemeToggle } from "@/components/ThemeToggle";
import { api, ApiError } from "@/lib/api";
import { getPendingFullCheck, getStorage, getTabVerdict, setTabVerdict, type PendingFullCheck, type TabVerdict } from "@/lib/storage";
import type { CheckEmailResponse, ReportResponse } from "@/types";

type ReportState =
  | { url: string; status: "idle" }
  | { url: string; status: "loading" }
  | { url: string; status: "done"; result: ReportResponse }
  | { url: string; status: "error"; message: string };

const MAX_PAGE_TEXT_CHARS = 20000;

type Mode = "phishing" | "anomaly";

interface ActiveTab {
  id: number;
  url: string;
  hostname: string;
}

type View =
  | { status: "loading" }
  | { status: "unsupported" }
  | { status: "idle"; tab: ActiveTab }
  // `step` is only ever populated for kind "link" — a live label from
  // background.ts's SSE consumption of /check-links-stream (e.g.
  // "Checking VirusTotal..."), absent until the first progress event
  // arrives. "email" checks aren't step-by-step (a single /check-email
  // call, no streaming) so they just show the generic scanning message.
  | { status: "checking"; tab: ActiveTab; kind: "link" | "email"; step?: string }
  | { status: "result"; tab: ActiveTab; verdict: TabVerdict }
  | { status: "error"; tab: ActiveTab; message: string };

function hostnameOf(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

function labelMeta(label: TabVerdict["label"]) {
  switch (label) {
    case "dangerous":
      return { Icon: ShieldAlert, color: "text-threat-critical", bg: "bg-threat-critical/10", border: "border-threat-critical/30", glow: "shadow-glow-critical" };
    case "suspicious":
      return { Icon: AlertTriangle, color: "text-threat-medium", bg: "bg-threat-medium/10", border: "border-threat-medium/30", glow: "shadow-glow-medium" };
    case "safe":
      return { Icon: ShieldCheck, color: "text-safe", bg: "bg-safe/10", border: "border-safe/30", glow: "shadow-glow-safe" };
    default:
      return { Icon: ShieldQuestion, color: "text-fog-dim", bg: "bg-panel-raised", border: "border-panel-line", glow: "" };
  }
}

export function Popup() {
  const [mode, setMode] = useState<Mode>("phishing");
  const [view, setView] = useState<View>({ status: "loading" });
  const [reportState, setReportState] = useState<ReportState>({ url: "", status: "idle" });
  const tab = "tab" in view ? view.tab : null;

  useEffect(() => {
    void bootstrap();
  }, []);

  // A "Full report" run started from the banner (or from this popup on a
  // previous open) lives in the background service worker, not in this
  // popup — popups close the instant they lose focus, so this component
  // can't just await a fetch itself and expect to still be around when it
  // resolves. Instead it watches chrome.storage.session for the same
  // writes background.ts's runFullCheck already makes, and reflects
  // whatever it finds — whether or not this popup instance is the one
  // that started the check.
  useEffect(() => {
    if (!tab) return;
    const tabId = tab.id;
    const currentUrl = tab.url;

    function onChanged(changes: Record<string, chrome.storage.StorageChange>, areaName: string) {
      if (areaName !== "session") return;
      const verdictChange = changes[`tab_verdict_${tabId}`];
      if (verdictChange) {
        const newVerdict = verdictChange.newValue as TabVerdict | undefined;
        if (newVerdict && newVerdict.checkedUrl === currentUrl) {
          setView({ status: "result", tab: { id: tabId, url: currentUrl, hostname: hostnameOf(currentUrl) }, verdict: newVerdict });
        }
        return;
      }
      const pendingChange = changes[`pending_full_check_${tabId}`];
      if (!pendingChange) return;
      if (pendingChange.newValue === undefined) {
        // Pending check cleared with no verdict update alongside it (that
        // case is handled above) means the check failed — but only worth
        // reporting if this popup was actually shown as waiting on it.
        setView((prev) =>
          prev.status === "checking" && prev.kind === "link"
            ? { status: "error", tab: prev.tab, message: "Full check failed. Try again." }
            : prev,
        );
        return;
      }
      // A live step label landed (background.ts's runFullCheck updates
      // this on every SSE progress event) — reflect it if this popup is
      // currently showing the "checking" state for the same check.
      const newPending = pendingChange.newValue as PendingFullCheck;
      if (newPending.url === currentUrl && newPending.step) {
        setView((prev) => (prev.status === "checking" && prev.kind === "link" ? { ...prev, step: newPending.step } : prev));
      }
    }

    chrome.storage.onChanged.addListener(onChanged);
    return () => chrome.storage.onChanged.removeListener(onChanged);
  }, [tab?.id, tab?.url]);

  async function bootstrap() {
    const [chromeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!chromeTab?.id || !chromeTab.url || !chromeTab.url.startsWith("http")) {
      setView({ status: "unsupported" });
      return;
    }
    const tab: ActiveTab = { id: chromeTab.id, url: chromeTab.url, hostname: hostnameOf(chromeTab.url) };

    // Checked before the cached verdict below, deliberately: the automatic
    // quick-scan sets a (kind: "quick") verdict on essentially every
    // navigation, almost always well before the user could open this
    // popup — so if that check ran first, a full check already running in
    // the background (started from the banner, or from a previous popup
    // open that got closed before it finished) would never be reflected,
    // and the user would see a stale quick-scan result with no indication
    // anything is in progress.
    const pending = await getPendingFullCheck(tab.id);
    if (pending && pending.url === tab.url) {
      setView({ status: "checking", tab, kind: "link", step: pending.step });
      return;
    }

    const cached = await getTabVerdict(tab.id);
    if (cached && cached.checkedUrl === tab.url) {
      setView({ status: "result", tab, verdict: cached });
      return;
    }

    setView({ status: "idle", tab });
  }

  async function applyVerdict(tab: ActiveTab, verdict: TabVerdict) {
    await setTabVerdict(tab.id, verdict);
    // The tab can close mid-investigation (a 10-30s full check) — badging a
    // tab that no longer exists throws, but that's not a reason to treat an
    // otherwise-successful verdict as a failure, so it's isolated here.
    try {
      await chrome.action.setBadgeText({
        tabId: tab.id,
        text: verdict.label === "dangerous" || verdict.label === "suspicious" ? "!" : "",
      });
      await chrome.action.setBadgeBackgroundColor({
        tabId: tab.id,
        color: verdict.label === "dangerous" ? "#EF4444" : "#F5A623",
      });
    } catch {
      // Tab closed before the badge could be set — the verdict itself is
      // still valid and gets shown/stored below.
    }
    setView({ status: "result", tab, verdict });
  }

  async function handleCheckUrl(tab: ActiveTab) {
    setView({ status: "checking", tab, kind: "link" });
    // The actual /check-links call now runs in the background service
    // worker (background.ts's runFullCheck), not here — a full
    // investigation can take 10-40s, and this popup closes the instant it
    // loses focus, which would silently abandon a check run locally the
    // same way the banner's "Full report" button used to get stuck. The
    // result comes back through the storage.onChanged listener above,
    // whether or not this exact popup instance is still open when it
    // lands. This also means a check already running (started from the
    // banner) is naturally deduped — see runFullCheck's pending-check
    // guard — instead of firing a second, redundant one.
    try {
      await chrome.runtime.sendMessage({ type: "RUN_FULL_CHECK", url: tab.url, tabId: tab.id });
    } catch {
      setView({ status: "error", tab, message: "Could not start the check. Try again." });
    }
  }

  async function handleCheckText(tab: ActiveTab) {
    setView({ status: "checking", tab, kind: "email" });
    try {
      const [{ result: pageText }] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => document.body.innerText,
      });
      const text = (pageText ?? "").slice(0, MAX_PAGE_TEXT_CHARS);
      if (!text.trim()) {
        setView({ status: "error", tab, message: "This page has no readable text to check." });
        return;
      }

      const v = await api.post<CheckEmailResponse>("/check-email", { text });
      await applyVerdict(tab, {
        checkedUrl: tab.url,
        kind: "email",
        label: v.label,
        confidence: v.confidence,
        reason: v.reason,
        mitigation: v.mitigation,
        legitimateAlternatives: v.legitimate_alternatives,
        runId: v.run_id,
        checkedAt: Date.now(),
      });
    } catch (error) {
      setView({ status: "error", tab, message: error instanceof ApiError ? error.message : "Check failed." });
    }
  }

  async function handleViewReport(runId: string) {
    const { dashboardBaseUrl } = await getStorage();
    chrome.tabs.create({ url: `${dashboardBaseUrl}/run/${runId}` });
  }

  // Reports the URL to VirusTotal and adds its domain to this tool's own
  // blocklist (backend/reporting.py's module docstring has the full
  // reasoning: this is the legal, effective alternative to attacking the
  // site back). REFRESH_BLOCKLIST tells background.ts to re-sync its
  // local copy immediately, so onBeforeNavigate enforces this domain on
  // the very next navigation rather than waiting for the periodic alarm.
  async function handleReportBlock(url: string) {
    setReportState({ url, status: "loading" });
    try {
      const result = await api.post<ReportResponse>("/report", { url });
      setReportState({ url, status: "done", result });
      void chrome.runtime.sendMessage({ type: "REFRESH_BLOCKLIST" });
    } catch (error) {
      setReportState({ url, status: "error", message: error instanceof ApiError ? error.message : "Report failed." });
    }
  }

  return (
    <div className="flex flex-col">
      {/* ── Header ──────────────────────────────────────────────── */}
      <header className="flex items-center gap-2.5 gradient-border-b px-5 py-3.5">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-sentinel/15">
          <ShieldHalf className="h-4.5 w-4.5 text-sentinel" />
        </div>
        <span className="font-display text-sm font-bold tracking-wide">security-copilot</span>
        <div className="ml-auto flex items-center gap-1">
          <ThemeToggle />
          <button
            className="rounded-md p-1.5 text-fog-faint transition-colors duration-200 hover:bg-panel-raised hover:text-fog"
            title="Settings"
            onClick={() => chrome.runtime.openOptionsPage()}
          >
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </header>

      {/* ── Mode tabs ───────────────────────────────────────────── */}
      <div className="flex gap-2 px-5 pb-1 pt-3">
        <button
          onClick={() => setMode("phishing")}
          className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg border py-2 text-xs font-semibold tracking-wide transition-all duration-200 ${
            mode === "phishing"
              ? "border-accent bg-accent/10 text-accent shadow-glow-accent"
              : "border-panel-line text-fog-dim hover:text-fog"
          }`}
        >
          <Fish className="h-3.5 w-3.5" />
          Phishing
        </button>
        <button
          onClick={() => setMode("anomaly")}
          className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg border py-2 text-xs font-semibold tracking-wide transition-all duration-200 ${
            mode === "anomaly"
              ? "border-sentinel bg-sentinel/10 text-sentinel shadow-glow-sentinel"
              : "border-panel-line text-fog-dim hover:text-fog"
          }`}
        >
          <Activity className="h-3.5 w-3.5" />
          Anomaly
        </button>
      </div>

      {/* ── Body ────────────────────────────────────────────────── */}
      <div className="p-5">
        {mode === "anomaly" ? (
          <AnomalyView />
        ) : (
          <>
            {view.status === "loading" && <p className="py-10 text-center text-sm text-fog-dim">Loading...</p>}

            {view.status === "unsupported" && (
              <p className="py-10 text-center text-sm text-fog-dim">Open a regular http(s) page to run a check.</p>
            )}

            {tab && (
              <>
                <p className="mb-4 truncate rounded-md bg-panel-raised/50 px-3 py-1.5 font-mono text-xs text-fog-faint" title={tab.url}>
                  {tab.hostname}
                </p>

                <div className="grid grid-cols-2 gap-3">
                  <button
                    disabled={view.status === "checking"}
                    onClick={() => handleCheckUrl(tab)}
                    className="flex items-center justify-center gap-2 rounded-lg border border-panel-line bg-panel py-2.5 text-xs font-medium text-fog transition-all duration-200 hover:border-sentinel/30 hover:bg-panel-raised hover:shadow-glow-sentinel disabled:opacity-40"
                  >
                    {view.status === "checking" && view.kind === "link" ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Link2 className="h-3.5 w-3.5 text-sentinel" />
                    )}
                    Check this URL
                  </button>
                  <button
                    disabled={view.status === "checking"}
                    onClick={() => handleCheckText(tab)}
                    className="flex items-center justify-center gap-2 rounded-lg border border-panel-line bg-panel py-2.5 text-xs font-medium text-fog transition-all duration-200 hover:border-accent/30 hover:bg-panel-raised hover:shadow-glow-accent disabled:opacity-40"
                  >
                    {view.status === "checking" && view.kind === "email" ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <FileText className="h-3.5 w-3.5 text-accent" />
                    )}
                    Check page text
                  </button>
                </div>

                {view.status === "checking" && (
                  <div className="mt-4 rounded-lg scan-bg animate-scan px-4 py-2.5 text-center">
                    <p className="flex items-center justify-center gap-2 font-mono text-xs text-fog-dim">
                      {view.kind === "link" && <Loader2 className="h-3 w-3 shrink-0 animate-spin" />}
                      {view.kind === "link" ? (view.step ?? "Starting investigation...") : "Analyzing page text..."}
                    </p>
                  </div>
                )}

                {view.status === "error" && (
                  <div className="mt-4 flex items-start gap-2.5 rounded-lg border border-threat-critical/30 bg-threat-critical/10 p-3 shadow-glow-critical">
                    <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-threat-critical" />
                    <p className="text-xs leading-relaxed text-threat-critical">{view.message}</p>
                  </div>
                )}

                {view.status === "result" &&
                  (() => {
                    const { Icon, color, bg, border, glow } = labelMeta(view.verdict.label);
                    return (
                      <div className="mt-4 space-y-3">
                        {/* Verdict banner */}
                        <div className={`glass flex items-start gap-3 rounded-lg border ${border} ${bg} p-4 ${glow}`}>
                          <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${color}`} />
                          <div>
                            <p className={`text-sm font-bold capitalize ${color}`}>{view.verdict.label}</p>
                            <p className="mt-0.5 font-mono text-xs text-fog-faint">
                              {view.verdict.kind === "link"
                                ? "URL check"
                                : view.verdict.kind === "email"
                                  ? "Page text check"
                                  : "Automatic quick scan"}{" "}
                              &middot; {Math.round(view.verdict.confidence * 100)}% confidence
                            </p>
                          </div>
                        </div>

                        {/* Reason */}
                        <p className="text-xs leading-relaxed text-fog-dim">{view.verdict.reason}</p>

                        {/* Mitigation */}
                        {view.verdict.mitigation && (
                          <p className="border-t border-panel-line pt-3 text-xs leading-relaxed text-fog-faint">{view.verdict.mitigation}</p>
                        )}

                        {/* Legitimate alternatives */}
                        {view.verdict.legitimateAlternatives.length > 0 && (
                          <div className="border-t border-panel-line pt-3">
                            <p className="mb-1.5 text-xs font-medium text-fog-faint">This might be an impersonation of:</p>
                            {view.verdict.legitimateAlternatives.map((alt) => (
                              <a
                                key={alt.url}
                                href={alt.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="block truncate text-xs text-sentinel transition-colors duration-200 hover:text-sentinel-glow hover:underline"
                              >
                                {alt.title}
                              </a>
                            ))}
                          </div>
                        )}

                        {/* Action buttons */}
                        <div className="grid grid-cols-2 gap-3 pt-1">
                          <button
                            onClick={() => handleViewReport(view.verdict.runId!)}
                            disabled={!view.verdict.runId}
                            className="flex items-center justify-center gap-2 rounded-lg border border-panel-line bg-panel py-2.5 text-xs font-medium text-fog transition-all duration-200 hover:border-sentinel/30 hover:bg-panel-raised hover:shadow-glow-sentinel disabled:opacity-40"
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                            Full report
                          </button>
                          <button
                            onClick={() => setView({ status: "idle", tab })}
                            className="flex items-center justify-center gap-2 rounded-lg border border-panel-line bg-panel py-2.5 text-xs font-medium text-fog-dim transition-all duration-200 hover:bg-panel-raised"
                          >
                            <RotateCcw className="h-3.5 w-3.5" />
                            Dismiss
                          </button>
                        </div>

                        {/* Report & block — only for a real, confirmed-bad verdict */}
                        {(view.verdict.label === "dangerous" || view.verdict.label === "suspicious") &&
                          (() => {
                            const url = view.verdict.checkedUrl;
                            const rs = reportState.url === url ? reportState : { url, status: "idle" as const };
                            if (rs.status === "done") {
                              return (
                                <p className="flex items-center gap-2 pt-1 text-xs text-fog-faint">
                                  <Ban className="h-3.5 w-3.5 shrink-0 text-threat-critical" />
                                  {rs.result.added_to_blocklist ? "Blocked" : "Already blocked"} on this device
                                  {rs.result.virustotal.reported ? " and reported to VirusTotal." : "."}
                                </p>
                              );
                            }
                            return (
                              <div className="pt-1">
                                <button
                                  disabled={rs.status === "loading"}
                                  onClick={() => handleReportBlock(url)}
                                  className="flex w-full items-center justify-center gap-2 rounded-lg border border-threat-critical/30 bg-threat-critical/5 py-2.5 text-xs font-medium text-threat-critical transition-all duration-200 hover:bg-threat-critical/10 disabled:opacity-40"
                                >
                                  {rs.status === "loading" ? (
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  ) : (
                                    <Ban className="h-3.5 w-3.5" />
                                  )}
                                  Report & block this site
                                </button>
                                {rs.status === "error" && <p className="mt-1.5 text-xs text-threat-critical">{rs.message}</p>}
                              </div>
                            );
                          })()}
                      </div>
                    );
                  })()}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
