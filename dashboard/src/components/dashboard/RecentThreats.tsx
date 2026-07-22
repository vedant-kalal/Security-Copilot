import { ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MitreChips } from "@/components/incidents/MitreChips";
import { SeverityBadge } from "@/components/incidents/SeverityBadge";
import { formatRelativeTime } from "@/lib/utils";
import type { Incident } from "@/types";

export function RecentThreats({ incidents }: { incidents: Incident[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent Threats</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        {incidents.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-10 text-center">
            <ShieldCheck className="h-8 w-8 text-sentinel" />
            <p className="text-sm text-fog-dim">No threats detected. All clear.</p>
          </div>
        )}
        {incidents.map((incident) => (
          <Link
            key={incident.incident_id}
            to={`/incidents/${incident.incident_id}`}
            className="flex items-center justify-between gap-4 rounded-md px-2 py-3 transition-colors hover:bg-panel-raised"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-fog">{incident.title}</p>
              <p className="mt-1 font-mono text-xs text-fog-faint">{formatRelativeTime(incident.created_at)}</p>
            </div>
            <div className="hidden sm:block">
              <MitreChips techniques={incident.mitre.slice(0, 2)} />
            </div>
            <SeverityBadge severity={incident.severity} />
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}
