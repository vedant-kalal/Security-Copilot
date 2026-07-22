import { Badge } from "@/components/ui/badge";
import { STATUS_LABELS } from "@/lib/constants";
import type { IncidentStatus } from "@/types";

const STATUS_VARIANT: Record<IncidentStatus, "sentinel" | "default" | "medium"> = {
  open: "medium",
  investigating: "medium",
  contained: "sentinel",
  resolved: "sentinel",
  dismissed: "default",
};

export function StatusBadge({ status }: { status: IncidentStatus }) {
  return <Badge variant={STATUS_VARIANT[status]}>{STATUS_LABELS[status]}</Badge>;
}
