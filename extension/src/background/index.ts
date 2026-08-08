/**
 * security-copilot background service worker.
 *
 * Owns the automatic per-navigation scan: on every top-level http(s)
 * navigation, calls the backend's fast /quick-check-url (local ML model,
 * corroborated with a cached VirusTotal lookup — see
 * api/routes_quick_check.py) and tells the content script in that tab to
 * show an in-page banner either way: dangerous/suspicious gets a banner
 * that stays until the user dismisses it (no auto-hide timer — the user
 * asked explicitly that unsafe verdicts not disappear on their own), safe
 * gets a brief ~1.5s confirmation toast that clears itself.
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

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Retry delays for a message the content script isn't ready for yet. A
// quick-check result can come back in single-digit milliseconds (cache/
// blocklist hits, or even a fresh ML score), which is faster than a
// content_scripts "document_idle" injection can possibly have registered
// its onMessage listener — chrome.tabs.sendMessage then rejects with
// "Could not establish connection. Receiving end does not exist." The
// content script does become ready shortly after, so a few short retries
// resolve this reliably instead of the banner silently never appearing.
const SEND_RETRY_DELAYS_MS = [100, 250, 500, 1000];

async function sendToTab(tabId: number, message: BackgroundToContentMessage): Promise<void> {
  for (let attempt = 0; ; attempt++) {
    try {
      await chrome.tabs.sendMessage(tabId, message);
      return;
    } catch (error) {
      if (attempt >= SEND_RETRY_DELAYS_MS.length) {
        // Content script never became reachable (tab closed, a chrome://
        // page slipped through, etc.) — the badge is still set as a
        // fallback signal, so this isn't a silent total failure.
        console.warn("security-copilot: sendToTab gave up after retries", tabId, message.type, error);
        return;
      }
      await sleep(SEND_RETRY_DELAYS_MS[attempt]);
    }
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
            : result.source === "virustotal"
              ? "VirusTotal already has multiple security vendors flagging this domain. Click \"Full report\" for a complete investigation."
              : "security-copilot's local phishing-URL model flagged this address. Click \"Full report\" for a complete investigation.",
        mitigation: null,
        legitimateAlternatives: [],
        runId: null,
        checkedAt: Date.now(),
      });
      await sendToTab(tabId, {
        type: "SHOW_BANNER",
        url,
        label: result.label,
        confidence: result.confidence,
        source: result.source,
      });
    } else if (result.label === "safe") {
      // No "Full report" button for these — it's a brief confirmation, not
      // an alert — so a bare TabVerdict is enough for the popup to reflect
      // it if opened right after.
      await setTabVerdict(tabId, {
        checkedUrl: url,
        kind: "quick",
        label: "safe",
        confidence: result.confidence,
        reason: "security-copilot's automatic quick scan found nothing suspicious about this page.",
        mitigation: null,
        legitimateAlternatives: [],
        runId: null,
        checkedAt: Date.now(),
      });
      await sendToTab(tabId, {
        type: "SHOW_BANNER",
        url,
        label: "safe",
        confidence: result.confidence,
        source: result.source,
      });
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
