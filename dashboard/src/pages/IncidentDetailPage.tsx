import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { AIExplanation } from "@/components/incidents/AIExplanation";
import { EvidenceList } from "@/components/incidents/EvidenceList";
import { IncidentTimeline } from "@/components/incidents/IncidentTimeline";
import { MitreChips } from "@/components/incidents/MitreChips";
import { PlaybooksDialog } from "@/components/incidents/PlaybooksDialog";
import { SeverityBadge } from "@/components/incidents/SeverityBadge";
import { StatusBadge } from "@/components/incidents/StatusBadge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { STATUS_LABELS } from "@/lib/constants";
import { formatDateTime, formatPercent } from "@/lib/utils";
import { useIncidentDetail } from "@/hooks/useIncidents";
import type { IncidentStatus } from "@/types";

export function IncidentDetailPage() {
  const { incidentId } = useParams<{ incidentId: string }>();
  const { incident, isLoading, error, updateStatus } = useIncidentDetail(incidentId);

  if (isLoading) {
    return <Skeleton className="h-96" />;
  }

  if (error || !incident) {
    return <p className="text-sm text-threat-critical">{error ?? "Incident not found"}</p>;
  }

  return (
    <div className="space-y-6">
      <Link to="/incidents" className="inline-flex items-center gap-1.5 text-sm text-fog-dim hover:text-sentinel">
        <ArrowLeft className="h-4 w-4" />
        Back to Investigation
      </Link>

      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="font-display text-2xl font-semibold text-fog">{incident.title}</h2>
            <SeverityBadge severity={incident.severity} />
          </div>
          <p className="mt-2 max-w-2xl text-sm text-fog-dim">{incident.summary}</p>
          <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-fog-faint">
            <span className="font-mono">Confidence {formatPercent(incident.confidence)}</span>
            <span className="font-mono">Detected {formatDateTime(incident.created_at)}</span>
          </div>
          <div className="mt-3">
            <MitreChips techniques={incident.mitre} />
          </div>
        </div>

        <div className="flex items-center gap-2">
          <StatusBadge status={incident.status} />
          <Select value={incident.status} onValueChange={(v) => void updateStatus(v as IncidentStatus)}>
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(STATUS_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <AIExplanation responses={incident.ai_responses} />
        <IncidentTimeline incident={incident} evidence={incident.evidence_entries} />
      </div>

      <EvidenceList evidence={incident.evidence_entries} />

      <div className="flex justify-end">
        <PlaybooksDialog incidentId={incident.incident_id} />
      </div>
    </div>
  );
}
