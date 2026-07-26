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
    <div className="mx-auto max-w-xl space-y-6 p-8">
      <div className="flex items-center gap-2.5">
        <ShieldHalf className="h-6 w-6 text-sentinel" />
        <h1 className="font-display text-lg font-semibold">security-copilot Settings</h1>
      </div>

      <section className="rounded-lg border border-panel-line bg-panel p-5">
        <h2 className="font-display text-sm font-semibold text-fog">Backend</h2>
        <p className="mt-1 text-xs text-fog-faint">
          Point the extension at your running security-copilot backend (<code>uvicorn api.app:app</code> in{" "}
          <code>backend/</code>). No sign-in is required.
        </p>
        <form className="mt-3 flex gap-2" onSubmit={handleSave}>
          <input
            type="url"
            required
            value={apiBaseUrl}
            onChange={(e) => setApiBaseUrl(e.target.value)}
            placeholder="http://127.0.0.1:8010"
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

      <p className="text-center text-xs text-fog-faint">security-copilot — v1.0.0</p>
    </div>
  );
}
