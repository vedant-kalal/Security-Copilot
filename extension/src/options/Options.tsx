import { Save, ShieldHalf } from "lucide-react";
import { useEffect, useState } from "react";

import { getStorage, setStorage } from "@/lib/storage";

export function Options() {
  const [apiBaseUrl, setApiBaseUrl] = useState("http://127.0.0.1:8010");
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const storage = await getStorage();
      setApiBaseUrl(storage.apiBaseUrl);
    })();
  }, []);

  async function handleSave(event: React.FormEvent) {
    event.preventDefault();
    await setStorage({ apiBaseUrl: apiBaseUrl.replace(/\/+$/, "") });
    setSavedMessage("Saved.");
    setTimeout(() => setSavedMessage(null), 2000);
  }

  return (
    <div className="mx-auto max-w-xl space-y-8 p-10">
      {/* ── Header ──────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sentinel/15 shadow-glow-sentinel">
          <ShieldHalf className="h-5 w-5 text-sentinel" />
        </div>
        <h1 className="font-display text-lg font-bold tracking-wide">security-copilot Settings</h1>
      </div>

      {/* ── Backend config card ──────────────────────────────── */}
      <section className="glass rounded-xl border border-panel-line p-6 shadow-card">
        <h2 className="font-display text-sm font-bold text-fog">Backend</h2>
        <p className="mt-1.5 text-xs leading-relaxed text-fog-faint">
          Point the extension at your running security-copilot backend (<code className="rounded bg-panel-raised px-1.5 py-0.5 font-mono text-[11px] text-fog-dim">uvicorn api.app:app</code> in{" "}
          <code className="rounded bg-panel-raised px-1.5 py-0.5 font-mono text-[11px] text-fog-dim">backend/</code>). No sign-in is required.
        </p>
        <form className="mt-4 flex gap-3" onSubmit={handleSave}>
          <input
            type="url"
            required
            value={apiBaseUrl}
            onChange={(e) => setApiBaseUrl(e.target.value)}
            placeholder="http://127.0.0.1:8010"
            className="flex-1 rounded-lg border border-panel-line bg-void px-4 py-2.5 font-mono text-sm text-fog transition-all duration-200 focus:border-sentinel/50 focus:shadow-glow-sentinel focus:outline-none"
          />
          <button
            type="submit"
            className="flex items-center gap-2 rounded-lg border border-panel-line bg-panel px-4 py-2.5 text-xs font-semibold text-fog transition-all duration-200 hover:border-sentinel/30 hover:bg-panel-raised hover:shadow-glow-sentinel"
          >
            <Save className="h-3.5 w-3.5" />
            Save
          </button>
        </form>
        {savedMessage && (
          <p className="mt-3 flex items-center gap-1.5 text-xs font-medium text-sentinel">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-sentinel shadow-glow-sentinel" />
            {savedMessage}
          </p>
        )}
      </section>

      <p className="text-center font-mono text-xs text-fog-faint">security-copilot — v1.0.0</p>
    </div>
  );
}
