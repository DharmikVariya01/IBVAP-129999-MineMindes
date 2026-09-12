/**
 * React hook for IBVAP M20 Real-Time Alerts & Acknowledgement.
 *
 * Coordinates:
 * 1. Initial REST alerts loading via apiClient.getAlerts()
 * 2. Real-time M17 WebSocket alert ingestion via WebSocketClient
 * 3. In-memory deduplication by alert_id
 * 4. Alert lifecycle state transitions via PATCH /api/v1/alerts/{alert_id}
 * 5. Complete decoupling of alert state from high-frequency video frames
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiClient, ApiError } from '@/services/api/client';
import { WebSocketClient } from '@/services/websocket/client';
import type { Alert, AlertSeverity, AlertStatus, AlertType } from '@/types/api';
import type { AlertData, ConnectionState, WebSocketMessage } from '@/types/websocket';

export interface UseAlertsOptions {
  cameraId?: string | null;
  autoConnectWs?: boolean;
  pageSize?: number;
}

export interface UseAlertsReturn {
  alerts: Alert[];
  activeAlertsCount: number;
  totalAlertsCount: number;
  loading: boolean;
  error: string | null;
  acknowledgingIds: Set<string>;
  ackError: string | null;
  newAlertIds: Set<string>;
  wsConnected: boolean;
  wsState: ConnectionState;
  refresh: () => Promise<void>;
  acknowledgeAlert: (alertId: string, operator?: string) => Promise<boolean>;
  clearAckError: () => void;
  markAlertRead: (alertId: string) => void;
}

/**
 * Normalize an incoming WebSocket AlertData payload into the canonical Alert interface.
 */
export function normalizeWsAlert(wsAlert: AlertData, fallbackCameraId?: string): Alert {
  const alertIdStr = String(wsAlert.alert_id);
  const numericId =
    typeof wsAlert.alert_id === 'number'
      ? wsAlert.alert_id
      : parseInt(alertIdStr.replace(/\D/g, ''), 10) || Date.now();

  const rawCam = wsAlert.camera_id || fallbackCameraId || 'CAM_01';
  const numericCam = parseInt(String(rawCam).replace(/\D/g, ''), 10);

  return {
    id: numericId,
    alert_id: alertIdStr,
    camera_id: isNaN(numericCam) ? null : numericCam,
    track_id: wsAlert.track_id !== undefined ? wsAlert.track_id : null,
    event_id: null,
    zone_id: null,
    alert_type: (wsAlert.alert_type as AlertType) || 'FENCE_BREACH',
    severity: (wsAlert.severity as AlertSeverity) || 'MEDIUM',
    status: (wsAlert.status as AlertStatus) || 'ACTIVE',
    message: wsAlert.message || 'Security alert triggered',
    alert_timestamp: wsAlert.timestamp || new Date().toISOString(),
    alert_metadata: {
      ...(wsAlert.zone_info ? { zone_info: wsAlert.zone_info } : {}),
      camera_code: rawCam,
      evidence_reference: wsAlert.evidence_reference,
    },
    acknowledged_at: null,
    acknowledged_by: null,
    resolved_at: null,
    resolved_by: null,
    created_at: wsAlert.timestamp || new Date().toISOString(),
    updated_at: wsAlert.timestamp || new Date().toISOString(),
  };
}

