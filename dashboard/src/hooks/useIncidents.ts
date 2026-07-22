import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api-client";
import type { Incident, IncidentDetail, IncidentStatus, PaginatedResponse } from "@/types";

export function useIncidents(status?: IncidentStatus, page = 1, pageSize = 20) {
  const [data, setData] = useState<PaginatedResponse<Incident> | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await api.get<PaginatedResponse<Incident>>("/incidents", {
        status,
        page,
        page_size: pageSize,
      });
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load incidents");
    } finally {
      setIsLoading(false);
    }
  }, [status, page, pageSize]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { data, isLoading, error, refresh };
}

export function useIncidentDetail(incidentId: string | undefined) {
  const [incident, setIncident] = useState<IncidentDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!incidentId) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await api.get<IncidentDetail>(`/incidents/${incidentId}`);
      setIncident(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load incident");
    } finally {
      setIsLoading(false);
    }
  }, [incidentId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const updateStatus = useCallback(
    async (newStatus: IncidentStatus) => {
      if (!incidentId) return;
      const updated = await api.patch<IncidentDetail>(`/incidents/${incidentId}`, { status: newStatus });
      setIncident(updated);
    },
    [incidentId]
  );

  return { incident, isLoading, error, refresh, updateStatus };
}
