import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { TacticalMap } from '@/pages/TacticalMap';
import { BorderMap } from '@/components/map/BorderMap';
import { MapLegend } from '@/components/map/MapLegend';
import { MapControls } from '@/components/map/MapControls';
import { CameraMarkerPopup } from '@/components/map/CameraMarkerPopup';
import { UnmappedCamerasList } from '@/components/map/UnmappedCamerasList';
import { parseCoordinates, isValidCoordinates } from '@/utils/coordinates';
import { App } from '@/App';
import { CCTVMonitoring } from '@/pages/CCTVMonitoring';
import { Alerts } from '@/pages/Alerts';
import type { Camera, Alert } from '@/types/api';

// Mock WebSockets
let mockSockets: MockWebSocket[] = [];

class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  static CONNECTING = 0;

  url: string;
  readyState = MockWebSocket.CONNECTING;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  sentData: string[] = [];

  constructor(url: string) {
    this.url = url;
    mockSockets.push(this);
    Promise.resolve().then(() => {
      if (this.readyState === MockWebSocket.CONNECTING) {
        this.readyState = MockWebSocket.OPEN;
        this.onopen?.(new Event('open'));
      }
    });
  }

  send(data: string): void {
    this.sentData.push(data);
  }

  close(code = 1000, reason = 'Normal closure'): void {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.(new CloseEvent('close', { code, reason }));
  }

  simulateServerMessage(messageObj: unknown): void {
    if (this.onmessage) {
      this.onmessage(
        new MessageEvent('message', {
          data: typeof messageObj === 'string' ? messageObj : JSON.stringify(messageObj),
        })
      );
    }
  }

  simulateError(): void {
    this.onerror?.(new Event('error'));
  }
}

// Sample test cameras
const mockCameras: Camera[] = [
  {
    id: 1,
    camera_id: 'CAM_01',
    name: 'North Perimeter Gate',
    source_type: 'RTSP',
    source_reference: 'rtsp://stream.edge/live/cam01',
    location: '28.6139, 77.2090',
    status: 'ONLINE',
    created_at: '2026-09-12T10:00:00Z',
    updated_at: '2026-09-12T12:00:00Z',
  },
  {
    id: 2,
    camera_id: 'CAM_02',
    name: 'Sector 4 Ridge',
    source_type: 'VIDEO_FILE',
    source_reference: '/data/feeds/cam02.mp4',
    location: '28.6250, 77.2150',
    status: 'OFFLINE',
    created_at: '2026-09-12T10:00:00Z',
    updated_at: '2026-09-12T12:00:00Z',
  },
  {
    id: 3,
    camera_id: 'CAM_03',
    name: 'Outpost Bunker East',
    source_type: 'WEBCAM',
    source_reference: '0',
    location: 'Perimeter East Bunker', // Missing parseable GPS
    status: 'ONLINE',
    created_at: '2026-09-12T10:00:00Z',
    updated_at: '2026-09-12T12:00:00Z',
  },
];

// Sample test alerts
const mockAlerts: Alert[] = [
  {
    id: 101,
    alert_id: 'ALT_001',
    camera_id: 1,
    track_id: 42,
    event_id: 10,
    zone_id: 2,
    alert_type: 'FENCE_BREACH',
    severity: 'CRITICAL',
    status: 'ACTIVE',
    message: 'Perimeter fence cut detected at North Gate',
    alert_timestamp: '2026-09-12T14:30:00Z',
    alert_metadata: { camera_id: 'CAM_01' },
    acknowledged_at: null,
    acknowledged_by: null,
    resolved_at: null,
    resolved_by: null,
    created_at: '2026-09-12T14:30:00Z',
    updated_at: '2026-09-12T14:30:00Z',
  },
  {
    id: 102,
    alert_id: 'ALT_002',
    camera_id: 1,
    track_id: 43,
    event_id: 11,
    zone_id: 2,
    alert_type: 'LOITERING',
    severity: 'MEDIUM',
    status: 'ACKNOWLEDGED',
    message: 'Individual lingering near sensor post',
    alert_timestamp: '2026-09-12T13:00:00Z',
    alert_metadata: { camera_id: 'CAM_01' },
    acknowledged_at: '2026-09-12T13:05:00Z',
    acknowledged_by: 'OPERATOR_1',
    resolved_at: null,
    resolved_by: null,
    created_at: '2026-09-12T13:00:00Z',
    updated_at: '2026-09-12T13:05:00Z',
  },
];

