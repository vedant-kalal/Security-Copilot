import { useState } from "react";

import { IncidentTable } from "@/components/incidents/IncidentTable";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { STATUS_LABELS } from "@/lib/constants";
import { useIncidents } from "@/hooks/useIncidents";
import type { IncidentStatus } from "@/types";

export function IncidentsPage() {
  const [statusFilter, setStatusFilter] = useState<IncidentStatus | "all">("all");
  const { data, isLoading, error } = useIncidents(statusFilter === "all" ? undefined : statusFilter);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-xl font-semibold text-fog">Investigation</h2>
          <p className="text-sm text-fog-dim">Timeline, evidence, and AI-guided response for every incident.</p>
        </div>
        <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as IncidentStatus | "all")}>
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading && <Skeleton className="h-96" />}
      {error && <p className="text-sm text-threat-critical">{error}</p>}
      {data && <IncidentTable incidents={data.items} />}
    </div>
  );
}
