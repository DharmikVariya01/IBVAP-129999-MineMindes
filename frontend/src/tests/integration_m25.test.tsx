import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { App } from '@/App';
import type { Camera, Alert, Track, Event as ApiEvent } from '@/types/api';

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

const mockCameras: Camera[] = [
  {
    id: 1,
    camera_id: 'CAM_01',
    name: 'North Gate Perimeter',
    source_type: 'RTSP',
    source_reference: 'rtsp://10.0.0.1/live',
    location: '28.6139, 77.2090',
    status: 'ONLINE',
    created_at: '2026-09-12T00:00:00Z',
    updated_at: '2026-09-12T00:00:00Z',
  },
  {
    id: 2,
    camera_id: 'CAM_02',
    name: 'East Fence Outpost',
    source_type: 'RTSP',
    source_reference: 'rtsp://10.0.0.2/live',
    location: '28.6145, 77.2105',
    status: 'ONLINE',
    created_at: '2026-09-12T00:00:00Z',
    updated_at: '2026-09-12T00:00:00Z',
  },
];

const mockAlerts: Alert[] = [
  {
    id: 101,
    alert_id: 'ALT_001',
    alert_type: 'FENCE_BREACH',
    severity: 'CRITICAL',
    status: 'ACTIVE',
    camera_id: 1,
    track_id: 105,
    event_id: 501,
    zone_id: 1,
    message: 'Fence breach detected at North Gate Perimeter',
    alert_timestamp: '2026-09-12T10:00:00Z',
    alert_metadata: { confidence: 0.95, camera_code: 'CAM_01' },
    acknowledged_at: null,
    acknowledged_by: null,
    resolved_at: null,
    resolved_by: null,
    created_at: '2026-09-12T10:00:00Z',
    updated_at: '2026-09-12T10:00:00Z',
  },
];

const mockTrack: Track = {
  id: 105,
  track_id: 105,
  camera_id: 1,
  class_id: 0,
  class_name: 'person',
  first_seen: '2026-09-12T09:59:00Z',
  last_seen: '2026-09-12T10:01:00Z',
  frame_count: 60,
  last_confidence: 0.94,
  bbox_x1: 100,
  bbox_y1: 150,
  bbox_x2: 200,
  bbox_y2: 350,
  last_center_x: 150,
  last_center_y: 250,
  status: 'ACTIVE',
  observation_metadata: {},
  created_at: '2026-09-12T09:59:00Z',
  updated_at: '2026-09-12T10:01:00Z',
};

const mockEvents: ApiEvent[] = [
  {
    id: 501,
    event_id: '501',
    event_type: 'FENCE_BREACH',
    camera_id: 1,
    track_id: 105,
    zone_id: 1,
    frame_id: 120,
    timestamp: '2026-09-12T10:00:00Z',
    details: { description: 'Track crossed fence line' },
    created_at: '2026-09-12T10:00:00Z',
  },
];

