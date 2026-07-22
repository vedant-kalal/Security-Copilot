import { Clock } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime } from "@/lib/utils";
import type { EvidenceEntry, Incident } from "@/types";

interface TimelineEvent {
  label: string;
  timestamp: string;
  detail?: string;
}

function buildTimeline(incident: Incident, evidence: EvidenceEntry[]): TimelineEvent[] {
  const events: TimelineEvent[] = evidence
    .filter((e) => e.event)
    .map((e) => ({
      label: e.event!.event_type.replace(/_/g, " "),
      timestamp: e.event!.timestamp,
      detail: e.reason,
    }));

  events.push({ label: "Incident created", timestamp: incident.created_at, detail: incident.title });

  return events.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
}

export function IncidentTimeline({ incident, evidence }: { incident: Incident; evidence: EvidenceEntry[] }) {
  const timeline = buildTimeline(incident, evidence);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-sentinel" />
          Timeline
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ol className="relative space-y-5 border-l border-panel-line pl-5">
          {timeline.map((event, index) => (
            <li key={`${event.timestamp}-${index}`} className="relative">
              <span className="absolute -left-[26px] top-1 h-2.5 w-2.5 rounded-full border-2 border-void bg-sentinel" />
              <p className="text-sm font-medium capitalize text-fog">{event.label}</p>
              {event.detail && <p className="mt-0.5 text-xs text-fog-dim">{event.detail}</p>}
              <p className="mt-1 font-mono text-[11px] text-fog-faint">{formatDateTime(event.timestamp)}</p>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
