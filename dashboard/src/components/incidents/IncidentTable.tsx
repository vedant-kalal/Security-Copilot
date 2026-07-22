import { Link } from "react-router-dom";

import { MitreChips } from "@/components/incidents/MitreChips";
import { SeverityBadge } from "@/components/incidents/SeverityBadge";
import { StatusBadge } from "@/components/incidents/StatusBadge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime, formatPercent } from "@/lib/utils";
import type { Incident } from "@/types";

export function IncidentTable({ incidents }: { incidents: Incident[] }) {
  if (incidents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-panel-line py-16 text-center">
        <p className="text-sm text-fog-dim">No incidents match this filter.</p>
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Incident</TableHead>
          <TableHead>Severity</TableHead>
          <TableHead>Confidence</TableHead>
          <TableHead>MITRE</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Detected</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {incidents.map((incident) => (
          <TableRow key={incident.incident_id}>
            <TableCell className="max-w-xs">
              <Link to={`/incidents/${incident.incident_id}`} className="font-medium text-fog hover:text-sentinel">
                {incident.title}
              </Link>
            </TableCell>
            <TableCell>
              <SeverityBadge severity={incident.severity} />
            </TableCell>
            <TableCell className="font-mono text-mono-tabular text-fog-dim">
              {formatPercent(incident.confidence)}
            </TableCell>
            <TableCell>
              <MitreChips techniques={incident.mitre} />
            </TableCell>
            <TableCell>
              <StatusBadge status={incident.status} />
            </TableCell>
            <TableCell className="font-mono text-xs text-fog-faint">{formatDateTime(incident.created_at)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
