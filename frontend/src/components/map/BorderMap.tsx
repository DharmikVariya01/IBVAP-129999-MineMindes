import React, { useState, useMemo, useEffect, useRef } from 'react';
import { MapContainer, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import { CameraMarker } from './CameraMarker';
import { ActivityMarker } from './ActivityMarker';
import { MapLegend } from './MapLegend';
import { MapControls } from './MapControls';
import { UnmappedCamerasList } from './UnmappedCamerasList';
import { parseCoordinates } from '@/utils/coordinates';
import { cn } from '@/utils/cn';
import type { Camera, Alert } from '@/types/api';

export interface BorderMapProps {
  cameras: Camera[];
  alerts?: Alert[];
  cameraActivityMap?: Record<string, { activeTrackCount: number; lastActivityTimestamp?: string }>;
  onSelectCamera?: (cameraId: string) => void;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  className?: string;
}

// Controller component to interact with Leaflet map instance
const MapController: React.FC<{
  bounds: L.LatLngBounds | null;
  fitTrigger: number;
  onInitMap: (map: L.Map) => void;
}> = ({ bounds, fitTrigger, onInitMap }) => {
  const map = useMap();

  useEffect(() => {
    onInitMap(map);
  }, [map, onInitMap]);

  useEffect(() => {
    if (bounds && bounds.isValid() && fitTrigger > 0) {
      try {
        map.fitBounds(bounds, { padding: [50, 50], maxZoom: 16 });
      } catch {
        // Graceful fallback if bounds fail
      }
    }
  }, [bounds, fitTrigger, map]);

  return null;
};

export const BorderMap: React.FC<BorderMapProps> = ({
  cameras,
  alerts = [],
  cameraActivityMap = {},
  onSelectCamera,
  onRefresh,
  isRefreshing = false,
  className,
}) => {
  const mapRef = useRef<L.Map | null>(null);
  const [fitTrigger, setFitTrigger] = useState<number>(1);
  const [isLegendVisible, setIsLegendVisible] = useState<boolean>(true);
  const [isUnmappedVisible, setIsUnmappedVisible] = useState<boolean>(false);

  // 1. Group active alerts by camera_id
  const cameraAlertsMap = useMemo(() => {
    const map: Record<string, Alert[]> = {};
    alerts.forEach((alert) => {
      // Only group ACTIVE alerts
      if (alert.status === 'ACTIVE') {
        // Backend alert.camera_id might be a number (camera surrogate id) or string
        const camIdKey = String(alert.camera_id);
        if (!map[camIdKey]) {
          map[camIdKey] = [];
        }
        map[camIdKey].push(alert);

        // Also check if metadata contains camera_id string
        const metaCamId = alert.alert_metadata?.camera_id as string | undefined;
        if (metaCamId && metaCamId !== camIdKey) {
          if (!map[metaCamId]) {
            map[metaCamId] = [];
          }
          map[metaCamId].push(alert);
        }
      }
    });
    return map;
  }, [alerts]);

  // 2. Classify cameras into Mapped (valid GPS coordinates) and Unmapped
  const { mappedCameras, unmappedCameras, bounds, defaultCenter } = useMemo(() => {
    const mapped: Array<{ camera: Camera; coords: { lat: number; lng: number } }> = [];
    const unmapped: Camera[] = [];

    cameras.forEach((cam) => {
      const coords = parseCoordinates(cam.location);
      if (coords) {
        mapped.push({ camera: cam, coords });
      } else {
        unmapped.push(cam);
      }
    });

    // Calculate map bounds and center
    let calculatedBounds: L.LatLngBounds | null = null;
    let center: [number, number] = [28.6139, 77.209]; // Default standard border sector center

    if (mapped.length > 0) {
      const latLngs = mapped.map((m) => L.latLng(m.coords.lat, m.coords.lng));
      calculatedBounds = L.latLngBounds(latLngs);
      const boundsCenter = calculatedBounds.getCenter();
      center = [boundsCenter.lat, boundsCenter.lng];
    }

    return {
      mappedCameras: mapped,
      unmappedCameras: unmapped,
      bounds: calculatedBounds,
      defaultCenter: center,
    };
  }, [cameras]);

  // Handler for custom zoom controls
  const handleZoomIn = () => {
    mapRef.current?.zoomIn();
  };

  const handleZoomOut = () => {
    mapRef.current?.zoomOut();
  };

  const handleFitBounds = () => {
    if (bounds && bounds.isValid() && mapRef.current) {
      mapRef.current.fitBounds(bounds, { padding: [50, 50], maxZoom: 16 });
    }
    setFitTrigger((prev) => prev + 1);
  };

  return (
    <div
      className={cn(
        'relative w-full h-[550px] lg:h-[650px] rounded-lg overflow-hidden border border-surveillance-800 shadow-2xl tactical-map-container',
        className
      )}
      data-testid="border-map-container"
    >
      {/* 1. Primary Leaflet Map Viewport */}
      <MapContainer
        center={defaultCenter}
        zoom={mappedCameras.length > 0 ? 13 : 6}
        scrollWheelZoom={true}
        zoomControl={false}
        className="w-full h-full"
        style={{ height: '100%', width: '100%', background: '#090d16' }}
      >
        <MapController
          bounds={bounds}
          fitTrigger={fitTrigger}
          onInitMap={(map) => {
            mapRef.current = map;
          }}
        />

        {/* Dark Tactical Filtered TileLayer */}
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          className="tactical-tiles"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> | IBVAP SIH26187'
          maxZoom={19}
        />

        {/* Render Mapped Camera Markers */}
        {mappedCameras.map(({ camera, coords }) => {
          const camAlerts =
            cameraAlertsMap[camera.camera_id] ||
            cameraAlertsMap[String(camera.id)] ||
            [];
          const activity = cameraActivityMap[camera.camera_id];

          return (
            <React.Fragment key={`cam-group-${camera.camera_id}`}>
              {/* Optional Camera Activity Radar/Pulse */}
              {activity && activity.activeTrackCount > 0 && (
                <ActivityMarker
                  cameraId={camera.camera_id}
                  cameraName={camera.name}
                  coordinates={coords}
                  activeTrackCount={activity.activeTrackCount}
                  lastActivityTimestamp={activity.lastActivityTimestamp}
                />
              )}

              {/* Main Camera Marker */}
              <CameraMarker
                camera={camera}
                coordinates={coords}
                activeAlerts={camAlerts}
                onSelectCamera={onSelectCamera}
              />
            </React.Fragment>
          );
        })}
      </MapContainer>

      {/* 2. Tactical Floating Controls (Top-Right) */}
      <div className="absolute top-3 right-3 z-[1000]">
        <MapControls
          onZoomIn={handleZoomIn}
          onZoomOut={handleZoomOut}
          onFitBounds={mappedCameras.length > 0 ? handleFitBounds : undefined}
          onRefresh={onRefresh}
          isRefreshing={isRefreshing}
          onToggleLegend={() => setIsLegendVisible((prev) => !prev)}
          isLegendVisible={isLegendVisible}
          onToggleUnmapped={() => setIsUnmappedVisible((prev) => !prev)}
          isUnmappedVisible={isUnmappedVisible}
          unmappedCount={unmappedCameras.length}
        />
      </div>

      {/* 3. Tactical Map Legend (Bottom-Left) */}
      {isLegendVisible && (
        <div className="absolute bottom-3 left-3 z-[1000] max-w-xs">
          <MapLegend />
        </div>
      )}

      {/* 4. Unmapped Cameras Panel (Top-Left or Toggleable) */}
      {isUnmappedVisible && unmappedCameras.length > 0 && (
        <div className="absolute top-3 left-3 z-[1000]">
          <UnmappedCamerasList
            cameras={unmappedCameras}
            cameraAlertsMap={cameraAlertsMap}
            onSelectCamera={onSelectCamera}
            onClose={() => setIsUnmappedVisible(false)}
          />
        </div>
      )}

      {/* 5. Informational Alert if all cameras lack GPS coordinates */}
      {cameras.length > 0 && mappedCameras.length === 0 && (
        <div
          role="status"
          className="absolute top-4 left-1/2 -translate-x-1/2 z-[1000] p-3 rounded-lg bg-surveillance-900/95 border border-tactical-amber/50 text-amber-200 text-xs font-mono shadow-2xl flex items-center gap-2.5 max-w-md pointer-events-auto"
          data-testid="no-gps-banner"
        >
          <span className="h-2 w-2 rounded-full bg-tactical-amber animate-ping" />
          <span>
            {cameras.length} camera(s) registered, but no valid GPS coordinates found in location strings. See Unmapped Units panel.
          </span>
          <button
            type="button"
            onClick={() => setIsUnmappedVisible(true)}
            className="px-2 py-1 bg-surveillance-800 hover:bg-surveillance-750 text-amber-100 rounded border border-surveillance-700 text-[10px] uppercase font-bold"
          >
            View
          </button>
        </div>
      )}
    </div>
  );
};
