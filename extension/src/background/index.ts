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
 * The banner's "Full report" button (and the popup's "Check this URL")
 * both send RUN_FULL_CHECK back here, which runs the real investigation
 * (the full agent — headless browser, WHOIS/VirusTotal, an LLM call,
 * 10-40s) via /check-links-stream — a Server-Sent Events endpoint that
 * reports each step live (see readSSE/runFullCheck below) instead of one
 * blocking response — then opens the report once it's done.
 *
 * Separately, the content script can send PAGE_SIGNALS if it finds a
 * password field posting to a different site than the page itself — see
 * handlePageSignals() below — which can upgrade an already-shown "safe"
 * result if the backend agrees it's meaningful.
 */
import { api, ApiError } from "@/lib/api";
import {
  clearPendingFullCheck,
  getPendingFullCheck,
  getStorage,
  setPendingFullCheck,
  setTabVerdict,
  updatePendingFullCheckStep,
} from "@/lib/storage";
import type { BackgroundToContentMessage, CheckLinksStreamEvent, ContentToBackgroundMessage, QuickCheckResponse } from "@/types";

// Per-tab debounce: SPA route changes / redirect chains can fire several
// onCommitted events in quick succession for what's conceptually one visit —
// skip re-checking a URL we just checked for the same tab.
const lastCheckedByTab = new Map<number, string>();

// A page load can produce two independent /quick-check-url calls — the
// immediate URL-only one from scanNavigation, and a slower page-signal-
// corroborated follow-up if the content script finds a cross-domain
// password form — and they can complete in either order (both do a
// VirusTotal round trip, so latency isn't predictable). Tracks the
// strongest label already shown for a tab's current URL so a slower,
// weaker result can never downgrade a correct escalation that already
// landed.
const RANK: Record<string, number> = { safe: 0, unknown: 0, suspicious: 1, dangerous: 2 };
const lastAppliedByTab = new Map<number, { url: string; rank: number }>();

chrome.tabs.onRemoved.addListener((tabId) => {
  lastCheckedByTab.delete(tabId);
  lastAppliedByTab.delete(tabId);
});

// ── Blocklist enforcement ──────────────────────────────────────────────
//
// A domain lands here after the popup's "Report & block" action (POST
// /report — see Popup.tsx) adds it to the backend's static blocklist.
// This is a local mirror of that list, synced periodically plus right
// after every report, so onBeforeNavigate below can decide in-process
// without a network round trip — the backend call already happened once,
// at report time, not on every subsequent navigation.
//
// Not a hard security boundary: this is a same-process JS check racing
// real navigation, not a declarativeNetRequest rule enforced by the
// browser itself, so a sufficiently fast redirect chain could in theory
// slip through. Acceptable for what this is — a personal safety net
// against a phishing page the user already investigated and blocked
// themselves, not a managed security boundary against a resourced
// adversary.
const BLOCKED_DOMAINS_KEY = "blockedDomains";
const SYNC_ALARM_NAME = "sync-blocklist";
const SYNC_INTERVAL_MINUTES = 15;

let blockedDomains = new Set<string>();

// A URL the user explicitly chose to proceed to anyway (Blocked.tsx) —
// let exactly one more attempt at it through, then forget it. Cleared
// after ALLOW_ONCE_TTL_MS as a safety net in case it's never consumed
// (e.g. the tab closed before navigating).
const ALLOW_ONCE_TTL_MS = 30_000;
const allowOnceUrls = new Set<string>();

function allowOnce(url: string): void {
  allowOnceUrls.add(url);
  setTimeout(() => allowOnceUrls.delete(url), ALLOW_ONCE_TTL_MS);
}

async function loadBlockedDomainsFromStorage(): Promise<void> {
  const stored = await chrome.storage.local.get(BLOCKED_DOMAINS_KEY);
  const domains = stored[BLOCKED_DOMAINS_KEY] as string[] | undefined;
  if (domains) blockedDomains = new Set(domains);
}

async function syncBlocklist(): Promise<void> {
  try {
    const { domains } = await api.get<{ domains: string[] }>("/blocklist");
    blockedDomains = new Set(domains);
    await chrome.storage.local.set({ [BLOCKED_DOMAINS_KEY]: domains });
  } catch (error) {
    // Backend unreachable — keep whatever was last synced (or nothing,
    // on a very first run) rather than clearing a list that's still
    // probably accurate.
    console.warn("security-copilot: blocklist sync failed", error);
  }
}

// Mirrors backend/cache/blocklist.py's is_blocklisted: an entry can be
// either a bare domain or a full URL, and either one is a match.
function isBlockedNavigation(url: string): boolean {
  if (blockedDomains.size === 0) return false;
  try {
    const hostname = new URL(url).hostname.toLowerCase();
    return blockedDomains.has(hostname) || blockedDomains.has(url.toLowerCase());
  } catch {
    return false;
  }
}

