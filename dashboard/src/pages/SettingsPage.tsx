import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { API_BASE_URL } from "@/lib/constants";
import { useAuth } from "@/hooks/useAuth";

export function SettingsPage() {
  const { user } = useAuth();

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-xl font-semibold text-fog">Settings</h2>
        <p className="text-sm text-fog-dim">Account and integration details.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex justify-between border-b border-panel-line py-2">
            <span className="text-fog-dim">Email</span>
            <span className="font-mono text-fog">{user?.email}</span>
          </div>
          <div className="flex justify-between py-2">
            <span className="text-fog-dim">User ID</span>
            <span className="font-mono text-xs text-fog-faint">{user?.id}</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>API Connection</CardTitle>
          <CardDescription>Used by this dashboard and can be configured for the browser extension.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex justify-between py-2">
            <span className="text-fog-dim">API base URL</span>
            <span className="font-mono text-xs text-fog">{API_BASE_URL}</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Threat Intelligence &amp; AI</CardTitle>
          <CardDescription>
            Configured server-side via environment variables — see the backend's <code>.env.example</code>.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-1.5 text-sm text-fog-dim">
          <p>• VirusTotal, AbuseIPDB, PhishTank — threat intelligence reputation lookups</p>
          <p>• Gemini — RAG playbook retrieval and incident explanations</p>
        </CardContent>
      </Card>
    </div>
  );
}
