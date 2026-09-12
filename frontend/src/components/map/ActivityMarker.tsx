import React, { useMemo } from 'react';
import { Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import { Radio } from 'lucide-react';

/**
 * ACTIVITY MARKER ARCHITECTURAL NOTE & LIMITATION DOCUMENTATION:
 *
 * M17 WebSocket frame messages provide tracking bounding boxes in video image
 * pixel coordinates (e.g. bbox_x1, bbox_y1 from 0 to frame_width/height).
 *
 * The IBVAP backend does NOT provide geographic (GPS/lat-lng) world-coordinates
 * for individual moving objects/tracks within the video frame.
 *
 * PER SPECIFICATION RULE #7:
 * - We strictly DO NOT invent or fake GPS coordinates for tracked objects.
 * - We never pretend image pixel coordinates are GPS coordinates.
 * - Live activity is represented geospatially at the camera's known location
 *   as a camera-associated activity pulse.
 */

export interface ActivityMarkerProps {
  cameraId: string;
  cameraName?: string;
  coordinates: { lat: number; lng: number };
  activeTrackCount?: number;
  lastActivityTimestamp?: string;
}

function createActivityIcon(): L.DivIcon {
  const html = `
    <div style="position: relative; width: 44px; height: 44px; display: flex; align-items: center; justify-content: center;" data-testid="activity-pulse-marker">
      <div style="
        position: absolute;
        width: 40px;
        height: 40px;
        border-radius: 9999px;
        background-color: rgba(6, 182, 212, 0.15);
        border: 1.5px dashed rgba(6, 182, 212, 0.7);
        pointer-events: none;
      "></div>
      <div style="
        width: 8px;
        height: 8px;
        border-radius: 9999px;
        background-color: #06b6d4;
        box-shadow: 0 0 8px #06b6d4;
      "></div>
    </div>
  `;

  return L.divIcon({
    html,
    className: 'custom-tactical-activity-marker',
    iconSize: [44, 44],
    iconAnchor: [22, 22],
    popupAnchor: [0, -22],
  });
}

export const ActivityMarker: React.FC<ActivityMarkerProps> = ({
  cameraId,
  cameraName,
  coordinates,
  activeTrackCount = 0,
  lastActivityTimestamp,
}) => {
  const icon = useMemo(() => createActivityIcon(), []);

  if (activeTrackCount <= 0) {
    return null;
  }

  return (
    <Marker position={[coordinates.lat, coordinates.lng]} icon={icon}>
      <Popup className="tactical-leaflet-popup" minWidth={220}>
        <div className="p-2.5 bg-surveillance-900 text-surveillance-100 font-mono text-xs">
          <div className="flex items-center gap-1.5 pb-1.5 mb-1.5 border-b border-surveillance-800 text-tactical-cyan font-bold">
            <Radio className="w-3.5 h-3.5" />
            <span>UNIT LIVE ACTIVITY</span>
          </div>
          <div className="space-y-1 text-[11px] text-surveillance-300">
            <div>
              CAMERA: <span className="text-surveillance-100">{cameraId}</span>
            </div>
            {cameraName && (
              <div className="text-[10px] text-surveillance-400">{cameraName}</div>
            )}
            <div className="text-tactical-cyan font-semibold">
              ACTIVE TRACKS: {activeTrackCount}
            </div>
            {lastActivityTimestamp && (
              <div className="text-[9px] text-surveillance-500">
                LAST DETECTED: {new Date(lastActivityTimestamp).toLocaleTimeString()}
              </div>
            )}
            <div className="text-[9px] text-surveillance-500 pt-1 border-t border-surveillance-850 italic">
              Geospatial activity associated at unit perimeter location.
            </div>
          </div>
        </div>
      </Popup>
    </Marker>
  );
};