// Loaded from storage immediately (fast, survives service-worker restarts)
// every time this module evaluates — which is every service-worker wake,
// not just browser startup — then refreshed from the backend right after.
void loadBlockedDomainsFromStorage().then(() => void syncBlocklist());

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === SYNC_ALARM_NAME) void syncBlocklist();
});
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(SYNC_ALARM_NAME, { periodInMinutes: SYNC_INTERVAL_MINUTES });
});
// onInstalled only fires on install/update, not on every browser start —
// this covers the "extension already installed, browser just launched,
// no alarm exists yet this session" case. chrome.alarms.create is a
// no-op if one by this name is already scheduled.
chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create(SYNC_ALARM_NAME, { periodInMinutes: SYNC_INTERVAL_MINUTES });
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

function reasonFor(result: QuickCheckResponse): string {
  switch (result.source) {
    case "blocklist":
      return "This URL matches security-copilot's static blocklist of known-bad domains.";
    case "virustotal":
      return "VirusTotal already has multiple security vendors flagging this domain. Click \"Full report\" for a complete investigation.";
    case "page_signal":
      return "This page has a login form that submits your password to a different, unrelated domain — a strong sign of credential phishing. Click \"Full report\" for a complete investigation.";
    default:
      return "security-copilot's local phishing-URL model flagged this address. Click \"Full report\" for a complete investigation.";
  }
}

