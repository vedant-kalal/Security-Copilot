/**
 * Typed wrapper around `chrome.storage.local`, used instead of
 * `localStorage` because service workers and content scripts do not
 * have access to `window.localStorage`.
 */
export interface SentinelStorage {
  apiBaseUrl: string;
  accessToken: string | null;
  refreshToken: string | null;
  userEmail: string | null;
  deviceId: string | null;
}

const DEFAULTS: SentinelStorage = {
  apiBaseUrl: "http://localhost:8000/api/v1",
  accessToken: null,
  refreshToken: null,
  userEmail: null,
  deviceId: null,
};

export async function getStorage(): Promise<SentinelStorage> {
  const stored = await chrome.storage.local.get(Object.keys(DEFAULTS));
  return { ...DEFAULTS, ...stored } as SentinelStorage;
}

export async function setStorage(partial: Partial<SentinelStorage>): Promise<void> {
  await chrome.storage.local.set(partial);
}

export async function clearAuth(): Promise<void> {
  await chrome.storage.local.remove(["accessToken", "refreshToken", "userEmail", "deviceId"]);
}

/** Per-tab phishing verdicts, kept in session storage (cleared on browser restart). */
export interface TabVerdict {
  url: string;
  isPhishing: boolean;
  confidence: number;
  riskLabel: "low" | "medium" | "high";
  reasons: string[];
  incidentId: string | null;
  checkedAt: number;
}

export async function setTabVerdict(tabId: number, verdict: TabVerdict): Promise<void> {
  await chrome.storage.session.set({ [`tab_verdict_${tabId}`]: verdict });
}

export async function getTabVerdict(tabId: number): Promise<TabVerdict | null> {
  const result = await chrome.storage.session.get(`tab_verdict_${tabId}`);
  return (result[`tab_verdict_${tabId}`] as TabVerdict | undefined) ?? null;
}