describe('M25 Frontend End-to-End System Integration', () => {
  let originalWebSocket: typeof WebSocket;
  let originalFetch: typeof fetch;

  beforeEach(() => {
    mockSockets = [];
    originalWebSocket = global.WebSocket;
    originalFetch = global.fetch;

    global.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    window.WebSocket = MockWebSocket as unknown as typeof WebSocket;

    global.fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/v1/cameras')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ items: mockCameras, total: mockCameras.length, page: 1, page_size: 50, total_pages: 1 }),
        } as unknown as Response;
      }
      if (url.includes('/api/v1/alerts')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ items: mockAlerts, total: mockAlerts.length, page: 1, page_size: 50, total_pages: 1 }),
        } as unknown as Response;
      }
      if (url.includes('/api/v1/tracks/105')) {
        return {
          ok: true,
          status: 200,
          json: async () => mockTrack,
        } as unknown as Response;
      }
      if (url.includes('/api/v1/events/105')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ items: mockEvents, total: 1 }),
        } as unknown as Response;
      }
      if (url.includes('/api/v1/stats')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            total_cameras: 2,
            active_cameras: 2,
            total_alerts_24h: 1,
            critical_alerts_24h: 1,
            active_tracks: 1,
            alerts_by_type: { FENCE_BREACH: 1 },
            alerts_by_severity: { CRITICAL: 1 },
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
    global.WebSocket = originalWebSocket;
    window.WebSocket = originalWebSocket;
    global.fetch = originalFetch;
    mockSockets.forEach(s => s.close());
    mockSockets = [];
    vi.restoreAllMocks();
  });

  it('Navigation: Alert -> Live CCTV (camera select) and Alert -> Timeline (track select)', async () => {
    render(<App />);

    // 1. Navigate to Alerts page
    const mainNav = screen.getByRole('navigation', { name: /main navigation/i });
    fireEvent.click(within(mainNav).getByRole('button', { name: /alert center/i }));

    await waitFor(() => {
      expect(screen.getByTestId('alerts-page')).toBeInTheDocument();
      expect(screen.getByTestId('alert-card-ALT_001')).toBeInTheDocument();
    });

    // 2. Click Alert Card to view Detail
    fireEvent.click(screen.getByTestId('alert-card-ALT_001'));

    await waitFor(() => {
      expect(screen.getByTestId('alert-detail-modal')).toBeInTheDocument();
      expect(screen.getByText('Incident Message')).toBeInTheDocument();
    });

    // 3. Click Camera "Live Feed" button in Alert Detail -> navigates to CCTV with CAM_01
    const liveFeedBtn = screen.getByTestId('detail-view-camera-btn');
    fireEvent.click(liveFeedBtn);

    await waitFor(() => {
      expect(screen.getByTestId('cctv-monitoring-page')).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: /live cctv monitoring/i })).toBeInTheDocument();
    });

    // 4. Return to Alerts -> Select Track to navigate to Timeline
    const navBar = screen.getByRole('navigation', { name: /main navigation/i });
    fireEvent.click(within(navBar).getByRole('button', { name: /alert center/i }));
    await waitFor(() => {
      expect(screen.getByTestId('alert-card-ALT_001')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('alert-card-ALT_001'));

    await waitFor(() => {
      expect(screen.getByTestId('detail-view-timeline-btn')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('detail-view-timeline-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('event-timeline-page')).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: /event timeline/i })).toBeInTheDocument();
    });
  });

  it('Navigation: Tactical Map -> Live CCTV and Analytics navigation', async () => {
    render(<App />);

    // 1. Navigate to Tactical Map
    const mainNav = screen.getByRole('navigation', { name: /main navigation/i });
    fireEvent.click(within(mainNav).getByRole('button', { name: /tactical map/i }));

    await waitFor(() => {
      expect(screen.getByTestId('tactical-map-page')).toBeInTheDocument();
      expect(screen.getByText(/live geospatial border map/i)).toBeInTheDocument();
    });

    // 2. Navigate to Analytics
    fireEvent.click(within(mainNav).getByRole('button', { name: /analytics/i }));

    await waitFor(() => {
      expect(screen.getByTestId('analytics-page')).toBeInTheDocument();
    });

    // Navigate back to CCTV
    fireEvent.click(within(mainNav).getByRole('button', { name: /live cctv/i }));

    await waitFor(() => {
      expect(screen.getByTestId('cctv-monitoring-page')).toBeInTheDocument();
    });
  });

  it('Single Camera Stream: exactly one active WebSocket subscription on selection, cleaned up on tab switch', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('cctv-monitoring-page')).toBeInTheDocument();
      expect(screen.getByRole('combobox', { name: /select camera feed/i })).toBeInTheDocument();
    });

    // Select camera CAM_01
    const select = screen.getByRole('combobox', { name: /select camera feed/i });
    fireEvent.change(select, { target: { value: 'CAM_01' } });

    // Verify WebSocket opened for CAM_01
    await waitFor(() => {
      expect(mockSockets.length).toBeGreaterThanOrEqual(1);
      const activeSockets = mockSockets.filter(s => s.readyState === MockWebSocket.OPEN || s.readyState === MockWebSocket.CONNECTING);
      expect(activeSockets.length).toBe(1);
      expect(activeSockets[0].url).toContain('/ws/CAM_01');
    });

    // Switch to Tactical Map tab via main nav
    const mainNav = screen.getByRole('navigation', { name: /main navigation/i });
    fireEvent.click(within(mainNav).getByRole('button', { name: /tactical map/i }));

    await waitFor(() => {
      expect(screen.getByTestId('tactical-map-page')).toBeInTheDocument();
      // CCTV socket should have closed
      const openSockets = mockSockets.filter(s => s.readyState === MockWebSocket.OPEN);
      expect(openSockets.length).toBe(0);
    });

    // Return to Live CCTV
    fireEvent.click(within(mainNav).getByRole('button', { name: /live cctv/i }));

    await waitFor(() => {
      expect(screen.getByTestId('cctv-monitoring-page')).toBeInTheDocument();
    });
  });
});