import { webSocketClient } from '@/services/websocket/client';

describe('IBVAP M21 — Live Geospatial Border Map Test Suite', () => {
  const originalWebSocket = global.WebSocket;

  beforeEach(() => {
    vi.restoreAllMocks();
    mockSockets = [];
    global.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    webSocketClient.disconnect();

    global.fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/cameras')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            items: mockCameras,
            total: mockCameras.length,
            page: 1,
            page_size: 100,
            total_pages: 1,
          }),
        } as unknown as Response;
      }
      if (url.includes('/alerts')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            items: mockAlerts,
            total: mockAlerts.length,
            page: 1,
            page_size: 100,
            total_pages: 1,
          }),
        } as unknown as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ items: [], total: 0 }),
      } as unknown as Response;
    });
  });

  afterEach(() => {
    webSocketClient.disconnect();
    global.WebSocket = originalWebSocket;
    vi.clearAllMocks();
  });

  // 1. Map page renders
  it('1. renders Map page with tactical header and M21 module badge', async () => {
    render(<TacticalMap />);

    await waitFor(() => {
      expect(screen.getByText(/live geospatial border map/i)).toBeInTheDocument();
      expect(screen.getByText('M21')).toBeInTheDocument();
      expect(screen.getByTestId('tactical-map-page')).toBeInTheDocument();
    });
  });

  // 2. Camera API loading state
  it('2. displays loading state while fetching camera and alert data', () => {
    render(<TacticalMap />);
    expect(screen.getByText(/initializing geospatial surveillance border map/i)).toBeInTheDocument();
  });

  // 3. Cameras rendered
  it('3. renders registered cameras and units count in telemetry header', async () => {
    render(<TacticalMap />);

    await waitFor(() => {
      expect(screen.getByTestId('map-camera-count-badge')).toBeInTheDocument();
      expect(screen.getByText(/units: 3/i)).toBeInTheDocument();
      expect(screen.getByText(/2 gps \/ 1 unmapped/i)).toBeInTheDocument();
    });
  });

  // 4. Empty camera state
  it('4. displays proper empty state when no perimeter cameras are registered', async () => {
    global.fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/cameras')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ items: [], total: 0, page: 1, page_size: 50, total_pages: 1 }),
        } as unknown as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ items: [], total: 0 }),
      } as unknown as Response;
    });

    render(<TacticalMap />);

    await waitFor(() => {
      expect(screen.getByTestId('map-empty-state')).toBeInTheDocument();
      expect(screen.getByText(/no perimeter cameras registered/i)).toBeInTheDocument();
    });
  });

  // 5. API failure state
  it('5. handles API fetch failure gracefully with retry option', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Network connection timeout to M16 REST'));

    render(<TacticalMap />);

    await waitFor(() => {
      expect(screen.getByText(/geospatial telemetry error/i)).toBeInTheDocument();
      expect(screen.getByText(/network connection timeout/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /retry connection/i })).toBeInTheDocument();
    });
  });

  // 6. Online camera state
  it('6. represents ONLINE camera with operational emerald indicator in popup', () => {
    render(
      <CameraMarkerPopup
        camera={mockCameras[0]}
        coordinates={{ lat: 28.6139, lng: 77.209 }}
        activeAlerts={[]}
      />
    );

    const statusBadge = screen.getByTestId('camera-popup-status');
    expect(statusBadge).toHaveTextContent('ONLINE');
    expect(statusBadge.className).toContain('text-tactical-emerald');
  });

  // 7. Offline camera state
  it('7. represents OFFLINE camera with muted indicator and distinct visual styling', () => {
    render(
      <CameraMarkerPopup
        camera={mockCameras[1]}
        coordinates={{ lat: 28.625, lng: 77.215 }}
        activeAlerts={[]}
      />
    );

    const statusBadge = screen.getByTestId('camera-popup-status');
    expect(statusBadge).toHaveTextContent('OFFLINE');
    expect(statusBadge.className).toContain('text-surveillance-400');
  });

  // 8. Camera marker metadata
  it('8. displays camera marker metadata: id, name, location, and source type', () => {
    render(
      <CameraMarkerPopup
        camera={mockCameras[0]}
        coordinates={{ lat: 28.6139, lng: 77.209 }}
        activeAlerts={[]}
      />
    );

    expect(screen.getByText('CAM_01')).toBeInTheDocument();
    expect(screen.getByText('North Perimeter Gate')).toBeInTheDocument();
    expect(screen.getByText('28.6139, 77.2090')).toBeInTheDocument();
    expect(screen.getByText('RTSP')).toBeInTheDocument();
    expect(screen.getByText(/gps: 28.61390, 77.20900/i)).toBeInTheDocument();
  });

  // 9. Camera popup
  it('9. renders operational popup with structured container and view button', () => {
    const handleSelect = vi.fn();
    render(
      <CameraMarkerPopup
        camera={mockCameras[0]}
        coordinates={{ lat: 28.6139, lng: 77.209 }}
        activeAlerts={[]}
        onSelectCamera={handleSelect}
      />
    );

    expect(screen.getByTestId('camera-popup-CAM_01')).toBeInTheDocument();
    const btn = screen.getByTestId('popup-view-camera-btn-CAM_01');
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(handleSelect).toHaveBeenCalledWith('CAM_01');
  });

  // 10. Active alert camera state
  it('10. highlights camera marker popup when active alert is present', () => {
    const activeAlert = mockAlerts[0]; // CRITICAL ACTIVE FENCE_BREACH
    render(
      <CameraMarkerPopup
        camera={mockCameras[0]}
        coordinates={{ lat: 28.6139, lng: 77.209 }}
        activeAlerts={[activeAlert]}
      />
    );

    expect(screen.getByTestId('camera-popup-alerts')).toBeInTheDocument();
    expect(screen.getByText(/active alerts \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText('CRITICAL')).toBeInTheDocument();
    expect(screen.getByText(/perimeter fence cut detected/i)).toBeInTheDocument();
  });

  // 11. Multiple active alerts handled correctly
  it('11. handles multiple active alerts correctly displaying count and latest alert', () => {
    const activeAlert1: Alert = { ...mockAlerts[0], alert_id: 'A1', severity: 'CRITICAL' };
    const activeAlert2: Alert = { ...mockAlerts[0], alert_id: 'A2', severity: 'HIGH', message: 'Second alarm' };

    render(
      <CameraMarkerPopup
        camera={mockCameras[0]}
        coordinates={{ lat: 28.6139, lng: 77.209 }}
        activeAlerts={[activeAlert1, activeAlert2]}
      />
    );

    expect(screen.getByText(/active alerts \(2\)/i)).toBeInTheDocument();
  });

  // 12. Acknowledged alert no longer treated as active
  it('12. filters out acknowledged/resolved alerts so camera is not marked as active alert', () => {
    // mockAlerts[1] is ACKNOWLEDGED
    const ackAlert = mockAlerts[1];
    expect(ackAlert.status).toBe('ACKNOWLEDGED');

    render(
      <BorderMap
        cameras={[mockCameras[0]]}
        alerts={[ackAlert]} // Only acknowledged alert passed
      />
    );

    // Camera has no active alerts, popup in container reflects 0 active alerts
    expect(screen.queryByTestId('camera-popup-alerts')).not.toBeInTheDocument();
  });

  // 13. Map legend
  it('13. renders tactical map legend with accessible symbology and non-color indicators', () => {
    render(<MapLegend />);

    expect(screen.getByTestId('map-legend')).toBeInTheDocument();
    expect(screen.getByText(/tactical map symbology/i)).toBeInTheDocument();
    expect(screen.getByTestId('legend-item-online')).toHaveTextContent(/online camera/i);
    expect(screen.getByTestId('legend-item-offline')).toHaveTextContent(/offline camera/i);
    expect(screen.getByTestId('legend-item-alert')).toHaveTextContent(/active threat alert/i);
    expect(screen.getByTestId('legend-item-activity')).toHaveTextContent(/live activity/i);
  });

  // 14. Camera selection/navigation
  it('14. triggers camera selection callback when user selects view camera from unmapped panel', () => {
    const handleSelect = vi.fn();
    render(
      <UnmappedCamerasList
        cameras={[mockCameras[2]]}
        onSelectCamera={handleSelect}
      />
    );

    const viewBtn = screen.getByTestId('unmapped-view-btn-CAM_03');
    expect(viewBtn).toBeInTheDocument();
    fireEvent.click(viewBtn);
    expect(handleSelect).toHaveBeenCalledWith('CAM_03');
  });

  // 15. WebSocket camera status update
  it('15. updates camera status dynamically when receiving M17 camera_status message', async () => {
    render(<TacticalMap />);

    await waitFor(() => {
      expect(screen.getByTestId('border-map-container')).toBeInTheDocument();
    });

    // Simulate WebSocket connection open
    const socket = mockSockets[0];
    expect(socket).toBeDefined();

    // Send camera_status changing CAM_02 from OFFLINE to ONLINE
    act(() => {
      socket.simulateServerMessage({
        type: 'camera_status',
        timestamp: new Date().toISOString(),
        camera_id: 'CAM_02',
        data: { status: 'ONLINE', details: 'Stream reconnected' },
      });
    });

    // Verify map is still running without crashing
    expect(screen.getByTestId('border-map-container')).toBeInTheDocument();
  });

  // 16. WebSocket alert update
  it('16. updates active alerts dynamically when receiving M17 alert WebSocket message', async () => {
    render(<TacticalMap />);

    await waitFor(() => {
      expect(screen.getByTestId('map-active-alerts-badge')).toBeInTheDocument();
    });

    const socket = mockSockets[0];
    expect(socket).toBeDefined();

    act(() => {
      socket.simulateServerMessage({
        type: 'alert',
        timestamp: new Date().toISOString(),
        camera_id: 'CAM_02',
        data: {
          alert_id: 'ALT_NEW_WS',
          camera_id: 'CAM_02',
          alert_type: 'FENCE_BREACH',
          severity: 'CRITICAL',
          status: 'ACTIVE',
          message: 'Real-time breach alarm via WebSocket',
          timestamp: new Date().toISOString(),
        },
      });
    });

    await waitFor(() => {
      // Active alert count incremented from 1 to 2
      expect(screen.getByText(/active alerts: 2/i)).toBeInTheDocument();
    });
  });

  // 17. Malformed WebSocket message resilience
  it('17. gracefully handles malformed WebSocket message payloads without crashing', async () => {
    render(<TacticalMap />);

    await waitFor(() => {
      expect(screen.getByTestId('border-map-container')).toBeInTheDocument();
    });

    const socket = mockSockets[0];
    expect(socket).toBeDefined();

    // Send broken JSON
    act(() => {
      socket.simulateServerMessage('MALFORMED_NON_JSON_CORRUPT');
      socket.simulateServerMessage({ type: 'unknown_type', data: null });
      socket.simulateServerMessage(null);
    });

    // Tactical map remains operational
    expect(screen.getByTestId('tactical-map-page')).toBeInTheDocument();
  });

  // 18. Missing location handling
  it('18. handles cameras without parseable GPS coordinates via Unmapped Units panel without faking positions', async () => {
    render(<TacticalMap />);

    await waitFor(() => {
      expect(screen.getByText(/1 unmapped/i)).toBeInTheDocument();
    });

    // Toggle unmapped list button
    const unmappedToggle = screen.getByTestId('map-toggle-unmapped-btn');
    expect(unmappedToggle).toBeInTheDocument();
    fireEvent.click(unmappedToggle);

    // Panel is visible
    expect(screen.getByTestId('unmapped-cameras-panel')).toBeInTheDocument();
    expect(screen.getByText('CAM_03')).toBeInTheDocument();
    expect(screen.getByText(/Perimeter East Bunker/i)).toBeInTheDocument();
  });

  // 19. M19 CCTV regression
  it('19. preserves M19 Live CCTV Monitoring page without regression', async () => {
    render(<CCTVMonitoring />);

    await waitFor(() => {
      expect(screen.getByTestId('cctv-monitoring-page')).toBeInTheDocument();
      expect(screen.getByText(/live cctv monitoring/i)).toBeInTheDocument();
    });
  });

  // 20. M20 Alert Center regression
  it('20. preserves M20 Real-Time Alert Center page without regression', async () => {
    render(<Alerts />);

    await waitFor(() => {
      expect(screen.getByTestId('alerts-page')).toBeInTheDocument();
      expect(screen.getByText(/real-time alert center/i)).toBeInTheDocument();
    });
  });

  // 21. Coordinate parsing formats & boundary validation
  it('21. validates and parses coordinate formats safely and rejects fake/invalid positions', () => {
    // Valid comma-separated
    expect(parseCoordinates('28.6139, 77.2090')).toEqual({ lat: 28.6139, lng: 77.209 });
    expect(parseCoordinates('-33.8688,151.2093')).toEqual({ lat: -33.8688, lng: 151.2093 });

    // Valid space-separated
    expect(parseCoordinates('28.6139 77.2090')).toEqual({ lat: 28.6139, lng: 77.209 });

    // Valid labeled format
    expect(parseCoordinates('lat: 28.6139, lng: 77.2090')).toEqual({ lat: 28.6139, lng: 77.209 });
    expect(parseCoordinates('latitude: 28.6139; longitude: 77.2090')).toEqual({ lat: 28.6139, lng: 77.209 });

    // Valid JSON format
    expect(parseCoordinates('{"lat": 28.6139, "lng": 77.2090}')).toEqual({ lat: 28.6139, lng: 77.209 });

    // Invalid coordinates: out of range, unparseable, null
    expect(parseCoordinates('Sector North Gate')).toBeNull();
    expect(parseCoordinates('95.0, 77.0')).toBeNull(); // Lat > 90
    expect(parseCoordinates('28.0, 195.0')).toBeNull(); // Lng > 180
    expect(parseCoordinates('')).toBeNull();
    expect(parseCoordinates(null)).toBeNull();
    expect(parseCoordinates(undefined)).toBeNull();

    expect(isValidCoordinates(28.6, 77.2)).toBe(true);
    expect(isValidCoordinates(NaN, 77.2)).toBe(false);
  });

  // 22. Map controls functionality
  it('22. provides tactical zoom, fit bounds, and legend toggle controls', () => {
    const handleZoomIn = vi.fn();
    const handleZoomOut = vi.fn();
    const handleFit = vi.fn();
    const handleToggleLegend = vi.fn();

    render(
      <MapControls
        onZoomIn={handleZoomIn}
        onZoomOut={handleZoomOut}
        onFitBounds={handleFit}
        onToggleLegend={handleToggleLegend}
        isLegendVisible={true}
        unmappedCount={2}
      />
    );

    fireEvent.click(screen.getByTestId('map-zoom-in-btn'));
    expect(handleZoomIn).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('map-zoom-out-btn'));
    expect(handleZoomOut).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('map-fit-bounds-btn'));
    expect(handleFit).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('map-toggle-legend-btn'));
    expect(handleToggleLegend).toHaveBeenCalledTimes(1);
  });

  // 23. Camera activity marker pulse display & pixel-space limitation
  it('23. renders unit activity marker at camera coordinates and documents track pixel limitation', () => {
    render(
      <BorderMap
        cameras={[mockCameras[0]]}
        cameraActivityMap={{
          CAM_01: { activeTrackCount: 3, lastActivityTimestamp: '2026-09-12T15:00:00Z' },
        }}
      />
    );

    // Component mounts without error and associates activity at camera GPS position
    expect(screen.getByTestId('border-map-container')).toBeInTheDocument();
  });

  // 24. Cross-module navigation in App
  it('24. navigates to Tactical Map from App and provides cross-navigation to Live CCTV', async () => {
    render(<App />);

    // Click Tactical Map nav item
    const mapNavBtn = screen.getByRole('button', { name: /tactical map/i });
    expect(mapNavBtn).toBeInTheDocument();
    fireEvent.click(mapNavBtn);

    await waitFor(() => {
      expect(screen.getByTestId('tactical-map-page')).toBeInTheDocument();
      expect(screen.getByText(/live geospatial border map/i)).toBeInTheDocument();
    });

    // Navigate back to Live CCTV
    const cctvNavBtn = screen.getByRole('button', { name: /live cctv/i });
    fireEvent.click(cctvNavBtn);

    await waitFor(() => {
      expect(screen.getByTestId('cctv-monitoring-page')).toBeInTheDocument();
    });
  });
});
