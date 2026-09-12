/**
 * React hook for IBVAP M24 — Tactical Camera Prioritization & Alert Sorting.
 *
 * Coordinates:
 * 1. Initial REST fetch of cameras and active security alerts
 * 2. Ingestion of real-time alerts & camera status updates from existing stream
 * 3. Dynamic recalculation of camera priorities and tactical order
 * 4. Alert acknowledgement integration without inventing lifecycle states
 * 5. Complete decoupling from high-frequency video frames
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '@/services/api/client';
import { normalizeWsAlert } from '@/hooks/useAlerts';
import {
  sortCamerasByPriority,
  calculatePrioritySummary,
} from '@/utils/prioritization';
import type { Alert, Camera } from '@/types/api';
import type { AlertData, CameraStreamStatus } from '@/types/websocket';
import type {
  PrioritizedCamera,
  PrioritySummaryCounts,
} from '@/types/prioritization';

export interface UseCameraPrioritizationOptions {
  autoFetch?: boolean;
}

export interface UseCameraPrioritizationReturn {
  cameras: Camera[];
  alerts: Alert[];
  prioritizedCameras: PrioritizedCamera[];
  summaryCounts: PrioritySummaryCounts;
  loading: boolean;
  error: string | null;
  sortByPriority: boolean;
  setSortByPriority: (value: boolean | ((prev: boolean) => boolean)) => void;
  refresh: () => Promise<void>;
  handleIncomingAlert: (alertData: AlertData, fallbackCamId?: string) => void;
  handleCameraStatus: (status: CameraStreamStatus, targetCamId?: string) => void;
  acknowledgeAlert: (alertId: string) => Promise<boolean>;
}

export function useCameraPrioritization(
  options?: UseCameraPrioritizationOptions
): UseCameraPrioritizationReturn {
  const { autoFetch = true } = options || {};

  const [cameras, setCameras] = useState<Camera[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [sortByPriority, setSortByPriority] = useState<boolean>(true);

  // 1. Initial REST Hydration
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [camerasRes, alertsRes] = await Promise.all([
        apiClient.getCameras({ page: 1, page_size: 100 }),
        apiClient.getAlerts({ status: 'ACTIVE', page: 1, page_size: 100 }),
      ]);

      setCameras(camerasRes.items || []);
      setAlerts(alertsRes.items || []);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load prioritization data';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (autoFetch) {
      fetchData();
    }
  }, [autoFetch, fetchData]);

  // 2. Real-time alert ingestion from WebSocket (piggybacks on existing stream)
  const handleIncomingAlert = useCallback((alertData: AlertData, fallbackCamId?: string) => {
    if (!alertData || !alertData.alert_id) return;

    const normalized = normalizeWsAlert(alertData, fallbackCamId);

    setAlerts((prev) => {
      const existingIdx = prev.findIndex((a) => a.alert_id === normalized.alert_id);
      if (existingIdx >= 0) {
        // Update existing alert status
        const next = [...prev];
        next[existingIdx] = normalized;
        return next;
      }
      // Prepend newly arrived alert
      return [normalized, ...prev];
    });
  }, []);

  // 3. Real-time camera status update from WebSocket
  const handleCameraStatus = useCallback((status: CameraStreamStatus, targetCamId?: string) => {
    if (!status || !targetCamId) return;

    setCameras((prev) =>
      prev.map((cam) => {
        if (cam.camera_id === targetCamId) {
          const mappedStatus = status === 'ONLINE' ? 'ONLINE' : 'OFFLINE';
          if (cam.status !== mappedStatus) {
            return { ...cam, status: mappedStatus };
          }
        }
        return cam;
      })
    );
  }, []);

  // 4. Alert acknowledgement
  const acknowledgeAlert = useCallback(
    async (alertId: string): Promise<boolean> => {
      try {
        const updated = await apiClient.patchAlertStatus(alertId, {
          status: 'ACKNOWLEDGED',
          acknowledged_by: 'Operator (HQ-01)',
        });

        // Update local alert in state so active alert list recalculates immediately
        setAlerts((prev) =>
          prev.map((a) => (a.alert_id === alertId ? updated : a))
        );
        return true;
      } catch {
        return false;
      }
    },
    []
  );

  // 5. Memoized deterministic prioritization calculation
  const prioritizedCameras = useMemo(() => {
    return sortCamerasByPriority(cameras, alerts);
  }, [cameras, alerts]);

  // 6. Summary counts
  const summaryCounts = useMemo(() => {
    return calculatePrioritySummary(prioritizedCameras);
  }, [prioritizedCameras]);

  return {
    cameras,
    alerts,
    prioritizedCameras,
    summaryCounts,
    loading,
    error,
    sortByPriority,
    setSortByPriority,
    refresh: fetchData,
    handleIncomingAlert,
    handleCameraStatus,
    acknowledgeAlert,
  };
}
