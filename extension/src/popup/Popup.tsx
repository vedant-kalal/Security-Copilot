import {
  AlertTriangle,
  ExternalLink,
  FileText,
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

import { api, ApiError } from "@/lib/api";
import { getStorage, getTabVerdict, setTabVerdict, type TabVerdict } from "@/lib/storage";
import type { CheckEmailResponse, CheckLinksResponse } from "@/types";

const MAX_PAGE_TEXT_CHARS = 20000;

interface ActiveTab {
  id: number;
  url: string;
  hostname: string;
}

type View =
  | { status: "loading" }
  | { status: "unsupported" }
  | { status: "idle"; tab: ActiveTab }
  | { status: "checking"; tab: ActiveTab; kind: "link" | "email" }
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
      return { Icon: ShieldAlert, color: "text-threat-critical", bg: "bg-threat-critical/10", border: "border-threat-critical/30" };
    case "suspicious":
      return { Icon: AlertTriangle, color: "text-threat-medium", bg: "bg-threat-medium/10", border: "border-threat-medium/30" };
    case "safe":
      return { Icon: ShieldCheck, color: "text-sentinel", bg: "bg-sentinel/10", border: "border-sentinel/30" };
    default:
      return { Icon: ShieldQuestion, color: "text-fog-dim", bg: "bg-panel-raised", border: "border-panel-line" };
  }
}

export function Popup() {
  const [view, setView] = useState<View>({ status: "loading" });

  useEffect(() => {
    void bootstrap();
  }, []);

  async function bootstrap() {
    const [chromeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!chromeTab?.id || !chromeTab.url || !chromeTab.url.startsWith("http")) {
      setView({ status: "unsupported" });
      return;
    }
    const tab: ActiveTab = { id: chromeTab.id, url: chromeTab.url, hostname: hostnameOf(chromeTab.url) };

    const cached = await getTabVerdict(tab.id);
    if (cached && cached.checkedUrl === tab.url) {
      setView({ status: "result", tab, verdict: cached });
    } else {
      setView({ status: "idle", tab });
    }
  }

  async function applyVerdict(tab: ActiveTab, verdict: TabVerdict) {
    await setTabVerdict(tab.id, verdict);
    await chrome.action.setBadgeText({
      tabId: tab.id,
      text: verdict.label === "dangerous" || verdict.label === "suspicious" ? "!" : "",
    });
    await chrome.action.setBadgeBackgroundColor({
      tabId: tab.id,
      color: verdict.label === "dangerous" ? "#EF4444" : "#F5A623",
    });
    setView({ status: "result", tab, verdict });
  }

  async function handleCheckUrl(tab: ActiveTab) {
    setView({ status: "checking", tab, kind: "link" });
    try {
      const { results } = await api.post<CheckLinksResponse>("/check-links", { urls: [tab.url] });
      const v = results[tab.url];
      await applyVerdict(tab, {
        checkedUrl: tab.url,
        kind: "link",
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
    const { apiBaseUrl } = await getStorage();
    chrome.tabs.create({ url: `${apiBaseUrl}/?run=${runId}` });
  }

  const tab = "tab" in view ? view.tab : null;

  return (
    <div className="flex flex-col">
      <header className="flex items-center gap-2 border-b border-panel-line px-4 py-3">
        <ShieldHalf className="h-5 w-5 text-sentinel" />
        <span className="font-display text-sm font-semibold">security-copilot</span>
        <button
          className="ml-auto text-fog-faint hover:text-fog"
          title="Settings"
          onClick={() => chrome.runtime.openOptionsPage()}
        >
          <Settings className="h-4 w-4" />
        </button>
      </header>

      <div className="p-4">
        {view.status === "loading" && <p className="py-8 text-center text-sm text-fog-dim">Loading...</p>}

        {view.status === "unsupported" && (
          <p className="py-8 text-center text-sm text-fog-dim">Open a regular http(s) page to run a check.</p>
        )}

        {tab && (
          <>
            <p className="mb-3 truncate font-mono text-xs text-fog-faint" title={tab.url}>
              {tab.hostname}
            </p>

            <div className="grid grid-cols-2 gap-2">
              <button
                disabled={view.status === "checking"}
                onClick={() => handleCheckUrl(tab)}
                className="flex items-center justify-center gap-1.5 rounded-md border border-panel-line py-2 text-xs font-medium text-fog hover:bg-panel-raised disabled:opacity-50"
              >
                {view.status === "checking" && view.kind === "link" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Link2 className="h-3.5 w-3.5" />
                )}
                Check this URL
              </button>
              <button
                disabled={view.status === "checking"}
                onClick={() => handleCheckText(tab)}
                className="flex items-center justify-center gap-1.5 rounded-md border border-panel-line py-2 text-xs font-medium text-fog hover:bg-panel-raised disabled:opacity-50"
              >
                {view.status === "checking" && view.kind === "email" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <FileText className="h-3.5 w-3.5" />
                )}
                Check page text
              </button>
            </div>

            {view.status === "checking" && (
              <p className="mt-3 text-center text-xs text-fog-dim">
                Investigating — this can take 10-30s while the agent looks around...
              </p>
            )}

            {view.status === "error" && (
              <p className="mt-3 rounded-md border border-threat-critical/30 bg-threat-critical/10 p-2.5 text-xs text-threat-critical">
                {view.message}
              </p>
            )}

            {view.status === "result" &&
              (() => {
                const { Icon, color, bg, border } = labelMeta(view.verdict.label);
                return (
                  <div className="mt-3 space-y-3">
                    <div className={`flex items-start gap-3 rounded-md border ${border} ${bg} p-3`}>
                      <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${color}`} />
                      <div>
                        <p className={`text-sm font-semibold capitalize ${color}`}>{view.verdict.label}</p>
                        <p className="mt-0.5 text-xs text-fog-faint">
                          {view.verdict.kind === "link" ? "URL check" : "Page text check"} &middot;{" "}
                          {Math.round(view.verdict.confidence * 100)}% confidence
                        </p>
                      </div>
                    </div>

                    <p className="text-xs leading-relaxed text-fog-dim">{view.verdict.reason}</p>

                    {view.verdict.mitigation && (
                      <p className="border-t border-panel-line pt-2 text-xs text-fog-faint">{view.verdict.mitigation}</p>
                    )}

                    {view.verdict.legitimateAlternatives.length > 0 && (
                      <div className="border-t border-panel-line pt-2">
                        <p className="mb-1 text-xs text-fog-faint">This might be an impersonation of:</p>
                        {view.verdict.legitimateAlternatives.map((alt) => (
                          <a
                            key={alt.url}
                            href={alt.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="block truncate text-xs text-sentinel hover:underline"
                          >
                            {alt.title}
                          </a>
                        ))}
                      </div>
                    )}

                    <div className="grid grid-cols-2 gap-2 pt-1">
                      <button
                        onClick={() => handleViewReport(view.verdict.runId!)}
                        disabled={!view.verdict.runId}
                        className="flex items-center justify-center gap-1.5 rounded-md border border-panel-line py-2 text-xs font-medium text-fog hover:bg-panel-raised disabled:opacity-50"
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                        Full report
                      </button>
                      <button
                        onClick={() => setView({ status: "idle", tab })}
                        className="flex items-center justify-center gap-1.5 rounded-md border border-panel-line py-2 text-xs font-medium text-fog-dim hover:bg-panel-raised"
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                        Dismiss
                      </button>
                    </div>
                  </div>
                );
              })()}
          </>
        )}
      </div>
    </div>
  );
}
