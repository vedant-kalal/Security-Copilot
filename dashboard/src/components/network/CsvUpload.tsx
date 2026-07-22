import { UploadCloud } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError, api } from "@/lib/api-client";
import type { Device, NetworkUploadResult } from "@/types";

export function CsvUpload({ devices }: { devices: Device[] }) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [deviceId, setDeviceId] = useState<string | undefined>(devices[0]?.device_id);
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<NetworkUploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleFileSelected(file: File) {
    if (!deviceId) {
      setError("Register a device first.");
      return;
    }
    setIsUploading(true);
    setError(null);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("device_id", deviceId);
      formData.append("file", file);
      const response = await api.postForm<NetworkUploadResult>("/network/upload", formData);
      setResult(response);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UploadCloud className="h-4 w-4 text-sentinel" />
          CSV Log Upload
        </CardTitle>
        <CardDescription>
          Upload a network flow CSV export for immediate Isolation Forest analysis.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
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

        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleFileSelected(file);
          }}
        />
        <Button
          variant="outline"
          className="w-full"
          disabled={isUploading || devices.length === 0}
          onClick={() => fileInputRef.current?.click()}
        >
          {isUploading ? "Analyzing..." : "Choose CSV file"}
        </Button>

        {error && <p className="text-sm text-threat-critical">{error}</p>}

        {result && (
          <div className="grid grid-cols-3 gap-3 rounded-md border border-panel-line bg-panel-raised/50 p-3 text-center">
            <div>
              <p className="font-display text-lg font-semibold text-fog">{result.rows_ingested}</p>
              <p className="text-[11px] text-fog-faint">Rows</p>
            </div>
            <div>
              <p className="font-display text-lg font-semibold text-threat-medium">{result.anomalies_detected}</p>
              <p className="text-[11px] text-fog-faint">Anomalies</p>
            </div>
            <div>
              <p className="font-display text-lg font-semibold text-threat-critical">{result.incidents_created}</p>
              <p className="text-[11px] text-fog-faint">Incidents</p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
