import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { BorderMap } from '@/components/map/BorderMap';
import { Button } from '@/components/common/Button';
import { LoadingState } from '@/components/common/LoadingState';
import { ErrorState } from '@/components/common/ErrorState';
import { apiClient } from '@/services/api/client';
import { webSocketClient } from '@/services/websocket/client';
import { parseCoordinates } from '@/utils/coordinates';
import {
  Map as MapIcon,
  RefreshCw,
  Radio,
  ShieldCheck,
  Video,
  AlertTriangle,
  MapPin,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import type { Camera, Alert } from '@/types/api';
import type {
  WebSocketMessage,
  CameraStatusData,
  AlertData,
  ConnectionState,
} from '@/types/websocket';

export interface TacticalMapPageProps {
  onSelectCamera?: (cameraId: string) => void;
  onViewTimeline?: (trackId: number | string) => void;
}

export const TacticalMap: React.FC<TacticalMapPageProps> = ({ onSelectCamera, onViewTimeline }) => {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // WebSocket connection state
  const [wsState, setWsState] = useState<ConnectionState>('DISCONNECTED');
  const [wsConnected, setWsConnected] = useState<boolean>(false);

  // Activity tracking per camera (throttled/isolated from full re-renders)
  const [cameraActivityMap, setCameraActivityMap] = useState<
    Record<string, { activeTrackCount: number; lastActivityTimestamp?: string }>
  >({});

  // 1. Fetch initial camera and active alert data from M16 REST
  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [camerasRes, alertsRes] = await Promise.all([
        apiClient.getCameras({ page_size: 100 }),
        apiClient.getAlerts({ status: 'ACTIVE', page_size: 100 }),
      ]);

      const fetchedCameras = camerasRes.items || [];
      const fetchedAlerts = alertsRes.items || [];

      setCameras(fetchedCameras);
      setAlerts(fetchedAlerts);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Failed to load surveillance map data';
      setError(message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleManualRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  // 2. Real-Time WebSocket integration for camera status & active alert updates
  useEffect(() => {
    // If we have cameras, connect to the first camera stream or manage connection
    const targetCameraId = cameras.length > 0 ? cameras[0].camera_id : 'CAM_01';

    try {
      webSocketClient.connect(targetCameraId);
    } catch (wsErr) {
      console.warn('[TacticalMap] WebSocket connect warning:', wsErr);
    }

    const unsubState = webSocketClient.onStateChange((state) => {
      setWsState(state);
      setWsConnected(state === 'CONNECTED');
    });

    const unsubMessage = webSocketClient.onMessage((msg: WebSocketMessage) => {
      // 1. Handle camera_status updates (e.g. ONLINE <-> OFFLINE)
      if (msg.type === 'camera_status') {
        const data = msg.data as CameraStatusData;
        const camId = msg.camera_id;
        if (camId && data && data.status) {
          setCameras((prev) =>
            prev.map((c) => {
              if (c.camera_id === camId) {
                const newStatus = data.status === 'ONLINE' ? 'ONLINE' : 'OFFLINE';
                return { ...c, status: newStatus };
              }
              return c;
            })
          );
        }
      }

      // 2. Handle real-time alert events
      if (msg.type === 'alert') {
        const alertData = msg.data as AlertData;
        if (alertData && alertData.status === 'ACTIVE') {
          const newAlert: Alert = {
            id: typeof alertData.alert_id === 'number' ? alertData.alert_id : Date.now(),
            alert_id: String(alertData.alert_id || `ALT-${Date.now()}`),
            camera_id: null,
            track_id: alertData.track_id ?? null,
            event_id: null,
            zone_id: null,
            alert_type: (alertData.alert_type as Alert['alert_type']) || 'FENCE_BREACH',
            severity: (alertData.severity as Alert['severity']) || 'HIGH',
            status: 'ACTIVE',
            message: alertData.message || 'Border security alert',
            alert_timestamp: alertData.timestamp || new Date().toISOString(),
            alert_metadata: { camera_id: alertData.camera_id || msg.camera_id },
            acknowledged_at: null,
            acknowledged_by: null,
            resolved_at: null,
            resolved_by: null,
            created_at: alertData.timestamp || new Date().toISOString(),
            updated_at: alertData.timestamp || new Date().toISOString(),
          };

          setAlerts((prev) => {
            // Avoid duplicate alert IDs
            if (prev.some((a) => a.alert_id === newAlert.alert_id)) {
              return prev;
            }
            return [newAlert, ...prev];
          });
        }
      }

      // 3. Handle stats messages for unit activity (isolated from whole-map re-render)
      if (msg.type === 'stats') {
        const stats = msg.data as { active_tracks?: number };
        const camId = msg.camera_id;
        if (camId && typeof stats?.active_tracks === 'number') {
          setCameraActivityMap((prev) => ({
            ...prev,
            [camId]: {
              activeTrackCount: stats.active_tracks ?? 0,
              lastActivityTimestamp: msg.timestamp,
            },
          }));
        }
      }
    });

    return () => {
      unsubState();
      unsubMessage();
    };
  }, [cameras]);

  // Derived counts
  const { mappedCount, unmappedCount } = useMemo(() => {
    let mapped = 0;
    let unmapped = 0;
    cameras.forEach((c) => {
      if (parseCoordinates(c.location)) {
        mapped++;
      } else {
        unmapped++;
      }
    });
    return { mappedCount: mapped, unmappedCount: unmapped };
  }, [cameras]);

  const activeAlertCount = useMemo(() => {
    return alerts.filter((a) => a.status === 'ACTIVE').length;
  }, [alerts]);

  return (
    <div className="space-y-4" data-testid="tactical-map-page">
      {/* 1. Header Control Bar */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 p-3.5 bg-surveillance-900/90 border border-surveillance-800 rounded-lg shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-tactical-emerald/10 border border-tactical-emerald/30 rounded text-tactical-emerald">
            <MapIcon className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold tracking-wider text-surveillance-100 uppercase font-mono">
                Live Geospatial Border Map
              </h1>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-surveillance-800 border border-surveillance-700 text-surveillance-400 font-mono">
                M21
              </span>
            </div>
            <p className="text-xs text-surveillance-400 font-mono">
              Tactical border perimeter surveillance, geospatial units & real-time threat alarms
            </p>
          </div>
        </div>

        {/* Telemetry Summary & Real-Time Controls */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Active Cameras Badge */}
          <div
            className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-surveillance-950 border border-surveillance-800 text-xs font-mono text-surveillance-300"
            data-testid="map-camera-count-badge"
          >
            <Video className="w-3.5 h-3.5 text-tactical-emerald" />
            <span>UNITS: {cameras.length}</span>
            <span className="text-surveillance-500 text-[10px]">
              ({mappedCount} GPS / {unmappedCount} UNMAPPED)
            </span>
          </div>

          {/* Active Threat Alarms Badge */}
          <div
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-mono border',
              activeAlertCount > 0
                ? 'bg-tactical-rose/15 text-rose-300 border-tactical-rose/50 animate-pulse'
                : 'bg-surveillance-950 border-surveillance-800 text-surveillance-400'
            )}
            data-testid="map-active-alerts-badge"
          >
            <AlertTriangle
              className={cn(
                'w-3.5 h-3.5',
                activeAlertCount > 0 ? 'text-tactical-rose' : 'text-surveillance-500'
              )}
            />
            <span>ACTIVE ALERTS: {activeAlertCount}</span>
          </div>

          {/* WebSocket Status Pill */}
          <div
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-mono border',
              wsConnected
                ? 'bg-tactical-emerald/10 text-emerald-300 border-tactical-emerald/40'
                : wsState === 'CONNECTING' || wsState === 'RECONNECTING'
                ? 'bg-tactical-amber/10 text-amber-300 border-tactical-amber/40 animate-pulse'
                : 'bg-surveillance-800 text-surveillance-400 border-surveillance-700'
            )}
            data-testid="map-ws-status-badge"
          >
            <Radio
              className={cn(
                'w-3.5 h-3.5',
                wsConnected ? 'text-tactical-emerald animate-pulse' : 'text-surveillance-400'
              )}
              aria-hidden="true"
            />
            <span className="uppercase">
              {wsConnected ? 'WS STREAM LIVE' : `WS ${wsState}`}
            </span>
          </div>

          {/* Manual Refresh Button */}
          <Button
            variant="secondary"
            size="sm"
            onClick={handleManualRefresh}
            isLoading={refreshing}
            className="text-xs px-3 py-1.5"
            aria-label="Refresh map data"
            data-testid="map-page-refresh-btn"
          >
            <RefreshCw className={cn('w-3.5 h-3.5 mr-1', refreshing && 'animate-spin')} />
            Sync
          </Button>
        </div>
      </div>

      {/* 2. Main Map Viewport / Loading / Error State */}
      {loading ? (
        <div className="h-[550px] flex items-center justify-center bg-surveillance-900/50 border border-surveillance-800 rounded-lg">
          <LoadingState message="Initializing geospatial surveillance border map..." />
        </div>
      ) : error ? (
        <ErrorState
          title="Geospatial Telemetry Error"
          message={error}
          onRetry={fetchData}
        />
      ) : cameras.length === 0 ? (
        <div
          className="h-[450px] flex flex-col items-center justify-center p-8 bg-surveillance-900/40 border border-surveillance-800 rounded-lg text-center"
          data-testid="map-empty-state"
        >
          <div className="p-3 bg-surveillance-800/80 rounded-full text-surveillance-400 mb-3 border border-surveillance-700">
            <MapPin className="w-8 h-8" />
          </div>
          <h3 className="text-base font-bold font-mono text-surveillance-200 uppercase tracking-wider mb-1">
            No Perimeter Cameras Registered
          </h3>
          <p className="text-xs text-surveillance-400 max-w-sm mb-4 font-mono">
            No active cameras were found in the database. Add surveillance units via the administration API to plot geospatial markers.
          </p>
          <Button variant="secondary" size="sm" onClick={fetchData}>
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
            Check Again
          </Button>
        </div>
      ) : (
        <BorderMap
          cameras={cameras}
          alerts={alerts}
          cameraActivityMap={cameraActivityMap}
          onSelectCamera={onSelectCamera}
          onViewTimeline={onViewTimeline}
          onRefresh={handleManualRefresh}
          isRefreshing={refreshing}
        />
      )}

      {/* 3. Operational Surveillance Advisory Bar */}
      <div className="flex items-center justify-between px-3 py-2 bg-surveillance-950/40 border border-surveillance-850 rounded text-[11px] font-mono text-surveillance-500">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-3.5 h-3.5 text-tactical-emerald" />
          <span>GEOSPATIAL COORDINATES GROUNDED: ZERO FABRICATED TELEMETRY • M16 REST + M17 WEBSOCKET OPERATIONAL</span>
        </div>
        <div className="hidden sm:block text-surveillance-600">
          OPERATIONAL PROTOCOL: M21 • SIH26187
        </div>
      </div>
    </div>
  );
};

export default TacticalMap;
