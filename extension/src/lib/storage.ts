/**
 * Typed wrapper around `chrome.storage.local`, used instead of
 * `localStorage` because service workers and popup/options pages do not
 * share a single `window`. The backend has no auth (see
 * backend/README.md — POC scope), so the only durable setting is where
 * the backend lives.
 */
export interface CopilotStorage {
  apiBaseUrl: string;
}

const DEFAULTS: CopilotStorage = {
  apiBaseUrl: "http://127.0.0.1:8010",
};

export async function getStorage(): Promise<CopilotStorage> {
  const stored = await chrome.storage.local.get(Object.keys(DEFAULTS));
  return { ...DEFAULTS, ...stored } as CopilotStorage;
}

export async function setStorage(partial: Partial<CopilotStorage>): Promise<void> {
  await chrome.storage.local.set(partial);
}

/** Per-tab last verdict, kept in session storage (cleared on browser restart)
 * so re-opening the popup on the same tab doesn't re-run a check. */
export interface TabVerdict {
  checkedUrl: string;
  kind: "link" | "email";
  label: "dangerous" | "suspicious" | "safe" | "inconclusive";
  confidence: number;
  reason: string;
  mitigation: string | null;
  legitimateAlternatives: { title: string; url: string }[];
  runId: string | null;
  checkedAt: number;
}

export async function setTabVerdict(tabId: number, verdict: TabVerdict): Promise<void> {
  await chrome.storage.session.set({ [`tab_verdict_${tabId}`]: verdict });
}

export async function getTabVerdict(tabId: number): Promise<TabVerdict | null> {
  const result = await chrome.storage.session.get(`tab_verdict_${tabId}`);
  return (result[`tab_verdict_${tabId}`] as TabVerdict | undefined) ?? null;
}

export async function clearTabVerdict(tabId: number): Promise<void> {
  await chrome.storage.session.remove(`tab_verdict_${tabId}`);
}
