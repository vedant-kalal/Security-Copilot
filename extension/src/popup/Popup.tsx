import { AlertTriangle, ExternalLink, Flag, LogOut, ShieldCheck, ShieldHalf, X } from "lucide-react";
import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { login as loginRequest } from "@/lib/auth";
import { getStorage, getTabVerdict, setStorage, type TabVerdict } from "@/lib/storage";
import type { PhishingCheckResult } from "@/types";

type ViewState =
  | { status: "loading" }
  | { status: "signed-out" }
  | { status: "checking" }
  | { status: "safe"; hostname: string }
  | { status: "threat"; verdict: TabVerdict; hostname: string };

export function Popup() {
  const [view, setView] = useState<ViewState>({ status: "loading" });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [reported, setReported] = useState(false);
  const [activeTabId, setActiveTabId] = useState<number | null>(null);
  const [dashboardUrl, setDashboardUrl] = useState("http://localhost:5173");

  useEffect(() => {
    void bootstrap();
  }, []);

  async function bootstrap() {
    const { accessToken, apiBaseUrl } = await getStorage();
    setDashboardUrl(apiBaseUrl.replace(/\/api\/v1\/?$/, "").replace(":8000", ":5173"));

    if (!accessToken) {
      setView({ status: "signed-out" });
      return;
    }

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !tab.url || !tab.url.startsWith("http")) {
      setView({ status: "safe", hostname: "this page" });
      return;
    }
    setActiveTabId(tab.id);

    const cached = await getTabVerdict(tab.id);
    const hostname = safeHostname(tab.url);

    if (cached && cached.url === tab.url) {
      applyVerdict(cached, hostname);
      return;
    }

    setView({ status: "checking" });
    try {
      const deviceId = (await getStorage()).deviceId;
      const result = await api.post<PhishingCheckResult>("/phishing/check", {
        url: tab.url,
        device_id: deviceId,
      });
      const verdict: TabVerdict = {
        url: tab.url,
        isPhishing: result.is_phishing,
        confidence: result.confidence,
        riskLabel: result.risk_label,
        reasons: result.reasons,
        incidentId: result.incident_id,
        checkedAt: Date.now(),
      };
      applyVerdict(verdict, hostname);
    } catch {
      setView({ status: "safe", hostname });
    }
  }

  function applyVerdict(verdict: TabVerdict, hostname: string) {
    if (verdict.isPhishing) {
      setView({ status: "threat", verdict, hostname });
    } else {
      setView({ status: "safe", hostname });
    }
  }

  function safeHostname(url: string): string {
    try {
      return new URL(url).hostname;
    } catch {
      return url;
    }
  }

  async function handleLogin(event: React.FormEvent) {
    event.preventDefault();
    setLoginError(null);
    setIsSubmitting(true);
    try {
      await loginRequest(email, password);
      setView({ status: "loading" });
      await bootstrap();
    } catch (error) {
      setLoginError(error instanceof ApiError ? error.message : "Sign in failed. Check your API URL in Settings.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleLeaveSite() {
    if (activeTabId === null) return;
    await chrome.tabs.update(activeTabId, { url: "chrome://newtab" });
    window.close();
  }

  function handleViewDetails() {
    if (view.status !== "threat") return;
    const path = view.verdict.incidentId ? `/incidents/${view.verdict.incidentId}` : "/incidents";
    chrome.tabs.create({ url: `${dashboardUrl}${path}` });
  }

  async function handleReport() {
    setReported(true);
    // The documented API surface (architecture doc section 20) does not
    // define a dedicated /report endpoint — the phishing/check call that
    // already ran has flagged this URL server-side. This button gives
    // the user local confirmation their report was acknowledged.
  }

  return (
    <div className="flex flex-col">
      <header className="flex items-center gap-2 border-b border-panel-line px-4 py-3">
        <ShieldHalf className="h-5 w-5 text-sentinel" />
        <span className="font-display text-sm font-semibold">SentinelAI</span>
        {view.status !== "signed-out" && view.status !== "loading" && (
          <button
            className="ml-auto text-fog-faint hover:text-fog"
            title="Sign out"
            onClick={async () => {
              await setStorage({ accessToken: null, refreshToken: null });
              setView({ status: "signed-out" });
            }}
          >
            <LogOut className="h-4 w-4" />
          </button>
        )}
      </header>

      <div className="p-4">
        {view.status === "loading" && <p className="py-8 text-center text-sm text-fog-dim">Loading...</p>}

        {view.status === "signed-out" && (
          <form className="space-y-3" onSubmit={handleLogin}>
            <p className="text-sm text-fog-dim">Sign in to start monitoring this browser.</p>
            <input
              type="email"
              required
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-panel-line bg-panel-raised px-3 py-2 text-sm text-fog placeholder:text-fog-faint focus:outline-none focus:ring-2 focus:ring-sentinel/50"
            />
            <input
              type="password"
              required
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-panel-line bg-panel-raised px-3 py-2 text-sm text-fog placeholder:text-fog-faint focus:outline-none focus:ring-2 focus:ring-sentinel/50"
            />
            {loginError && <p className="text-xs text-threat-critical">{loginError}</p>}
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-md bg-sentinel py-2 text-sm font-medium text-void hover:bg-sentinel-glow disabled:opacity-50"
            >
              {isSubmitting ? "Signing in..." : "Sign In"}
            </button>
            <button
              type="button"
              className="w-full text-center text-xs text-fog-faint hover:text-sentinel"
              onClick={() => chrome.runtime.openOptionsPage()}
            >
              New here? Create an account in Settings
            </button>
          </form>
        )}

        {view.status === "checking" && <p className="py-8 text-center text-sm text-fog-dim">Checking this page...</p>}

        {view.status === "safe" && (
          <div className="flex flex-col items-center gap-2 py-6 text-center">
            <ShieldCheck className="h-9 w-9 text-sentinel" />
            <p className="text-sm font-medium text-fog">No threats detected</p>
            <p className="text-xs text-fog-faint">{view.hostname}</p>
          </div>
        )}

        {view.status === "threat" && (
          <div className="space-y-3">
            <div className="flex items-start gap-3 rounded-md border border-threat-high/30 bg-threat-high/10 p-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-threat-high" />
              <div>
                <p className="text-sm font-semibold text-fog">Suspicious site detected</p>
                <p className="mt-0.5 font-mono text-xs text-fog-faint">{view.hostname}</p>
              </div>
            </div>

            <div className="flex items-center justify-between rounded-md bg-panel-raised px-3 py-2 text-xs">
              <span className="text-fog-dim">Confidence</span>
              <span className="font-mono font-semibold text-threat-high">
                {Math.round(view.verdict.confidence * 100)}%
              </span>
            </div>

            <ul className="space-y-1 text-xs text-fog-dim">
              {view.verdict.reasons.slice(0, 3).map((reason, i) => (
                <li key={i} className="flex gap-1.5">
                  <span className="text-threat-high">•</span>
                  {reason}
                </li>
              ))}
            </ul>

            <div className="grid grid-cols-2 gap-2 pt-1">
              <button
                onClick={handleViewDetails}
                className="flex items-center justify-center gap-1.5 rounded-md border border-panel-line py-2 text-xs font-medium text-fog hover:bg-panel-raised"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                View Details
              </button>
              <button
                onClick={handleReport}
                disabled={reported}
                className="flex items-center justify-center gap-1.5 rounded-md border border-panel-line py-2 text-xs font-medium text-fog hover:bg-panel-raised disabled:opacity-50"
              >
                <Flag className="h-3.5 w-3.5" />
                {reported ? "Reported" : "Report"}
              </button>
              <button
                onClick={() => window.close()}
                className="flex items-center justify-center gap-1.5 rounded-md border border-panel-line py-2 text-xs font-medium text-fog-dim hover:bg-panel-raised"
              >
                Continue
              </button>
              <button
                onClick={handleLeaveSite}
                className="flex items-center justify-center gap-1.5 rounded-md bg-threat-critical py-2 text-xs font-semibold text-white hover:bg-threat-critical/90"
              >
                <X className="h-3.5 w-3.5" />
                Leave Site
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
