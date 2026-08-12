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
import { getPendingFullCheck, getStorage, getTabVerdict, type PendingFullCheck, type TabVerdict } from "@/lib/storage";
import { isWebmailHost } from "@/lib/webmail";
import type { QuickCheckEmailResponse, ReportResponse } from "@/types";

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
  // `step` is a live label from background.ts's SSE consumption of
  // /check-links-stream or /check-email-stream (e.g. "Checking
  // VirusTotal...", "Exploring another page found on the site..."),
  // absent until the first progress event arrives — both kinds stream
  // now, an email investigation follows every link it found the same
  // way a link case follows a suspicious link on the page.
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

// Grabs both the visible text AND every real anchor href on the page —
// innerText alone misses "Click here"-style links entirely (the visible
// text has no URL in it at all; only the href does), which matters a lot
// more for an email than for a generic page-text check. `func` here runs
// injected into the tab, not this module — it can't close over anything
// from the outer scope, so the whole extraction has to be self-contained.
async function extractPageContent(tabId: number): Promise<{ text: string; links: string[] }> {
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const text = document.body.innerText;
        const links = Array.from(document.querySelectorAll("a[href]"))
          .map((a) => (a as HTMLAnchorElement).href)
          .filter((href) => href.startsWith("http"));
        return { text, links: Array.from(new Set(links)).slice(0, 40) };
      },
    });
    return result ?? { text: "", links: [] };
  } catch {
    return { text: "", links: [] };
  }
}

