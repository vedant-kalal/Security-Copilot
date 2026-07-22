import { Radar } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError, api } from "@/lib/api-client";
import type { Device } from "@/types";

interface ReplayResponse {
  replay_id: string;
  dataset: string;
  rows_scheduled: number;
  status: string;
}

const DATASETS = [
  { value: "cicids2017", label: "CICIDS2017 (sample)" },
  { value: "unsw-nb15", label: "UNSW-NB15 (sample)" },
];

export function ReplayControl({ devices }: { devices: Device[] }) {
  const [dataset, setDataset] = useState(DATASETS[0].value);
  const [deviceId, setDeviceId] = useState<string | undefined>(devices[0]?.device_id);
  const [isStarting, setIsStarting] = useState(false);
  const [result, setResult] = useState<ReplayResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function startReplay() {
    setIsStarting(true);
    setError(null);
    setResult(null);
    try {
      const response = await api.post<ReplayResponse>("/network/replay/start", {
        dataset,
        device_id: deviceId,
        max_rows: 150,
        speed: 15,
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start replay");
    } finally {
      setIsStarting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Radar className="h-4 w-4 text-sentinel" />
          Dataset Replay
        </CardTitle>
        <CardDescription>
          Replay a sample CICIDS2017/UNSW-NB15 dataset as live telemetry to demonstrate network anomaly detection.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Select value={dataset} onValueChange={setDataset}>
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DATASETS.map((d) => (
              <SelectItem key={d.value} value={d.value}>
                {d.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {devices.length > 1 && (
          <Select value={deviceId} onValueChange={setDeviceId}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Select a device" />
            </SelectTrigger>
            <SelectContent>
              {devices.map((d) => (
                <SelectItem key={d.device_id} value={d.device_id}>
                  {d.browser} on {d.os}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        <Button className="w-full" disabled={isStarting || devices.length === 0} onClick={() => void startReplay()}>
          {isStarting ? "Starting..." : "Start Replay"}
        </Button>

        {error && <p className="text-sm text-threat-critical">{error}</p>}
        {result && (
          <p className="rounded-md border border-sentinel/30 bg-sentinel/10 p-3 text-sm text-sentinel">
            Replay scheduled: {result.rows_scheduled} rows from {result.dataset}. Watch the Investigation tab for
            incidents as they appear.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
