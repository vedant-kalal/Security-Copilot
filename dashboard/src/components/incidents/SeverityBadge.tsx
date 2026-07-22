import { Badge } from "@/components/ui/badge";
import { SEVERITY_LABELS } from "@/lib/constants";
import type { IncidentSeverity } from "@/types";

export function SeverityBadge({ severity }: { severity: IncidentSeverity }) {
  return <Badge variant={severity}>{SEVERITY_LABELS[severity]}</Badge>;
}