// Widened to TabVerdict["label"] | QuickCheckEmailResponse["label"] — the
// same rendering (a generic "unknown" look via the switch's default case)
// already covers "inconclusive" and "unknown" identically, so this is
// just making the signature honest about the two label sets that
// actually get passed to it, not a behavior change.
function labelMeta(label: TabVerdict["label"] | QuickCheckEmailResponse["label"]) {
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
  // The automatic "you're looking at an email" quick check (see the
  // useEffect below) — separate from `view` on purpose: it's an
  // auxiliary, always-fast BERT-only read of the page's text, shown
  // alongside the normal idle state rather than replacing it, and never
  // itself gets stored as a TabVerdict the way a real check does.
  const [quickEmailCheck, setQuickEmailCheck] = useState<
    null | { status: "checking" } | { status: "done"; result: QuickCheckEmailResponse; text: string; links: string[] }
  >(null);
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
          prev.status === "checking"
            ? { status: "error", tab: prev.tab, message: "Full check failed. Try again." }
            : prev,
        );
        return;
      }
      // A live step label landed (background.ts's runFullCheck /
      // runFullEmailCheck updates this on every SSE progress event) —
      // reflect it if this popup is currently showing the "checking"
      // state for the same check.
      const newPending = pendingChange.newValue as PendingFullCheck;
      if (newPending.url === currentUrl && newPending.step) {
        setView((prev) => (prev.status === "checking" ? { ...prev, step: newPending.step } : prev));
      }
    }

    chrome.storage.onChanged.addListener(onChanged);
    return () => chrome.storage.onChanged.removeListener(onChanged);
  }, [tab?.id, tab?.url]);

  // The email quick-check is offered whenever nothing more specific than
  // the passive per-navigation URL scan (kind "quick") has happened for
  // this tab yet. That automatic URL scan fires — and, on any reasonable
  // connection, finishes — on every navigation, including the webmail
  // site's own domain, well before a user could realistically open the
  // popup. Gating purely on view.status === "idle" would mean this
  // almost never triggers in practice: bootstrap() finds that cached URL
  // verdict first and jumps straight to "result", and the email-content
  // check (a completely different signal — about the open email, not
  // about mail.google.com's own domain) never gets a chance to run.
  const emailQuickCheckEligible =
    !!tab && isWebmailHost(tab.hostname) && (view.status === "idle" || (view.status === "result" && view.verdict.kind === "quick"));

  // The automatic webmail scan: the instant the popup opens on a
  // recognized webmail tab with nothing more specific already shown,
  // extract the page's text + real link hrefs and run them through the
  // fast BERT-only quick check — no click needed, the same way the
  // extension already shows an automatic quick verdict for the current
  // tab's URL on every navigation. Deliberately NOT fully passive/
  // background like that URL autoscan, though: this only runs when the
  // user actually opens the popup, since it means sending this page's
  // visible text to the backend, which shouldn't happen on every email a
  // user merely has open in a tab.
  useEffect(() => {
    if (!emailQuickCheckEligible || !tab) return;
    let cancelled = false;
    setQuickEmailCheck({ status: "checking" });
    void (async () => {
      const extracted = await extractPageContent(tab.id);
      if (cancelled) return;
      const text = extracted.text.slice(0, MAX_PAGE_TEXT_CHARS);
      if (!text.trim()) {
        setQuickEmailCheck(null);
        return;
      }
      try {
        const result = await api.post<QuickCheckEmailResponse>("/quick-check-email", { text });
        if (!cancelled) setQuickEmailCheck({ status: "done", result, text, links: extracted.links });
      } catch {
        // A quick-check failure should never block using the popup —
        // same principle as background.ts's scanNavigation.
        if (!cancelled) setQuickEmailCheck(null);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emailQuickCheckEligible, tab?.id]);

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
      setView({ status: "checking", tab, kind: pending.kind, step: pending.step });
      return;
    }

    const cached = await getTabVerdict(tab.id);
    if (cached && cached.checkedUrl === tab.url) {
      setView({ status: "result", tab, verdict: cached });
      return;
    }

    setView({ status: "idle", tab });
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

  // Shared by the manual "Check page text" button (any page other than a
  // recognized webmail tab) and the automatic webmail quick-check's
  // "Check this email" button — both end up wanting the same thing: hand
  // text + links to background.ts's
  // runFullEmailCheck, which streams the real investigation (every
  // extracted link gets its own inspect_website + domain_reputation look,
  // not just the email's wording) the same reliable, survives-a-closed-
  // popup way handleCheckUrl already does for a link case.
  async function runFullEmailScan(tab: ActiveTab, text: string, links: string[]) {
    setView({ status: "checking", tab, kind: "email" });
    try {
      await chrome.runtime.sendMessage({ type: "RUN_FULL_EMAIL_CHECK", text, links, pageUrl: tab.url, tabId: tab.id });
    } catch {
      setView({ status: "error", tab, message: "Could not start the check. Try again." });
    }
  }

  async function handleCheckText(tab: ActiveTab) {
    setView({ status: "checking", tab, kind: "email" });
    const extracted = await extractPageContent(tab.id);
    const text = extracted.text.slice(0, MAX_PAGE_TEXT_CHARS);
    if (!text.trim()) {
      setView({ status: "error", tab, message: "This page has no readable text to check." });
      return;
    }
    await runFullEmailScan(tab, text, extracted.links);
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

                <div className={emailQuickCheckEligible ? "grid grid-cols-1 gap-3" : "grid grid-cols-2 gap-3"}>
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
                  {/* Hidden on a webmail tab once the quick-check panel below is */}
                  {/* showing — its "Check this email" button does the exact same */}
                  {/* thing (extract text + links, run the full investigation), */}
                  {/* just correctly framed as checking the email rather than the */}
                  {/* generic page. Having both was confusing: two differently- */}
                  {/* labeled buttons that trigger the identical flow. */}
                  {!emailQuickCheckEligible && (
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
                  )}
                </div>

                {view.status === "checking" && (
                  <div className="mt-4 rounded-lg scan-bg animate-scan px-4 py-2.5 text-center">
                    <p className="flex items-center justify-center gap-2 font-mono text-xs text-fog-dim">
                      <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
                      {view.step ?? "Starting investigation..."}
                    </p>
                  </div>
                )}

                {/* Automatic webmail quick-check — a recognized webmail tab with */}
                {/* nothing more specific than the passive URL scan shown yet */}
                {emailQuickCheckEligible && (
                  <div className="mt-4">
                    {quickEmailCheck?.status === "checking" && (
                      <div className="flex items-center gap-2 rounded-lg border border-panel-line bg-panel-raised/50 px-3 py-2.5 text-xs text-fog-dim">
                        <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                        Scanning this email...
                      </div>
                    )}
                    {quickEmailCheck?.status === "done" &&
                      (() => {
                        const { Icon, color, bg, border } = labelMeta(quickEmailCheck.result.label);
                        const { result, text, links } = quickEmailCheck;
                        return (
                          <div className={`rounded-lg border ${border} ${bg} p-3`}>
                            <div className="flex items-center gap-2">
                              <Icon className={`h-4 w-4 shrink-0 ${color}`} />
                              <p className={`text-xs font-semibold capitalize ${color}`}>
                                {result.label === "unknown" ? "Quick scan unavailable" : `Quick scan: ${result.label}`}
                              </p>
                            </div>
                            <button
                              onClick={() => runFullEmailScan(tab, text, links)}
                              className="mt-2.5 flex w-full items-center justify-center gap-2 rounded-lg border border-panel-line bg-panel py-2 text-xs font-medium text-fog transition-all duration-200 hover:border-accent/30 hover:bg-panel-raised hover:shadow-glow-accent"
                            >
                              <FileText className="h-3.5 w-3.5 text-accent" />
                              Check this email
                            </button>
                          </div>
                        );
                      })()}
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
