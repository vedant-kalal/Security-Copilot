import { LogOut, Save, ShieldHalf } from "lucide-react";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { login as loginRequest, logout as logoutRequest, register as registerRequest } from "@/lib/auth";
import { getStorage, setStorage } from "@/lib/storage";

export function Options() {
  const [apiBaseUrl, setApiBaseUrl] = useState("http://localhost:8000/api/v1");
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [authError, setAuthError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [signedInEmail, setSignedInEmail] = useState<string | null>(null);

  useEffect(() => {
    void refresh();
  }, []);

  async function refresh() {
    const storage = await getStorage();
    setApiBaseUrl(storage.apiBaseUrl);
    setSignedInEmail(storage.accessToken ? storage.userEmail : null);
  }

  async function handleSaveApiUrl(event: React.FormEvent) {
    event.preventDefault();
    await setStorage({ apiBaseUrl: apiBaseUrl.replace(/\/+$/, "") });
    setSavedMessage("Saved.");
    setTimeout(() => setSavedMessage(null), 2000);
  }

  async function handleAuthSubmit(event: React.FormEvent) {
    event.preventDefault();
    setAuthError(null);
    setIsSubmitting(true);
    try {
      if (mode === "login") {
        await loginRequest(email, password);
      } else {
        await registerRequest(email, password);
      }
      await refresh();
      setEmail("");
      setPassword("");
    } catch (error) {
      setAuthError(error instanceof ApiError ? error.message : "Something went wrong");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleSignOut() {
    await logoutRequest();
    await refresh();
  }

  return (
    <div className="mx-auto max-w-xl space-y-6 p-8">
      <div className="flex items-center gap-2.5">
        <ShieldHalf className="h-6 w-6 text-sentinel" />
        <h1 className="font-display text-lg font-semibold">SentinelAI Settings</h1>
      </div>

      <section className="rounded-lg border border-panel-line bg-panel p-5">
        <h2 className="font-display text-sm font-semibold text-fog">Account</h2>
        {signedInEmail ? (
          <div className="mt-3 flex items-center justify-between">
            <p className="text-sm text-fog-dim">
              Signed in as <span className="font-mono text-fog">{signedInEmail}</span>
            </p>
            <button
              onClick={handleSignOut}
              className="flex items-center gap-1.5 rounded-md border border-panel-line px-3 py-1.5 text-xs font-medium text-fog hover:bg-panel-raised"
            >
              <LogOut className="h-3.5 w-3.5" />
              Sign out
            </button>
          </div>
        ) : (
          <form className="mt-3 space-y-3" onSubmit={handleAuthSubmit}>
            <div className="flex gap-2 text-xs">
              <button
                type="button"
                onClick={() => setMode("login")}
                className={`rounded-md px-3 py-1.5 font-medium ${mode === "login" ? "bg-sentinel/15 text-sentinel" : "text-fog-dim"}`}
              >
                Sign In
              </button>
              <button
                type="button"
                onClick={() => setMode("register")}
                className={`rounded-md px-3 py-1.5 font-medium ${mode === "register" ? "bg-sentinel/15 text-sentinel" : "text-fog-dim"}`}
              >
                Create Account
              </button>
            </div>
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
              minLength={8}
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-panel-line bg-panel-raised px-3 py-2 text-sm text-fog placeholder:text-fog-faint focus:outline-none focus:ring-2 focus:ring-sentinel/50"
            />
            {authError && <p className="text-xs text-threat-critical">{authError}</p>}
            <button
              type="submit"
              disabled={isSubmitting}
              className="rounded-md bg-sentinel px-4 py-2 text-sm font-medium text-void hover:bg-sentinel-glow disabled:opacity-50"
            >
              {isSubmitting ? "Please wait..." : mode === "login" ? "Sign In" : "Create Account"}
            </button>
          </form>
        )}
      </section>

      <section className="rounded-lg border border-panel-line bg-panel p-5">
        <h2 className="font-display text-sm font-semibold text-fog">API Connection</h2>
        <p className="mt-1 text-xs text-fog-faint">
          Point the extension at your SentinelAI backend. Defaults to a locally running backend on port 8000.
        </p>
        <form className="mt-3 flex gap-2" onSubmit={handleSaveApiUrl}>
          <input
            type="url"
            required
            value={apiBaseUrl}
            onChange={(e) => setApiBaseUrl(e.target.value)}
            className="flex-1 rounded-md border border-panel-line bg-panel-raised px-3 py-2 font-mono text-sm text-fog focus:outline-none focus:ring-2 focus:ring-sentinel/50"
          />
          <button
            type="submit"
            className="flex items-center gap-1.5 rounded-md border border-panel-line px-3 py-2 text-xs font-medium text-fog hover:bg-panel-raised"
          >
            <Save className="h-3.5 w-3.5" />
            Save
          </button>
        </form>
        {savedMessage && <p className="mt-2 text-xs text-sentinel">{savedMessage}</p>}
      </section>

      <p className="text-center text-xs text-fog-faint">SentinelAI Security Copilot — v1.0.0</p>
    </div>
  );
}
