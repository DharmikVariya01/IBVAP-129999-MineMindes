import React, { useState } from 'react';
import { useCameraStream } from '@/hooks/useCameraStream';
import { CameraSelector } from '@/components/cctv/CameraSelector';
import { LiveVideo } from '@/components/cctv/LiveVideo';
import { ConnectionStatus } from '@/components/cctv/ConnectionStatus';
import { CameraStatus } from '@/components/cctv/CameraStatus';
import { LiveStats } from '@/components/cctv/LiveStats';
import { Video, ShieldCheck } from 'lucide-react';

export const CCTVMonitoring: React.FC = () => {
  const [selectedCameraId, setSelectedCameraId] = useState<string | null>(null);

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
