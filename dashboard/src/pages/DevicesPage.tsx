import { Laptop2, Puzzle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api-client";
import { formatRelativeTime } from "@/lib/utils";
import type { Device } from "@/types";

export function DevicesPage() {
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const result = await api.get<Device[]>("/devices");
      setDevices(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load devices");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-xl font-semibold text-fog">Devices</h2>
        <p className="text-sm text-fog-dim">
          Devices are registered automatically by the SentinelAI browser extension when you sign in.
        </p>
      </div>

      {!devices && !error && <Skeleton className="h-48" />}
      {error && <p className="text-sm text-threat-critical">{error}</p>}

      {devices && devices.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <Puzzle className="h-8 w-8 text-fog-faint" />
            <div>
              <p className="text-sm font-medium text-fog">No devices registered yet</p>
              <p className="mt-1 text-sm text-fog-dim">
                Install the SentinelAI browser extension and sign in to register your first device — see{" "}
                <code className="rounded bg-panel-raised px-1 py-0.5 font-mono text-xs">extension/README.md</code>{" "}
                for setup.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {devices && devices.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {devices.map((device) => (
            <Card key={device.device_id}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Laptop2 className="h-4 w-4 text-sentinel" />
                  {device.browser}
                </CardTitle>
                <CardDescription>{device.os}</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="font-mono text-xs text-fog-faint">
                  Last seen {formatRelativeTime(device.last_seen)}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
