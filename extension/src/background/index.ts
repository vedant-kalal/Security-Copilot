/**
 * security-copilot background service worker.
 *
 * Owns the automatic per-navigation scan: on every top-level http(s)
 * navigation, calls the backend's fast /quick-check-url (local ML model
 * only, milliseconds, no LLM — see api/routes_quick_check.py) and, if it
 * comes back dangerous/suspicious, tells the content script in that tab to
 * show an in-page banner. A safe result shows nothing — silent by design,
 * per the user's explicit ask: automatic, but only surfaces on a hit.
 *
 * The banner's "Full report" button sends RUN_FULL_CHECK back here, which
 * runs the real investigation (the full agent — headless browser,
 * WHOIS/VirusTotal, an LLM call, 10-30s) via the same /check-links the
 * popup's "Check this URL" button uses, then opens the report.
 */
import { api, ApiError } from "@/lib/api";
import { getStorage, setTabVerdict } from "@/lib/storage";
import type {
  BackgroundToContentMessage,
  CheckLinksResponse,
  ContentToBackgroundMessage,
  QuickCheckResponse,
} from "@/types";

// Per-tab debounce: SPA route changes / redirect chains can fire several
// onCommitted events in quick succession for what's conceptually one visit —
// skip re-checking a URL we just checked for the same tab.
const lastCheckedByTab = new Map<number, string>();

chrome.tabs.onRemoved.addListener((tabId) => {
  lastCheckedByTab.delete(tabId);
});

function shouldSkip(url: string, apiBaseUrl: string): boolean {
  if (!url.startsWith("http://") && !url.startsWith("https://")) return true;
  try {
    const target = new URL(url);
    const backend = new URL(apiBaseUrl);
    // Never scan our own backend's UI, and never scan bare localhost/127.0.0.1
    // dev servers — avoids noise and avoids the extension flagging itself.
    if (target.hostname === backend.hostname && target.port === backend.port) return true;
    if (target.hostname === "localhost" || target.hostname === "127.0.0.1") return true;
  } catch {
    return true;
  }
  return false;
}

async function setBadge(tabId: number, label: string): Promise<void> {
  // The tab can close mid-check (quick-check is fast, but a full investigation
  // takes 10-30s) — badging a closed tab throws "No tab with id: ...", which
  // must never abort the caller: the verdict itself is still valid, and for
  // runFullCheck specifically, still needs to open the report tab afterward.
  try {
    if (label === "dangerous" || label === "suspicious") {
      await chrome.action.setBadgeText({ tabId, text: "!" });
      await chrome.action.setBadgeBackgroundColor({ tabId, color: label === "dangerous" ? "#EF4444" : "#F5A623" });
    } else {
      await chrome.action.setBadgeText({ tabId, text: "" });
    }
  } catch {
    // Tab no longer exists — nothing to badge.
  }
}

async function sendToTab(tabId: number, message: BackgroundToContentMessage): Promise<void> {
  try {
    await chrome.tabs.sendMessage(tabId, message);
  } catch {
    // The content script may not be injected yet (very early navigation) or
    // the tab may not accept content scripts (a chrome:// page slipped
    // through) — the badge is still set as a fallback signal either way.
  }
}

async function scanNavigation(tabId: number, url: string): Promise<void> {
  const { apiBaseUrl, autoScanEnabled } = await getStorage();
  if (!autoScanEnabled) return;
  if (shouldSkip(url, apiBaseUrl)) return;
  if (lastCheckedByTab.get(tabId) === url) return;
  lastCheckedByTab.set(tabId, url);

  try {
    const result = await api.post<QuickCheckResponse>("/quick-check-url", { url });

    await setBadge(tabId, result.label);

    if (result.label === "dangerous" || result.label === "suspicious") {
      await setTabVerdict(tabId, {
        checkedUrl: url,
        kind: "quick",
        label: result.label,
        confidence: result.confidence,
        reason:
          result.source === "blocklist"
            ? "This URL matches security-copilot's static blocklist of known-bad domains."
            : "security-copilot's local phishing-URL model flagged this address. Click \"Full report\" for a complete investigation.",
        mitigation: null,
        legitimateAlternatives: [],
        runId: null,
        checkedAt: Date.now(),
      });
      await sendToTab(tabId, { type: "SHOW_BANNER", url, label: result.label, confidence: result.confidence });
    }
  } catch (error) {
    // A quick-check failure (backend down, etc.) should never interrupt
    // browsing — log only, no badge, no banner.
    console.warn("security-copilot: quick-check failed", error);
  }
}

chrome.webNavigation.onCommitted.addListener((details) => {
  if (details.frameId !== 0) return; // main frame only, not iframes/ads
  void scanNavigation(details.tabId, details.url);
});

async function runFullCheck(tabId: number, url: string): Promise<void> {
  await sendToTab(tabId, { type: "FULL_CHECK_STARTED" });
  try {
    const { results } = await api.post<CheckLinksResponse>("/check-links", { urls: [url] });
    const v = results[url];

    await setBadge(tabId, v.label);
    await setTabVerdict(tabId, {
      checkedUrl: url,
      kind: "link",
      label: v.label,
      confidence: v.confidence,
      reason: v.reason,
      mitigation: v.mitigation,
      legitimateAlternatives: v.legitimate_alternatives,
      runId: v.run_id,
      checkedAt: Date.now(),
    });
    await sendToTab(tabId, { type: "FULL_CHECK_DONE", runId: v.run_id, label: v.label, confidence: v.confidence });

    // Content scripts can't open tabs — the background does it, since it
    // already has both the base URL and the run_id in hand.
    const { apiBaseUrl } = await getStorage();
    chrome.tabs.create({ url: `${apiBaseUrl}/?run=${v.run_id}` });
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "Full check failed.";
    await sendToTab(tabId, { type: "FULL_CHECK_FAILED", message });
  }
}

chrome.runtime.onMessage.addListener((message: ContentToBackgroundMessage, sender) => {
  if (message.type === "RUN_FULL_CHECK" && sender.tab?.id !== undefined) {
    void runFullCheck(sender.tab.id, message.url);
  }
  return false;
});
