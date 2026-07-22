import { useEffect, useState } from "react";

import { CsvUpload } from "@/components/network/CsvUpload";
import { ReplayControl } from "@/components/network/ReplayControl";
import { api } from "@/lib/api-client";
import type { Device } from "@/types";

export function NetworkPage() {
  const [devices, setDevices] = useState<Device[]>([]);

  useEffect(() => {
    api
      .get<Device[]>("/devices")
      .then(setDevices)
      .catch(() => setDevices([]));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-xl font-semibold text-fog">Network Anomaly Detection</h2>
        <p className="text-sm text-fog-dim">
          The browser alone can't demonstrate infrastructure-level anomalies — upload real logs or replay a sample
          dataset so Isolation Forest has network traffic to analyze.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <CsvUpload devices={devices} />
        <ReplayControl devices={devices} />
      </div>
    </div>
  );
}
