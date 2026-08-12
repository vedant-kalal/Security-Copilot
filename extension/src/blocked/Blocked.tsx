/**
 * The interstitial shown in place of a page whose domain is on the
 * blocklist (backend/data/blocklist.txt, added via the "Report & block"
 * action). background.ts's onBeforeNavigate redirects here *before* the
 * real navigation ever commits — see that file's comment on why this is
 * a best-effort, not a hard security boundary (no declarativeNetRequest
 * here, just a same-process check that wins the race in practice).
 *
 * "Proceed anyway" exists on purpose: a personal blocklist can have false
 * positives, and a tool with no escape hatch just gets uninstalled the
 * first time it's wrong. It sends ALLOW_ONCE first so the next attempt at
 * this exact URL isn't blocked again, then navigates there itself.
 */
import { ArrowLeft, ShieldAlert } from "lucide-react";
import { useState } from "react";

function useQueryParam(name: string): string {
  const [value] = useState(() => new URLSearchParams(window.location.search).get(name) ?? "");
  return value;
}

function hostnameOf(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

export function Blocked() {
  const url = useQueryParam("url");
  const [proceeding, setProceeding] = useState(false);

  function goBack() {
    if (window.history.length > 1) window.history.back();
    else window.location.href = "about:blank";
  }

  async function proceedAnyway() {
    if (!url) return;
    setProceeding(true);
    try {
      const tab = await chrome.tabs.getCurrent();
      if (!tab?.id) return;
      await chrome.runtime.sendMessage({ type: "ALLOW_ONCE", url });
      await chrome.tabs.update(tab.id, { url });
    } catch {
      setProceeding(false);
    }
  }

  return (
    <div className="glass w-[440px] rounded-2xl border border-threat-critical/30 p-8 shadow-glow-critical">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-threat-critical/15">
          <ShieldAlert className="h-5 w-5 text-threat-critical" />
        </div>
        <div>
          <p className="font-display text-base font-bold text-threat-critical">Blocked by security-copilot</p>
          <p className="mt-0.5 font-mono text-xs text-fog-faint">on your personal blocklist</p>
        </div>
      </div>

      <p className="mt-5 text-sm leading-relaxed text-fog-dim">
        <span className="break-all font-mono text-fog">{hostnameOf(url) || url}</span> was previously reported and
        added to your blocklist, so security-copilot stopped this page from loading.
      </p>

      <div className="mt-6 flex items-center gap-3">
        <button
          onClick={goBack}
          className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-panel-line bg-panel py-2.5 text-xs font-medium text-fog transition-all duration-200 hover:border-sentinel/30 hover:bg-panel-raised"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Go back
        </button>
        <button
          onClick={proceedAnyway}
          disabled={proceeding || !url}
          className="flex-1 rounded-lg py-2.5 text-xs font-medium text-fog-faint underline-offset-2 transition-colors duration-200 hover:text-fog-dim hover:underline disabled:opacity-40"
        >
          {proceeding ? "Loading…" : "Proceed anyway"}
        </button>
      </div>
    </div>
  );
}