export function useAlerts(options?: UseAlertsOptions): UseAlertsReturn {
  const { cameraId, autoConnectWs = true, pageSize = 50 } = options || {};

  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [ackError, setAckError] = useState<string | null>(null);
  const [acknowledgingIds, setAcknowledgingIds] = useState<Set<string>>(new Set());
  const [newAlertIds, setNewAlertIds] = useState<Set<string>>(new Set());
  const [wsState, setWsState] = useState<ConnectionState>('DISCONNECTED');

  const clientRef = useRef<WebSocketClient | null>(null);
  const alertsMapRef = useRef<Map<string, Alert>>(new Map());

  if (!clientRef.current) {
    clientRef.current = new WebSocketClient();
  }

  // 1. Initial REST Hydration
  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.getAlerts({
        page: 1,
        page_size: pageSize,
      });

      const loadedAlerts = response.items || [];
      const newMap = new Map<string, Alert>();

      loadedAlerts.forEach((item) => {
        newMap.set(item.alert_id, item);
      });

      alertsMapRef.current = newMap;
      setAlerts(Array.from(newMap.values()));
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : 'Failed to load alerts from backend';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [pageSize]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  // 2. Real-Time WebSocket Alerts Ingestion
  useEffect(() => {
    const client = clientRef.current;
    if (!client) return;

    const unsubs = [
      client.onStateChange((state) => {
        setWsState(state);
      }),

      client.onMessage((msg: WebSocketMessage) => {
        if (!msg || msg.type !== 'alert') {
          // Discard high-frequency frames, stats, heartbeat without altering alert state
          return;
        }

        const alertData = msg.data as AlertData;
        if (!alertData || !alertData.alert_id) {
          // Malformed message payload safely discarded
          return;
        }

        const normalized = normalizeWsAlert(alertData, msg.camera_id || cameraId || undefined);
        const alertId = normalized.alert_id;

        // Deduplication using alert_id
        alertsMapRef.current.set(alertId, normalized);

        setAlerts(Array.from(alertsMapRef.current.values()));

        // Mark as newly arrived if status is ACTIVE
        if (normalized.status === 'ACTIVE') {
          setNewAlertIds((prev) => new Set(prev).add(alertId));
        }
      }),
    ];

    if (autoConnectWs) {
      const targetCam = cameraId || 'CAM_01';
      try {
        client.connect(targetCam);
      } catch {
        // Socket connection errors handled via state handlers
      }
    }

    return () => {
      unsubs.forEach((unsub) => unsub());
      client.disconnect();
    };
  }, [cameraId, autoConnectWs]);

  // 3. Alert Acknowledgement Handler
  const acknowledgeAlert = useCallback(
    async (alertId: string, operator = 'Operator (HQ-01)'): Promise<boolean> => {
      setAckError(null);
      setAcknowledgingIds((prev) => new Set(prev).add(alertId));

      try {
        const updated = await apiClient.patchAlertStatus(alertId, {
          status: 'ACKNOWLEDGED',
          acknowledged_by: operator,
        });

        // Update local alert in state immediately
        alertsMapRef.current.set(alertId, updated);
        setAlerts(Array.from(alertsMapRef.current.values()));

        // Remove from new alert set once acknowledged
        setNewAlertIds((prev) => {
          const next = new Set(prev);
          next.delete(alertId);
          return next;
        });

        return true;
      } catch (err: unknown) {
        const msg = err instanceof ApiError ? err.message : `Failed to acknowledge alert ${alertId}`;
        setAckError(msg);
        return false;
      } finally {
        setAcknowledgingIds((prev) => {
          const next = new Set(prev);
          next.delete(alertId);
          return next;
        });
      }
    },
    []
  );

  const clearAckError = useCallback(() => {
    setAckError(null);
  }, []);

  const markAlertRead = useCallback((alertId: string) => {
    setNewAlertIds((prev) => {
      const next = new Set(prev);
      next.delete(alertId);
      return next;
    });
  }, []);

  // Compute Active Alert Count (status === 'ACTIVE')
  const activeAlertsCount = useMemo(() => {
    return alerts.filter((a) => a.status === 'ACTIVE').length;
  }, [alerts]);

  return {
    alerts,
    activeAlertsCount,
    totalAlertsCount: alerts.length,
    loading,
    error,
    acknowledgingIds,
    ackError,
    newAlertIds,
    wsConnected: wsState === 'CONNECTED',
    wsState,
    refresh: fetchAlerts,
    acknowledgeAlert,
    clearAckError,
    markAlertRead,
  };
}
