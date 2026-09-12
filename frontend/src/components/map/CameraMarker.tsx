import React, { useMemo } from 'react';
import { Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import { CameraMarkerPopup } from './CameraMarkerPopup';
import type { Camera, Alert } from '@/types/api';

export interface CameraMarkerProps {
  camera: Camera;
  coordinates: { lat: number; lng: number };
  activeAlerts?: Alert[];
  onSelectCamera?: (cameraId: string) => void;
}

/**
 * Creates a Leaflet divIcon representing a camera with online/offline and active alert states.
 */
function createCameraIcon(camera: Camera, hasActiveAlert: boolean): L.DivIcon {
  const isOnline = camera.status === 'ONLINE';

  const borderColor = hasActiveAlert
    ? '#f43f5e' // tactical-rose
    : isOnline
    ? '#10b981' // tactical-emerald
    : '#64748b'; // surveillance-500

  const bgColor = hasActiveAlert
    ? '#2d121e'
    : isOnline
    ? '#09211c'
    : '#1e293b';

  const pulseClass = hasActiveAlert ? 'animate-tactical-pulse-alert' : '';

  // Accessible SVG camera icon
  const iconSvg = isOnline
    ? `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="${borderColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 8-6 4 6 4V8Z"/><rect width="14" height="12" x="2" y="6" rx="2" ry="2"/></svg>`
    : `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="${borderColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 16 6 4V8l-6 4"/><path d="m2 2 20 20"/><path d="M7 7H4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h12a2 2 0 0 0 1.414-.586"/><path d="M9.828 4.172A2 2 0 0 1 12 4h4a2 2 0 0 1 2 2v4.172"/></svg>`;

  const alertBadge = hasActiveAlert
    ? `<span style="position: absolute; top: -4px; right: -4px; width: 10px; height: 10px; background-color: #f43f5e; border-radius: 9999px; border: 2px solid #0f172a;"></span>`
    : '';

  const html = `
    <div style="position: relative; display: flex; flex-direction: column; align-items: center;" data-testid="marker-container-${camera.camera_id}">
      <div class="${pulseClass}" style="
        width: 34px;
        height: 34px;
        border-radius: 9999px;
        background-color: ${bgColor};
        border: 2px solid ${borderColor};
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.6);
        cursor: pointer;
        position: relative;
      ">
        ${iconSvg}
        ${alertBadge}
      </div>
      <div style="
        margin-top: 3px;
        padding: 1px 5px;
        background-color: rgba(15, 23, 42, 0.9);
        border: 1px solid rgba(51, 65, 85, 0.8);
        border-radius: 4px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 9px;
        font-weight: 600;
        color: ${hasActiveAlert ? '#fda4af' : isOnline ? '#a7f3d0' : '#94a3b8'};
        white-space: nowrap;
        pointer-events: none;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
      ">
        ${camera.camera_id}
      </div>
    </div>
  `;

  return L.divIcon({
    html,
    className: 'custom-tactical-camera-marker',
    iconSize: [34, 52],
    iconAnchor: [17, 17],
    popupAnchor: [0, -18],
  });
}

export const CameraMarker: React.FC<CameraMarkerProps> = React.memo(
  ({ camera, coordinates, activeAlerts = [], onSelectCamera }) => {
    const hasActiveAlert = activeAlerts.length > 0;

    const icon = useMemo(
      () => createCameraIcon(camera, hasActiveAlert),
      [camera.camera_id, camera.status, hasActiveAlert]
    );

    return (
      <Marker
        position={[coordinates.lat, coordinates.lng]}
        icon={icon}
        title={`${camera.camera_id} (${camera.status})`}
      >
        <Popup className="tactical-leaflet-popup" minWidth={260} maxWidth={280}>
          <CameraMarkerPopup
            camera={camera}
            coordinates={coordinates}
            activeAlerts={activeAlerts}
            onSelectCamera={onSelectCamera}
          />
        </Popup>
      </Marker>
    );
  }
);

CameraMarker.displayName = 'CameraMarker';
