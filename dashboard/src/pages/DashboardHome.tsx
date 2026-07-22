import { RecentThreats } from "@/components/dashboard/RecentThreats";
import { SecurityScoreGauge } from "@/components/dashboard/SecurityScoreGauge";
import { StatsGrid } from "@/components/dashboard/StatsGrid";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboard } from "@/hooks/useDashboard";

const SEVERITY_ORDER: Array<{ key: "critical" | "high" | "medium" | "low"; color: string; label: string }> = [
  { key: "critical", color: "bg-threat-critical", label: "Critical" },
  { key: "high", color: "bg-threat-high", label: "High" },
  { key: "medium", color: "bg-threat-medium", label: "Medium" },
  { key: "low", color: "bg-threat-low", label: "Low" },
];

export function DashboardHome() {
  const { summary, isLoading, error } = useDashboard();

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Skeleton className="h-80 lg:col-span-1" />
        <Skeleton className="h-80 lg:col-span-2" />
      </div>
    );
  }

  if (error || !summary) {
    return <p className="text-sm text-threat-critical">{error ?? "Unable to load dashboard"}</p>;
  }

  const maxSeverityCount = Math.max(1, ...SEVERITY_ORDER.map((s) => summary.severity_breakdown[s.key]));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="flex flex-col items-center justify-center py-8 lg:col-span-1">
          <SecurityScoreGauge score={summary.security_score} />
          <p className="mt-4 max-w-[16rem] text-center text-xs text-fog-dim">
            {summary.security_score >= 80
              ? "Your posture is strong. SentinelAI is actively monitoring for threats."
              : summary.security_score >= 50
                ? "Some unresolved incidents need attention."
                : "Multiple high-severity incidents require immediate action."}
          </p>
        </Card>

        <div className="space-y-6 lg:col-span-2">
          <StatsGrid summary={summary} />

          <Card>
            <CardHeader>
              <CardTitle>Severity Breakdown</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {SEVERITY_ORDER.map((s) => (
                <div key={s.key} className="flex items-center gap-3">
                  <span className="w-16 text-xs text-fog-dim">{s.label}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-panel-raised">
                    <div
                      className={`h-full rounded-full ${s.color} transition-all duration-500`}
                      style={{ width: `${(summary.severity_breakdown[s.key] / maxSeverityCount) * 100}%` }}
                    />
                  </div>
                  <span className="w-6 text-right font-mono text-xs text-fog-dim">
                    {summary.severity_breakdown[s.key]}
                  </span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>

      <RecentThreats incidents={summary.recent_incidents} />
    </div>
  );
}
