import React from 'react';
import { Video, VideoOff, AlertTriangle, ExternalLink, MapPin } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { Camera, Alert } from '@/types/api';

export interface CameraMarkerPopupProps {
  camera: Camera;
  coordinates: { lat: number; lng: number } | null;
  activeAlerts?: Alert[];
  onSelectCamera?: (cameraId: string) => void;
}

export const CameraMarkerPopup: React.FC<CameraMarkerPopupProps> = ({
  camera,
  coordinates,
  activeAlerts = [],
  onSelectCamera,
}) => {
  const isOnline = camera.status === 'ONLINE';
  const hasActiveAlert = activeAlerts.length > 0;
  const latestAlert = hasActiveAlert ? activeAlerts[0] : null;

  return (
    <div
      className="p-3.5 bg-surveillance-900 text-surveillance-100 font-sans text-xs w-64 rounded-lg select-text"
      data-testid={`camera-popup-${camera.camera_id}`}
    >
      {/* Header: Camera ID & Online Status Badge */}
      <div className="flex items-center justify-between pb-2 mb-2.5 border-b border-surveillance-800">
        <div className="flex items-center gap-1.5 min-w-0">
          <div
            className={cn(
              'p-1 rounded border flex-shrink-0',
              hasActiveAlert
                ? 'bg-tactical-rose/20 text-tactical-rose border-tactical-rose/50'
                : isOnline
                ? 'bg-tactical-emerald/20 text-tactical-emerald border-tactical-emerald/50'
                : 'bg-surveillance-800 text-surveillance-400 border-surveillance-700'
            )}
          >
            {isOnline ? (
              <Video className="w-3.5 h-3.5" aria-hidden="true" />
            ) : (
              <VideoOff className="w-3.5 h-3.5" aria-hidden="true" />
            )}
          </div>
          <div className="min-w-0">
            <h4 className="font-mono font-bold text-surveillance-100 text-xs tracking-wider truncate">
              {camera.camera_id}
            </h4>
            <p className="text-[10px] text-surveillance-400 truncate">
              {camera.name || 'Perimeter Unit'}
            </p>
          </div>
        </div>

        {/* Status Pill */}
        <span
          className={cn(
            'text-[10px] font-mono px-1.5 py-0.5 rounded border uppercase tracking-wider font-semibold flex-shrink-0',
            isOnline
              ? 'bg-tactical-emerald/10 text-tactical-emerald border-tactical-emerald/30'
              : 'bg-surveillance-800 text-surveillance-400 border-surveillance-700'
          )}
          data-testid="camera-popup-status"
        >
          {camera.status}
        </span>
      </div>

      {/* Location Details */}
      <div className="space-y-1.5 font-mono text-[11px] mb-3">
        <div className="flex items-start gap-1.5 text-surveillance-300">
          <MapPin className="w-3.5 h-3.5 text-surveillance-400 mt-0.5 flex-shrink-0" />
          <div className="min-w-0">
            <div className="text-surveillance-200 truncate">
              {camera.location || 'Location Unspecified'}
            </div>
            {coordinates && (
              <div className="text-[10px] text-surveillance-500">
                GPS: {coordinates.lat.toFixed(5)}, {coordinates.lng.toFixed(5)}
              </div>
            )}
          </div>
        </div>

        {/* Source Type / Reference */}
        <div className="text-[10px] text-surveillance-400 flex items-center justify-between pt-1 border-t border-surveillance-850">
          <span>SOURCE:</span>
          <span className="font-mono text-surveillance-300 uppercase">
            {camera.source_type}
          </span>
        </div>
      </div>

      {/* Active Alerts Banner if Present */}
      {hasActiveAlert && (
        <div
          className="mb-3 p-2 rounded bg-tactical-rose/15 border border-tactical-rose/40 text-[11px]"
          data-testid="camera-popup-alerts"
        >
          <div className="flex items-center justify-between text-tactical-rose font-bold mb-1">
            <span className="flex items-center gap-1 font-mono">
              <AlertTriangle className="w-3 h-3" />
              ACTIVE ALERTS ({activeAlerts.length})
            </span>
            {latestAlert && (
              <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-tactical-rose/20 uppercase border border-tactical-rose/30">
                {latestAlert.severity}
              </span>
            )}
          </div>
          {latestAlert && (
            <p className="text-[10px] text-rose-200 line-clamp-2">
              {latestAlert.message || `${latestAlert.alert_type} detected`}
            </p>
          )}
        </div>
      )}

      {/* Operational Action: View Camera in CCTV */}
      {onSelectCamera && (
        <button
          type="button"
          onClick={() => onSelectCamera(camera.camera_id)}
          className="w-full flex items-center justify-center gap-1.5 py-1.5 px-3 rounded bg-surveillance-800 hover:bg-surveillance-750 text-surveillance-100 hover:text-tactical-emerald border border-surveillance-700 hover:border-tactical-emerald/50 transition-colors font-mono text-[11px] font-semibold focus:outline-none focus:ring-1 focus:ring-tactical-emerald"
          data-testid={`popup-view-camera-btn-${camera.camera_id}`}
        >
          <Video className="w-3.5 h-3.5" />
          <span>View Live Stream</span>
          <ExternalLink className="w-3 h-3 ml-0.5 opacity-70" />
        </button>
      )}
    </div>
  );
};
