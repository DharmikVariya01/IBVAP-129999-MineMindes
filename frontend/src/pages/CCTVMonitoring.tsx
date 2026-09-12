import React, { useState, useMemo } from 'react';
import { useCameraStream } from '@/hooks/useCameraStream';
import { CameraSelector } from '@/components/cctv/CameraSelector';
import { LiveVideo } from '@/components/cctv/LiveVideo';
import { ConnectionStatus } from '@/components/cctv/ConnectionStatus';
import { CameraStatus } from '@/components/cctv/CameraStatus';
import { LiveStats } from '@/components/cctv/LiveStats';
import { Video, ShieldCheck, Crosshair, History } from 'lucide-react';

export interface CCTVMonitoringProps {
  initialCameraId?: string | null;
  onViewTimeline?: (trackId: number | string) => void;
}

export const CCTVMonitoring: React.FC<CCTVMonitoringProps> = ({
  initialCameraId = null,
  onViewTimeline,
}) => {
  const [selectedCameraId, setSelectedCameraId] = useState<string | null>(initialCameraId);

  // Stream management for the selected camera feed
  const {
    connectionState,
    cameraStatus,
    cameraStatusDetails,
    stats,
    latestFrame,
    error,
    frameCount,
  } = useCameraStream(selectedCameraId, { autoConnect: true });

  const handleSelectCamera = (cameraId: string) => {
    setSelectedCameraId(cameraId);
  };

  // Real-time active tracks detected in current frame metadata
  const activeTracksList = useMemo(() => {
    if (!latestFrame?.metadata) return [];
    const raw = (latestFrame.metadata.tracks ||
      latestFrame.metadata.tracked_objects ||
      latestFrame.metadata.detections ||
      []) as Array<{ track_id?: number | string; id?: number | string; class_name?: string; label?: string }>;
    if (!Array.isArray(raw)) return [];
    return raw
      .map((t) => ({
        id: t.track_id ?? t.id,
        label: t.class_name || t.label || 'Target',
      }))
      .filter((t) => t.id !== undefined && t.id !== null);
  }, [latestFrame?.metadata]);

  return (
    <div className="space-y-4" data-testid="cctv-monitoring-page">
      {/* 1. Header Control Bar */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 p-3.5 bg-surveillance-900/90 border border-surveillance-800 rounded-lg shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-tactical-emerald/10 border border-tactical-emerald/30 rounded text-tactical-emerald">
            <Video className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold tracking-wider text-surveillance-100 uppercase font-mono">
                Live CCTV Monitoring
              </h1>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-surveillance-800 border border-surveillance-700 text-surveillance-400 font-mono">
                M19
              </span>
            </div>
            <p className="text-xs text-surveillance-400 font-mono">
              Border perimeter real-time visual stream & AI tracking overlay
            </p>
          </div>
        </div>

        {/* Camera Selector & Live Badges */}
        <div className="flex flex-wrap items-center gap-2.5">
          <CameraSelector
            selectedCameraId={selectedCameraId}
            onSelectCamera={handleSelectCamera}
          />
          {selectedCameraId && (
            <>
              <ConnectionStatus state={connectionState} />
              <CameraStatus status={cameraStatus} details={cameraStatusDetails} />
            </>
          )}
        </div>
      </div>

      {/* 2. Main Live CCTV Viewport */}
      <div className="w-full">
        <LiveVideo
          frame={latestFrame}
          cameraId={selectedCameraId}
          connectionState={connectionState}
          cameraStatus={cameraStatus}
          error={error}
        />
      </div>

      {/* 2b. Active Tracks Inspection Bar (M22 Timeline Integration) */}
      {activeTracksList.length > 0 && onViewTimeline && (
        <div
          className="flex items-center gap-2 p-2.5 bg-surveillance-900/90 border border-surveillance-800 rounded-lg text-xs font-mono overflow-x-auto scrollbar-none"
          data-testid="cctv-active-tracks-bar"
        >
          <span className="text-surveillance-400 flex items-center gap-1 text-[11px] uppercase tracking-wider flex-shrink-0">
            <Crosshair className="w-3.5 h-3.5 text-tactical-cyan" />
            Detected Targets:
          </span>
          {activeTracksList.map((tr) => (
            <button
              key={`cctv-track-${tr.id}`}
              type="button"
              onClick={() => onViewTimeline(tr.id!)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-surveillance-950 hover:bg-surveillance-850 text-surveillance-200 hover:text-tactical-cyan border border-surveillance-700 hover:border-tactical-cyan/40 transition-colors flex-shrink-0"
              data-testid={`cctv-inspect-track-${tr.id}`}
              title={`Inspect timeline for Track #${tr.id}`}
            >
              <span className="text-tactical-cyan font-bold">#{tr.id}</span>
              <span className="text-surveillance-400 text-[10px]">({tr.label})</span>
              <History className="w-3 h-3 text-surveillance-500 ml-0.5" />
            </button>
          ))}
        </div>
      )}

      {/* 3. Live Telemetry & Stats Bar */}
      <LiveStats stats={stats} frameCount={frameCount} />

      {/* 4. Operational Surveillance Advisory */}
      <div className="flex items-center justify-between px-3 py-2 bg-surveillance-950/40 border border-surveillance-850 rounded text-[11px] font-mono text-surveillance-500">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-3.5 h-3.5 text-tactical-emerald" />
          <span>REAL-TIME STREAMING: M17 PROTOCOL ENFORCED (ZERO INVENTED TELEMETRY)</span>
        </div>
        <div className="hidden sm:block text-surveillance-600">
          SECURE CHANNEL: TLS/WSS • SIH26187
        </div>
      </div>
    </div>
  );
};

export default CCTVMonitoring;
