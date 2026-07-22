import { AlertTriangle, Laptop2, ShieldAlert, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { DashboardSummary } from "@/types";

function StatTile({
  label,
  value,
  icon,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  icon: ReactNode;
  tone?: "default" | "warning" | "danger";
}) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between p-5">
        <div>
          <p className="text-xs uppercase tracking-wide text-fog-faint">{label}</p>
          <p
            className={cn(
              "mt-1.5 font-display text-2xl font-semibold tabular-nums",
              tone === "danger" && "text-threat-critical",
              tone === "warning" && "text-threat-medium",
              tone === "default" && "text-fog"
            )}
          >
            {value}
          </p>
        </div>
        <div
          className={cn(
            "flex h-10 w-10 items-center justify-center rounded-md",
            tone === "danger" && "bg-threat-critical/10 text-threat-critical",
            tone === "warning" && "bg-threat-medium/10 text-threat-medium",
            tone === "default" && "bg-sentinel/10 text-sentinel"
          )}
        >
          {icon}
        </div>
      </CardContent>
    </Card>
  );
}

export function StatsGrid({ summary }: { summary: DashboardSummary }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <StatTile label="Devices Protected" value={summary.devices_protected} icon={<Laptop2 className="h-5 w-5" />} />
      <StatTile
        label="Incidents Today"
        value={summary.incidents_today}
        icon={<TrendingUp className="h-5 w-5" />}
        tone={summary.incidents_today > 0 ? "warning" : "default"}
      />
      <StatTile
        label="Open Incidents"
        value={summary.open_incidents}
        icon={summary.open_incidents > 0 ? <AlertTriangle className="h-5 w-5" /> : <ShieldAlert className="h-5 w-5" />}
        tone={summary.open_incidents > 0 ? "danger" : "default"}
      />
    </div>
  );
}
