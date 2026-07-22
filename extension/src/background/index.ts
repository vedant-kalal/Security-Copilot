/**
 * SentinelAI background service worker.
 *
 * Responsibilities (architecture doc section 7 — "Browser Extension
 * Responsibilities: Event collection, URL submission, Authentication,
 * Popup rendering [via popup.html]. The extension is NOT an AI model —
 * the backend performs all intelligence."):
 *
 *   - Watch top-level navigations and submit each URL for a phishing
 *     check (core workflow steps 3-6).
 *   - Watch file downloads and report them as events.
 *   - Relay form-submission signals from the content script.
 *   - Surface a warning (badge + notification) when a threat is found
 *     (architecture doc section 8, "Popup Behaviour").
 *   - Keep the device's `last_seen` timestamp fresh via a periodic
 *     heartbeat alarm.
 */
import { api } from "@/lib/api";
import { ensureDeviceRegistered } from "@/lib/auth";
import { getStorage, setTabVerdict } from "@/lib/storage";
import type { EventIngestResponse, PhishingCheckResult, RuntimeMessage } from "@/types";

const HEARTBEAT_ALARM = "sentinelai-heartbeat";

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(HEARTBEAT_ALARM, { periodInMinutes: 5 });
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === HEARTBEAT_ALARM) {
    void sendHeartbeat();
  }
});

async function sendHeartbeat(): Promise<void> {
  const { accessToken, deviceId } = await getStorage();
  if (!accessToken || !deviceId) return;
  try {
    await api.post(`/devices/${deviceId}/heartbeat`);
  } catch {
    // Non-fatal: the next successful heartbeat will catch up.
  }
}

async function setBadge(tabId: number, riskLabel: "low" | "medium" | "high" | null): Promise<void> {
  if (riskLabel === "high" || riskLabel === "medium") {
    await chrome.action.setBadgeText({ tabId, text: "!" });
    await chrome.action.setBadgeBackgroundColor({ tabId, color: riskLabel === "high" ? "#EF4444" : "#F5A623" });
  } else {
    await chrome.action.setBadgeText({ tabId, text: "" });
  }
}

async function checkNavigation(tabId: number, url: string): Promise<void> {
  const { accessToken } = await getStorage();
  if (!accessToken) return; // Not signed in yet — monitoring has not started.
  if (!url.startsWith("http://") && !url.startsWith("https://")) return;

  // Do not scan local development environments (avoid API noise & false positives)
  if (url.includes("localhost") || url.includes("127.0.0.1") || url.includes("0.0.0.0")) return;

  try {
    const deviceId = await ensureDeviceRegistered();
    const result = await api.post<PhishingCheckResult>("/phishing/check", { url, device_id: deviceId });

    await setTabVerdict(tabId, {
      url,
      isPhishing: result.is_phishing,
      confidence: result.confidence,
      riskLabel: result.risk_label,
      reasons: result.reasons,
      incidentId: result.incident_id,
      checkedAt: Date.now(),
    });

    await setBadge(tabId, result.risk_label === "low" ? null : result.risk_label);

    if (result.is_phishing) {
      chrome.notifications.create(`sentinelai-${tabId}-${Date.now()}`, {
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: "SentinelAI: Suspicious site detected",
        message: `${new URL(url).hostname} looks like a phishing site (${Math.round(result.confidence * 100)}% confidence). Click the SentinelAI icon for details.`,
        priority: 2,
      });
    }
  } catch (error) {
    console.warn("SentinelAI: phishing check failed", error);
  }
}

chrome.webNavigation.onCommitted.addListener((details) => {
  if (details.frameId !== 0) return; // main frame only
  void checkNavigation(details.tabId, details.url);
});

chrome.downloads.onCreated.addListener((downloadItem) => {
  void (async () => {
    const { accessToken, deviceId } = await getStorage();
    if (!accessToken || !deviceId) return;
    try {
      await api.post<EventIngestResponse>("/events", {
        device_id: deviceId,
        event_type: "file_download",
        payload: {
          filename: downloadItem.filename.split(/[\\/]/).pop() ?? downloadItem.filename,
          source_url: downloadItem.url,
        },
      });
    } catch (error) {
      console.warn("SentinelAI: failed to report download event", error);
    }
  })();
});

chrome.runtime.onMessage.addListener((message: RuntimeMessage) => {
  if (message.type === "FORM_SUBMISSION") {
    void (async () => {
      const { accessToken, deviceId } = await getStorage();
      if (!accessToken || !deviceId) return;
      try {
        await api.post<EventIngestResponse>("/events", {
          device_id: deviceId,
          event_type: "form_submission",
          payload: { url: message.url, has_password_field: message.hasPasswordField },
        });
      } catch (error) {
        console.warn("SentinelAI: failed to report form submission event", error);
      }
    })();
  }
  return false;
});
