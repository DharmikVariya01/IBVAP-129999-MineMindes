import React, { useEffect, useState } from 'react';
import { useAlerts } from '@/hooks/useAlerts';
import { AlertPanel } from '@/components/alerts/AlertPanel';
import { Button } from '@/components/common/Button';
import { apiClient } from '@/services/api/client';
import {
  Bell,
  RefreshCw,
  Radio,
  ShieldCheck,
  AlertTriangle,
  X,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import type { Camera } from '@/types/api';

export interface AlertsProps {
  onViewTimeline?: (trackId: number | string) => void;
  onSelectCamera?: (cameraId: string) => void;
}

export const Alerts: React.FC<AlertsProps> = ({ onViewTimeline, onSelectCamera }) => {
  const [selectedCameraId, setSelectedCameraId] = useState<string>('CAM_01');
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [cameraMap, setCameraMap] = useState<Record<string, string>>({});

  // 1. Alert State & WebSocket Stream
  const {
    alerts,
    loading,
    error,
    acknowledgingIds,
    ackError,
    newAlertIds,
    wsConnected,
    wsState,
    refresh,
    acknowledgeAlert,
    clearAckError,
    markAlertRead,
  } = useAlerts({ cameraId: selectedCameraId, autoConnectWs: true });

  // 2. Fetch Cameras for Reference
  useEffect(() => {
    let isMounted = true;
    apiClient
      .getCameras({ page_size: 50 })
      .then((res) => {
        if (!isMounted) return;
        const items = res.items || [];
        setCameras(items);

        const map: Record<string, string> = {};
        items.forEach((c) => {
          map[String(c.id)] = c.name || c.camera_id;
          map[c.camera_id] = c.name || c.camera_id;
        });
        setCameraMap(map);

        if (items.length > 0 && !items.some((c) => c.camera_id === selectedCameraId)) {
          setSelectedCameraId(items[0].camera_id);
        }
      })
      .catch(() => {
        // Fallback gracefully if camera service is temporarily unavailable
      });

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div className="space-y-4" data-testid="alerts-page">
      {/* 1. Header Control Bar */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 p-3.5 bg-surveillance-900/90 border border-surveillance-800 rounded-lg shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-tactical-rose/10 border border-tactical-rose/30 rounded text-tactical-rose">
            <Bell className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold tracking-wider text-surveillance-100 uppercase font-mono">
                Real-Time Alert Center
              </h1>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-surveillance-800 border border-surveillance-700 text-surveillance-400 font-mono">
                M20
              </span>
            </div>
            <p className="text-xs text-surveillance-400 font-mono">
              Border threat alerts, intrusion alarms & rapid operator acknowledgement
            </p>
          </div>
        </div>

        {/* Real-Time WebSocket & Camera Controls */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Stream Camera Selector */}
          {cameras.length > 0 && (
            <div className="flex items-center gap-1.5 text-xs font-mono">
              <label htmlFor="alert-camera-select" className="text-surveillance-400">
                Stream:
              </label>
              <select
                id="alert-camera-select"
                value={selectedCameraId}
                onChange={(e) => setSelectedCameraId(e.target.value)}
                className="px-2 py-1 bg-surveillance-950 border border-surveillance-700 rounded text-surveillance-100 text-xs focus:outline-none focus:ring-1 focus:ring-tactical-emerald"
                data-testid="alert-camera-select"
              >
                {cameras.map((c, idx) => (
                  <option key={`${c.camera_id || c.id}_${idx}`} value={c.camera_id}>
                    {c.camera_id} ({c.name || 'Perimeter'})
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* WebSocket Connection Status Pill */}
          <div
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-mono border',
              wsConnected
                ? 'bg-tactical-emerald/10 text-emerald-300 border-tactical-emerald/40'
                : wsState === 'CONNECTING' || wsState === 'RECONNECTING'
                ? 'bg-tactical-amber/10 text-amber-300 border-tactical-amber/40 animate-pulse'
                : 'bg-surveillance-800 text-surveillance-400 border-surveillance-700'
            )}
            data-testid="ws-status-badge"
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
            onClick={refresh}
            isLoading={loading}
            className="text-xs px-3 py-1.5"
            aria-label="Refresh alerts list"
            data-testid="refresh-alerts-btn"
          >
            <RefreshCw className={cn('w-3.5 h-3.5 mr-1', loading && 'animate-spin')} />
            Sync
          </Button>
        </div>
      </div>

      {/* 2. Acknowledgement Failure Warning Banner */}
      {ackError && (
        <div
          role="alert"
          className="p-3 bg-tactical-rose/15 border border-tactical-rose/40 rounded-lg flex items-center justify-between gap-3 text-xs text-rose-200 font-mono"
          data-testid="ack-error-banner"
        >
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-tactical-rose flex-shrink-0" />
            <span>{ackError}</span>
          </div>
          <button
            type="button"
            onClick={clearAckError}
            aria-label="Dismiss error notification"
            className="p-1 hover:bg-tactical-rose/20 rounded transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* 3. Operational Alert Panel */}
      <AlertPanel
        alerts={alerts}
        loading={loading}
        error={error}
        acknowledgingIds={acknowledgingIds}
        newAlertIds={newAlertIds}
        onAcknowledge={acknowledgeAlert}
        onViewTimeline={onViewTimeline}
        onSelectCamera={onSelectCamera}
        onRefresh={refresh}
        onMarkRead={markAlertRead}
        cameraNameMap={cameraMap}
      />

      {/* 4. Operational Surveillance Advisory */}
      <div className="flex items-center justify-between px-3 py-2 bg-surveillance-950/40 border border-surveillance-850 rounded text-[11px] font-mono text-surveillance-500">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-3.5 h-3.5 text-tactical-emerald" />
          <span>REAL-TIME THREAT TRIAGE: M16 REST + M17 WEBSOCKET OPERATIONAL</span>
        </div>
        <div className="hidden sm:block text-surveillance-600">
          OPERATOR ID: HQ-01 • AUDIT LOGGED
        </div>
      </div>
    </div>
  );
};

export default Alerts;