// Shared by both the automatic per-navigation scan and the page-signal
// follow-up below — either can produce a QuickCheckResponse that needs the
// same badge/verdict/banner treatment.
async function applyQuickCheckResult(tabId: number, url: string, result: QuickCheckResponse): Promise<void> {
  const rank = RANK[result.label] ?? 0;
  const previous = lastAppliedByTab.get(tabId);
  if (previous && previous.url === url && previous.rank > rank) {
    // A stronger verdict for this exact page already landed — see
    // lastAppliedByTab's comment. Don't let this slower, weaker one win.
    return;
  }
  lastAppliedByTab.set(tabId, { url, rank });

  await setBadge(tabId, result.label);

  if (result.label === "dangerous" || result.label === "suspicious") {
    await setTabVerdict(tabId, {
      checkedUrl: url,
      kind: "quick",
      label: result.label,
      confidence: result.confidence,
      reason: reasonFor(result),
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
}

async function scanNavigation(tabId: number, url: string): Promise<void> {
  const { apiBaseUrl, autoScanEnabled } = await getStorage();
  if (!autoScanEnabled) return;
  if (shouldSkip(url, apiBaseUrl)) return;
  if (lastCheckedByTab.get(tabId) === url) return;
  lastCheckedByTab.set(tabId, url);

  try {
    const result = await api.post<QuickCheckResponse>("/quick-check-url", { url });
    await applyQuickCheckResult(tabId, url, result);
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

// Fires before the navigation commits — the only event early enough to
// redirect away instead of letting a blocklisted page load first and
// showing a banner on top of it (what onCommitted above does for the
// automatic scan). Deliberately synchronous against the in-memory
// blockedDomains Set (see the "Blocklist enforcement" section above)
// rather than awaiting a fresh /blocklist call here — a network round
// trip on every single navigation would be real, user-visible latency
// for a check that's almost always going to say "not blocked."
chrome.webNavigation.onBeforeNavigate.addListener((details) => {
  if (details.frameId !== 0) return;
  if (allowOnceUrls.delete(details.url)) return; // consumed — let this one attempt through
  if (!isBlockedNavigation(details.url)) return;

  void chrome.tabs.update(details.tabId, {
    url: chrome.runtime.getURL(`blocked.html?url=${encodeURIComponent(details.url)}`),
  });
});

// The content script only ever sends PAGE_SIGNALS when it found a password
// field posting to a different site than the page itself — see
// content/index.ts's computePageSignals(). Re-runs the same quick-check
// with that fact attached; routes_quick_check.py decides whether it's
// enough to escalate (it also re-derives the ML/VT verdict itself, so this
// doesn't need to know what scanNavigation already found). A "safe" result
// back means the backend didn't find it convincing (e.g. same registrable
// domain after normalization) — nothing to show in that case, since
// scanNavigation already showed whatever was appropriate for the URL alone.
async function handlePageSignals(tabId: number, url: string, actionDomain: string): Promise<void> {
  const { apiBaseUrl, autoScanEnabled } = await getStorage();
  if (!autoScanEnabled) return;
  if (shouldSkip(url, apiBaseUrl)) return;

  try {
    const result = await api.post<QuickCheckResponse>("/quick-check-url", {
      url,
      cross_domain_password_form: true,
      action_domain: actionDomain,
    });
    if (result.label === "safe") return;
    await applyQuickCheckResult(tabId, url, result);
  } catch (error) {
    console.warn("security-copilot: page-signal check failed", error);
  }
}

// A full investigation (headless browser, WHOIS/VirusTotal, an LLM call)
// can take well past 30 seconds — confirmed 2026-08 at ~40s for a real
// case. MV3 tears down a service worker after ~30s with no extension-API
// activity, and a bare in-flight fetch() isn't reliably enough to prevent
// that on its own. When the worker gets killed mid-await, the fetch's
// eventual response has nothing left to run it — the banner is stuck on
// "Investigating..." forever, the report never opens, and the only way
// the user found the result was to trigger a second, redundant check.
// Touching a trivial chrome.* API on an interval resets that idle timer
// and keeps the worker (and this function's paused await) alive.
function startKeepAlive(): () => void {
  const interval = setInterval(() => {
    void chrome.storage.local.get("keepalive");
  }, 20000);
  return () => clearInterval(interval);
}

// POST /check-links-stream (api/routes_check_links_stream.py) sends
// Server-Sent Events — one "progress" event per real step the agent
// takes (see graph.py's stream_case_traced), then one "done" event with
// the actual result. Parses the "data: {...}\n\n" framing incrementally
// off the fetch response body as it arrives, instead of waiting for the
// whole thing to buffer.
async function* readSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<CheckLinksStreamEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const raw of events) {
      const line = raw.trim();
      if (!line.startsWith("data:")) continue;
      yield JSON.parse(line.slice("data:".length).trim()) as CheckLinksStreamEvent;
    }
  }
}

async function runFullCheck(tabId: number, url: string): Promise<void> {
  const pending = await getPendingFullCheck(tabId);
  if (pending && pending.url === url) return; // already running for this exact tab+URL — nothing to do

  await setPendingFullCheck(tabId, { url, startedAt: Date.now() });
  const stopKeepAlive = startKeepAlive();
  await sendToTab(tabId, { type: "FULL_CHECK_STARTED" });
  try {
    const { apiBaseUrl, dashboardBaseUrl } = await getStorage();
    const response = await fetch(`${apiBaseUrl}/check-links-stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls: [url] }),
    });
    if (!response.ok || !response.body) {
      throw new ApiError(response.status, `Full check failed (HTTP ${response.status}).`);
    }

    let final: Extract<CheckLinksStreamEvent, { type: "done" }> | null = null;
    for await (const event of readSSE(response.body)) {
      if (event.type === "progress") {
        await updatePendingFullCheckStep(tabId, event.label);
        await sendToTab(tabId, { type: "FULL_CHECK_PROGRESS", label: event.label });
      } else {
        final = event;
      }
    }
    if (!final) throw new Error("Investigation stream ended without a result.");

    const v = final.verdict;
    await setBadge(tabId, v.label);
    await setTabVerdict(tabId, {
      checkedUrl: url,
      kind: "link",
      label: v.label,
      confidence: v.confidence,
      reason: v.reason,
      mitigation: v.mitigation,
      legitimateAlternatives: v.legitimate_alternatives,
      runId: final.run_id,
      checkedAt: Date.now(),
    });
    // Cleared after the verdict lands, not before — the popup treats
    // "pending cleared with no matching verdict" as a failure signal, so
    // this ordering matters (see Popup.tsx's storage.onChanged listener).
    await clearPendingFullCheck(tabId);
    await sendToTab(tabId, { type: "FULL_CHECK_DONE", runId: final.run_id, label: v.label, confidence: v.confidence });

    // Content scripts can't open tabs — the background does it, since it
    // already has the dashboard's base URL and the run_id in hand. Opens
    // the Next.js dashboard's dedicated /run/[id] page (dashboard/app/run/
    // [id]/page.tsx) — a full page, not the small in-app modal.
    chrome.tabs.create({ url: `${dashboardBaseUrl}/run/${final.run_id}` });
  } catch (error) {
    await clearPendingFullCheck(tabId);
    const message = error instanceof ApiError ? error.message : "Full check failed.";
    await sendToTab(tabId, { type: "FULL_CHECK_FAILED", message });
  } finally {
    stopKeepAlive();
  }
}

chrome.runtime.onMessage.addListener((message: ContentToBackgroundMessage, sender) => {
  if (message.type === "RUN_FULL_CHECK") {
    // From the banner (content script), the tab is sender.tab; from the
    // popup (an extension page, not injected into any tab) there's no
    // sender.tab at all, so it sends its own tabId explicitly instead.
    const tabId = sender.tab?.id ?? message.tabId;
    if (tabId !== undefined) void runFullCheck(tabId, message.url);
  } else if (message.type === "PAGE_SIGNALS" && sender.tab?.id !== undefined) {
    void handlePageSignals(sender.tab.id, message.url, message.actionDomain);
  } else if (message.type === "REFRESH_BLOCKLIST") {
    void syncBlocklist();
  } else if (message.type === "ALLOW_ONCE") {
    allowOnce(message.url);
  }
  return false;
});
