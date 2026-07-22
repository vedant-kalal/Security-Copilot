import { useEffect, useState } from "react";

import { IncidentTable } from "@/components/incidents/IncidentTable";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api-client";
import type { Incident, PaginatedResponse } from "@/types";

const SEVERITY_RANK: Record<Incident["severity"], number> = { critical: 0, high: 1, medium: 2, low: 3 };

export function SecurityOperationsPage() {
  const [incidents, setIncidents] = useState<Incident[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [open, investigating] = await Promise.all([
          api.get<PaginatedResponse<Incident>>("/incidents", { status: "open", page_size: 100 }),
          api.get<PaginatedResponse<Incident>>("/incidents", { status: "investigating", page_size: 100 }),
        ]);
        const merged = [...open.items, ...investigating.items].sort(
          (a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]
        );
        setIncidents(merged);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load security operations data");
      }
    }
    void load();
  }, []);

  const criticalCount = incidents?.filter((i) => i.severity === "critical").length ?? 0;
  const highCount = incidents?.filter((i) => i.severity === "high").length ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-xl font-semibold text-fog">Security Operations</h2>
        <p className="text-sm text-fog-dim">Active incidents requiring analyst attention, ranked by severity.</p>
      </div>

      {incidents && (criticalCount > 0 || highCount > 0) && (
        <Card className="border-threat-critical/30 bg-threat-critical/5">
          <CardContent className="flex items-center gap-3 py-4">
            <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-threat-critical" />
            <p className="text-sm text-fog">
              {criticalCount > 0 && <span className="font-semibold text-threat-critical">{criticalCount} critical</span>}
              {criticalCount > 0 && highCount > 0 && " and "}
              {highCount > 0 && <span className="font-semibold text-threat-high">{highCount} high</span>}
              {" "}severity incident{criticalCount + highCount === 1 ? "" : "s"} need attention.
            </p>
          </CardContent>
        </Card>
      )}

      {!incidents && !error && <Skeleton className="h-96" />}
      {error && <p className="text-sm text-threat-critical">{error}</p>}
      {incidents && <IncidentTable incidents={incidents} />}
    </div>
  );
}
