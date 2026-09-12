import React from 'react';
import { MapPinOff, Video, AlertTriangle, ExternalLink, X } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { Camera, Alert } from '@/types/api';

export interface UnmappedCamerasListProps {
  cameras: Camera[];
  cameraAlertsMap?: Record<string, Alert[]>;
  onSelectCamera?: (cameraId: string) => void;
  onClose?: () => void;
  className?: string;
}

export const UnmappedCamerasList: React.FC<UnmappedCamerasListProps> = ({
  cameras,
  cameraAlertsMap = {},
  onSelectCamera,
  onClose,
  className,
}) => {
  if (cameras.length === 0) {
    return null;
  }

  return (
    <div
      role="region"
      aria-label="Cameras without GPS coordinates"
      data-testid="unmapped-cameras-panel"
      className={cn(
        'bg-surveillance-900/95 border border-surveillance-800 rounded-lg shadow-2xl backdrop-blur-md flex flex-col max-h-80 w-80 font-mono text-xs overflow-hidden',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between p-3 bg-surveillance-950 border-b border-surveillance-800 flex-shrink-0">
        <div className="flex items-center gap-2">
          <MapPinOff className="w-4 h-4 text-tactical-amber flex-shrink-0" />
          <div>
            <div className="font-bold text-surveillance-100 text-[11px] uppercase tracking-wider">
              Unmapped Units ({cameras.length})
            </div>
            <div className="text-[10px] text-surveillance-400">
              GPS coordinates not specified in location
            </div>
          </div>
        </div>

        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close unmapped units panel"
            className="p-1 hover:bg-surveillance-800 rounded text-surveillance-400 hover:text-surveillance-200 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* Camera List */}
      <div className="divide-y divide-surveillance-850 overflow-y-auto p-1.5 space-y-1">
        {cameras.map((camera) => {
          const isOnline = camera.status === 'ONLINE';
          const alerts = cameraAlertsMap[camera.camera_id] || cameraAlertsMap[String(camera.id)] || [];
          const hasAlert = alerts.length > 0;

          return (
            <div
              key={camera.camera_id}
              className="p-2 rounded bg-surveillance-950/60 border border-surveillance-850/80 hover:border-surveillance-700 transition-colors flex flex-col gap-1.5"
              data-testid={`unmapped-camera-item-${camera.camera_id}`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 min-w-0">
                  <span
                    className={cn(
                      'h-2 w-2 rounded-full flex-shrink-0',
                      isOnline ? 'bg-tactical-emerald' : 'bg-surveillance-500'
                    )}
                  />
                  <span className="font-bold text-surveillance-100 truncate">
                    {camera.camera_id}
                  </span>
                  <span className="text-[10px] text-surveillance-400 truncate">
                    {camera.name}
                  </span>
                </div>

                <div className="flex items-center gap-1 flex-shrink-0">
                  {hasAlert && (
                    <span className="flex items-center gap-0.5 px-1 py-0.2 rounded bg-tactical-rose/20 text-tactical-rose border border-tactical-rose/40 text-[9px] font-bold">
                      <AlertTriangle className="w-2.5 h-2.5" />
                      {alerts.length}
                    </span>
                  )}
                  <span
                    className={cn(
                      'text-[9px] px-1 py-0.2 rounded border uppercase font-semibold',
                      isOnline
                        ? 'bg-tactical-emerald/10 text-tactical-emerald border-tactical-emerald/30'
                        : 'bg-surveillance-800 text-surveillance-400 border-surveillance-700'
                    )}
                  >
                    {camera.status}
                  </span>
                </div>
              </div>

              {/* Location Description */}
              <div className="text-[10px] text-surveillance-400 flex items-center justify-between">
                <span className="text-surveillance-500">Location:</span>
                <span className="text-surveillance-300 italic truncate max-w-[170px]">
                  {camera.location || 'None provided'}
                </span>
              </div>

              {/* Action */}
              {onSelectCamera && (
                <button
                  type="button"
                  onClick={() => onSelectCamera(camera.camera_id)}
                  className="w-full mt-0.5 flex items-center justify-center gap-1 py-1 rounded bg-surveillance-800 hover:bg-surveillance-750 text-surveillance-200 hover:text-tactical-emerald text-[10px] border border-surveillance-700 transition-colors"
                  data-testid={`unmapped-view-btn-${camera.camera_id}`}
                >
                  <Video className="w-3 h-3" />
                  <span>Open in CCTV</span>
                  <ExternalLink className="w-2.5 h-2.5 opacity-60 ml-0.5" />
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
