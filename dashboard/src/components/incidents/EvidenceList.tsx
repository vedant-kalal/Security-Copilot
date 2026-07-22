import { FileSearch } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatPercent } from "@/lib/utils";
import type { EvidenceEntry } from "@/types";

export function EvidenceList({ evidence }: { evidence: EvidenceEntry[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileSearch className="h-4 w-4 text-sentinel" />
          Evidence
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {evidence.length === 0 && <p className="text-sm text-fog-dim">No evidence recorded.</p>}
        {evidence.map((item) => (
          <div key={item.evidence_id} className="rounded-md border border-panel-line bg-panel-raised/50 p-3">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm text-fog">{item.reason}</p>
              <span className="shrink-0 font-mono text-xs text-sentinel">{formatPercent(item.score)}</span>
            </div>
            {item.event && (
              <p className="mt-2 font-mono text-[11px] text-fog-faint">
                {item.event.event_type} &middot; {new Date(item.event.timestamp).toLocaleString()}
              </p>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
