import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { Alerts } from '@/pages/Alerts';
import { AlertSeverityBadge } from '@/components/alerts/AlertSeverityBadge';
import { CCTVMonitoring } from '@/pages/CCTVMonitoring';
import { App } from '@/App';
import type { Alert, Camera } from '@/types/api';

// Track mock WebSocket instances
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
    name: 'Perimeter Sector Alpha',
    source_type: 'RTSP',
    source_reference: 'rtsp://10.0.0.1/live',
    location: 'North Boundary',
    status: 'ONLINE',
    created_at: '2026-09-12T00:00:00Z',
    updated_at: '2026-09-12T00:00:00Z',
  },
];

const mockAlerts: Alert[] = [
  {
    id: 1,
    alert_id: 'ALT-00001',
    camera_id: 1,
    track_id: 17,
    event_id: 101,
    zone_id: 2,
    alert_type: 'FENCE_BREACH',
    severity: 'CRITICAL',
    status: 'ACTIVE',
    message: 'Unauthorized boundary intrusion detected',
    alert_timestamp: '2026-09-12T12:00:00Z',
    alert_metadata: { zone: 'Restricted Sector Alpha' },
    acknowledged_at: null,
    acknowledged_by: null,
    resolved_at: null,
    resolved_by: null,
    created_at: '2026-09-12T12:00:00Z',
    updated_at: '2026-09-12T12:00:00Z',
  },
  {
    id: 2,
    alert_id: 'ALT-00002',
    camera_id: 1,
    track_id: 23,
    event_id: 102,
    zone_id: null,
    alert_type: 'LOITERING',
    severity: 'MEDIUM',
    status: 'ACKNOWLEDGED',
    message: 'Individual loitering near boundary outpost',
    alert_timestamp: '2026-09-12T11:45:00Z',
    alert_metadata: { duration_seconds: 45 },
    acknowledged_at: '2026-09-12T11:50:00Z',
    acknowledged_by: 'Operator (HQ-01)',
    resolved_at: null,
    resolved_by: null,
    created_at: '2026-09-12T11:45:00Z',
    updated_at: '2026-09-12T11:50:00Z',
  },
  {
    id: 3,
    alert_id: 'ALT-00003',
    camera_id: 1,
    track_id: 99,
    event_id: 103,
    zone_id: 1,
    alert_type: 'FENCE_BREACH',
    severity: 'HIGH',
    status: 'RESOLVED',
    message: 'Resolved fence breach after patrol inspection',
    alert_timestamp: '2026-09-12T10:30:00Z',
    alert_metadata: { patrol_dispatched: true },
    acknowledged_at: '2026-09-12T10:35:00Z',
    acknowledged_by: 'Officer Ray',
    resolved_at: '2026-09-12T11:00:00Z',
    resolved_by: 'Commander Vance',
    created_at: '2026-09-12T10:30:00Z',
    updated_at: '2026-09-12T11:00:00Z',
  },
];

describe('M20 Real-Time Alert Panel + Acknowledgement', () => {
  let originalWebSocket: typeof WebSocket;
  let originalFetch: typeof fetch;

  beforeEach(() => {
    mockSockets = [];
    originalWebSocket = global.WebSocket;
    originalFetch = global.fetch;
    global.WebSocket = MockWebSocket as unknown as typeof WebSocket;

    global.fetch = vi.fn().mockImplementation(async (url: string | URL, options?: RequestInit) => {
      const urlStr = url.toString();

      // GET /api/v1/cameras
      if (urlStr.includes('/cameras')) {
        return {
          ok: true,
          json: async () => ({
            items: mockCameras,
            total: mockCameras.length,
            page: 1,
            page_size: 50,
            total_pages: 1,
          }),
        };
      }

      // PATCH /api/v1/alerts/{alert_id}
      if (options?.method === 'PATCH' && urlStr.includes('/alerts/')) {
        const body = JSON.parse(options.body as string);
        const alertId = urlStr.split('/alerts/')[1];
        const target = mockAlerts.find((a) => a.alert_id === alertId) || mockAlerts[0];

        return {
          ok: true,
          json: async () => ({
            ...target,
            status: body.status || 'ACKNOWLEDGED',
            acknowledged_by: body.acknowledged_by || 'Operator',
            acknowledged_at: new Date().toISOString(),
          }),
        };
      }

      // GET /api/v1/alerts
      if (urlStr.includes('/alerts')) {
        return {
          ok: true,
          json: async () => ({
            items: mockAlerts,
            total: mockAlerts.length,
            page: 1,
            page_size: 50,
            total_pages: 1,
          }),
        };
      }

      return {
        ok: true,
        json: async () => ({ items: [], total: 0 }),
      };
    });
  });

  afterEach(() => {
    global.WebSocket = originalWebSocket;
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  // 1. Alerts page renders
  it('1. renders Real-Time Alert Center page structure and header', async () => {
    render(<Alerts />);
    expect(screen.getByTestId('alerts-page')).toBeInTheDocument();
    expect(screen.getByText(/Real-Time Alert Center/i)).toBeInTheDocument();
    expect(screen.getByText('M20')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('alert-panel')).toBeInTheDocument();
    });
  });

  // 2. REST alert loading state
  it('2. displays loading state while fetching initial REST alerts', async () => {
    // Delay fetch response to inspect loading indicator
    global.fetch = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(() => {
            resolve({
              ok: true,
              json: async () => ({ items: mockAlerts, total: mockAlerts.length }),
            });
          }, 50);
        })
    );

    render(<Alerts />);
    expect(screen.getByText(/loading security alerts/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.queryByText(/loading security alerts/i)).not.toBeInTheDocument();
    });
  });

  // 3. Alerts rendered from API
  it('3. renders alerts loaded from the REST API', async () => {
    render(<Alerts />);
    await waitFor(() => {
      expect(screen.getByTestId('alert-card-ALT-00001')).toBeInTheDocument();
      expect(screen.getByTestId('alert-card-ALT-00002')).toBeInTheDocument();
      expect(screen.getByTestId('alert-card-ALT-00003')).toBeInTheDocument();
    });
    expect(screen.getByText('Unauthorized boundary intrusion detected')).toBeInTheDocument();
    expect(screen.getByText('Individual loitering near boundary outpost')).toBeInTheDocument();
  });

  // 4. Empty state
  it('4. displays empty state when REST returns no alerts', async () => {
    global.fetch = vi.fn().mockImplementation(async (url: string | URL) => {
      if (url.toString().includes('/cameras')) {
        return { ok: true, json: async () => ({ items: mockCameras, total: 1 }) };
      }
      return { ok: true, json: async () => ({ items: [], total: 0 }) };
    });

    render(<Alerts />);
    await waitFor(() => {
      expect(screen.getByText(/No Active Alerts/i)).toBeInTheDocument();
      expect(screen.getByText(/Perimeter perimeter sensors report zero security incidents/i)).toBeInTheDocument();
    });
  });

  // 5. REST failure state
  it('5. renders error state with retry action when REST alert request fails', async () => {
    global.fetch = vi.fn().mockImplementation(async (url: string | URL) => {
      if (url.toString().includes('/cameras')) {
        return { ok: true, json: async () => ({ items: mockCameras, total: 1 }) };
      }
      return {
        ok: false,
        status: 503,
        json: async () => ({ detail: 'Database cluster connection failed' }),
      };
    });

    render(<Alerts />);
    await waitFor(() => {
      expect(screen.getByText(/Alert Service Disconnected/i)).toBeInTheDocument();
      expect(screen.getByText('Database cluster connection failed')).toBeInTheDocument();
    });

    const retryBtn = screen.getByRole('button', { name: /Retry Alert Sync/i });
    expect(retryBtn).toBeInTheDocument();
  });

  // 6. WebSocket alert insertion
  it('6. receives real-time alert from M17 WebSocket and inserts into alert list', async () => {
    render(<Alerts />);
    await waitFor(() => {
      expect(screen.getByTestId('alert-card-ALT-00001')).toBeInTheDocument();
    });

    const ws = mockSockets[0];
    expect(ws).toBeDefined();

    // Simulate incoming real-time alert
    act(() => {
      ws.simulateServerMessage({
        type: 'alert',
        timestamp: '2026-09-12T12:05:00Z',
        camera_id: 'CAM_01',
        data: {
          alert_id: 'ALT-99999',
          camera_id: 'CAM_01',
          track_id: 88,
          alert_type: 'FENCE_BREACH',
          severity: 'CRITICAL',
          status: 'ACTIVE',
          message: 'Real-time live fence breach received over WebSocket',
          timestamp: '2026-09-12T12:05:00Z',
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByTestId('alert-card-ALT-99999')).toBeInTheDocument();
      expect(screen.getByText('Real-time live fence breach received over WebSocket')).toBeInTheDocument();
    });
  });

  // 7. Duplicate alert prevention
  it('7. deduplicates alerts using alert_id without duplicating cards in UI', async () => {
    render(<Alerts />);
    await waitFor(() => {
      expect(screen.getByTestId('alert-card-ALT-00001')).toBeInTheDocument();
    });

    const ws = mockSockets[0];

    // Simulate re-broadcasting an existing alert ALT-00001
    act(() => {
      ws.simulateServerMessage({
        type: 'alert',
        timestamp: '2026-09-12T12:10:00Z',
        camera_id: 'CAM_01',
        data: {
          alert_id: 'ALT-00001',
          camera_id: 'CAM_01',
          track_id: 17,
          alert_type: 'FENCE_BREACH',
          severity: 'CRITICAL',
          status: 'ACTIVE',
          message: 'Updated description for same alert ID',
          timestamp: '2026-09-12T12:10:00Z',
        },
      });
    });

    await waitFor(() => {
      const cards = screen.getAllByTestId('alert-card-ALT-00001');
      expect(cards).toHaveLength(1);
      expect(screen.getByText('Updated description for same alert ID')).toBeInTheDocument();
    });
  });

  // 8. New alert indicator/count
  it('8. displays NEW indicator on fresh alerts and updates ACTIVE count', async () => {
    render(<Alerts />);
    await waitFor(() => {
      expect(screen.getByTestId('active-alerts-count')).toHaveTextContent('ACTIVE: 1');
    });

    const ws = mockSockets[0];

    // Push new active alert
    act(() => {
      ws.simulateServerMessage({
        type: 'alert',
        timestamp: '2026-09-12T12:15:00Z',
        camera_id: 'CAM_01',
        data: {
          alert_id: 'ALT-NEW-1',
          camera_id: 'CAM_01',
          track_id: 55,
          alert_type: 'LOITERING',
          severity: 'HIGH',
          status: 'ACTIVE',
          message: 'Loiterer detected at North sector',
          timestamp: '2026-09-12T12:15:00Z',
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByTestId('active-alerts-count')).toHaveTextContent('ACTIVE: 2');
      expect(screen.getByTestId('new-alert-badge')).toBeInTheDocument();
    });
  });

  // 9. Severity rendering
  it('9. renders severity badges with distinct non-color accessible indicators', () => {
    const { rerender } = render(<AlertSeverityBadge severity="CRITICAL" />);
    expect(screen.getByTestId('severity-badge-critical')).toHaveTextContent('CRITICAL');

    rerender(<AlertSeverityBadge severity="HIGH" />);
    expect(screen.getByTestId('severity-badge-high')).toHaveTextContent('HIGH');

    rerender(<AlertSeverityBadge severity="MEDIUM" />);
    expect(screen.getByTestId('severity-badge-medium')).toHaveTextContent('MEDIUM');

    rerender(<AlertSeverityBadge severity="LOW" />);
    expect(screen.getByTestId('severity-badge-low')).toHaveTextContent('LOW');
  });

  // 10. Status rendering
  it('10. renders status badges distinguishing ACTIVE, ACKNOWLEDGED, and RESOLVED', async () => {
    render(<Alerts />);
    await waitFor(() => {
      expect(screen.getByTestId('alert-card-ALT-00001')).toBeInTheDocument();
    });

    const activeCard = screen.getByTestId('alert-card-ALT-00001');
    expect(activeCard).toHaveTextContent('ACKNOWLEDGE');

    const ackCard = screen.getByTestId('alert-card-ALT-00002');
    expect(ackCard).toHaveTextContent('ACKNOWLEDGED');

    const resolvedCard = screen.getByTestId('alert-card-ALT-00003');
    expect(resolvedCard).toHaveTextContent('RESOLVED');
  });

  // 11. Alert detail opening
  it('11. opens alert detail drawer with complete telemetry upon card click', async () => {
    render(<Alerts />);
    await waitFor(() => {
      expect(screen.getByTestId('alert-card-ALT-00001')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('alert-card-ALT-00001'));

    await waitFor(() => {
      expect(screen.getByTestId('alert-detail-modal')).toBeInTheDocument();
      expect(screen.getByText('Incident Message')).toBeInTheDocument();
      expect(screen.getByTestId('alert-detail-modal')).toHaveTextContent('Restricted Sector Alpha');
      expect(screen.getByText('Track Target')).toBeInTheDocument();
    });

    // Close modal
    fireEvent.click(screen.getByTestId('alert-detail-close-btn'));
    await waitFor(() => {
      expect(screen.queryByTestId('alert-detail-modal')).not.toBeInTheDocument();
    });
  });

  // 12. Acknowledge button
  it('12. renders acknowledge button only for unacknowledged alerts', async () => {
    render(<Alerts />);
    await waitFor(() => {
      expect(screen.getByTestId('acknowledge-btn-ALT-00001')).toBeInTheDocument();
      expect(screen.queryByTestId('acknowledge-btn-ALT-00002')).not.toBeInTheDocument();
      expect(screen.queryByTestId('acknowledge-btn-ALT-00003')).not.toBeInTheDocument();
    });
  });

  // 13. PATCH acknowledgement request
  it('13. sends PATCH request with { status: "ACKNOWLEDGED", acknowledged_by: ... }', async () => {
    render(<Alerts />);
    await waitFor(() => {
      expect(screen.getByTestId('acknowledge-btn-ALT-00001')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('acknowledge-btn-ALT-00001'));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/alerts/ALT-00001'),
        expect.objectContaining({
          method: 'PATCH',
          body: expect.stringContaining('"status":"ACKNOWLEDGED"'),
        })
      );
    });
  });

  // 14. Successful acknowledgement updates UI
  it('14. updates UI to ACKNOWLEDGED state and decrements active count', async () => {
    render(<Alerts />);
    await waitFor(() => {
      expect(screen.getByTestId('active-alerts-count')).toHaveTextContent('ACTIVE: 1');
    });

    fireEvent.click(screen.getByTestId('acknowledge-btn-ALT-00001'));

    await waitFor(() => {
      expect(screen.getByTestId('alert-card-ALT-00001')).toHaveTextContent('ACKNOWLEDGED');
      expect(screen.queryByTestId('acknowledge-btn-ALT-00001')).not.toBeInTheDocument();
      expect(screen.getByTestId('active-alerts-count')).toHaveTextContent('ACTIVE: 0');
    });
  });

  // 15. Failed acknowledgement preserves correct state
  it('15. handles acknowledgement failure gracefully without losing alert or corrupting state', async () => {
    global.fetch = vi.fn().mockImplementation(async (url: string | URL, options?: RequestInit) => {
      if (options?.method === 'PATCH') {
        return {
          ok: false,
          status: 500,
          json: async () => ({ detail: 'Database commit error' }),
        };
      }
      if (url.toString().includes('/cameras')) {
        return { ok: true, json: async () => ({ items: mockCameras, total: 1 }) };
      }
      return { ok: true, json: async () => ({ items: mockAlerts, total: mockAlerts.length }) };
    });

    render(<Alerts />);
    await waitFor(() => {
      expect(screen.getByTestId('acknowledge-btn-ALT-00001')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('acknowledge-btn-ALT-00001'));

    await waitFor(() => {
      // Still unacknowledged
      expect(screen.getByTestId('acknowledge-btn-ALT-00001')).toBeInTheDocument();
      // Error banner shown
      expect(screen.getByTestId('ack-error-banner')).toHaveTextContent('Database commit error');
    });
  });

  // 16. Filtering
  it('16. performs client-side filtering by severity, status, and alert type', async () => {
    render(<Alerts />);
    await waitFor(() => {
      expect(screen.getByTestId('alert-card-ALT-00001')).toBeInTheDocument();
      expect(screen.getByTestId('alert-card-ALT-00002')).toBeInTheDocument();
      expect(screen.getByTestId('alert-card-ALT-00003')).toBeInTheDocument();
    });

    // Filter by status: ACTIVE
    const statusSelect = screen.getByTestId('filter-status-select');
    fireEvent.change(statusSelect, { target: { value: 'ACTIVE' } });

    await waitFor(() => {
      expect(screen.getByTestId('alert-card-ALT-00001')).toBeInTheDocument();
      expect(screen.queryByTestId('alert-card-ALT-00002')).not.toBeInTheDocument();
      expect(screen.queryByTestId('alert-card-ALT-00003')).not.toBeInTheDocument();
    });

    // Reset filters
    fireEvent.click(screen.getByTestId('filter-reset-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('alert-card-ALT-00002')).toBeInTheDocument();
    });

    // Filter by severity: CRITICAL
    const severitySelect = screen.getByTestId('filter-severity-select');
    fireEvent.change(severitySelect, { target: { value: 'CRITICAL' } });

    await waitFor(() => {
      expect(screen.getByTestId('alert-card-ALT-00001')).toBeInTheDocument();
      expect(screen.queryByTestId('alert-card-ALT-00002')).not.toBeInTheDocument();
    });
  });

  // 17. Sorting
  it('17. sorts alerts by newest, oldest, and highest severity priority', async () => {
    render(<Alerts />);
    await waitFor(() => {
      expect(screen.getByTestId('alert-card-ALT-00001')).toBeInTheDocument();
    });

    const sortSelect = screen.getByTestId('sort-select');

    // Sort by oldest
    fireEvent.change(sortSelect, { target: { value: 'oldest' } });
    await waitFor(() => {
      const cards = screen.getAllByTestId(/^alert-card-/);
      // ALT-00003 is oldest (10:30)
      expect(cards[0]).toHaveAttribute('data-testid', 'alert-card-ALT-00003');
    });

    // Sort by severity (CRITICAL first, then HIGH, then MEDIUM)
    fireEvent.change(sortSelect, { target: { value: 'severity' } });
    await waitFor(() => {
      const cards = screen.getAllByTestId(/^alert-card-/);
      expect(cards[0]).toHaveAttribute('data-testid', 'alert-card-ALT-00001'); // CRITICAL
      expect(cards[1]).toHaveAttribute('data-testid', 'alert-card-ALT-00003'); // HIGH
      expect(cards[2]).toHaveAttribute('data-testid', 'alert-card-ALT-00002'); // MEDIUM
    });
  });

  // 18. Malformed WebSocket alert does not crash UI
  it('18. safely discards malformed WebSocket alerts without crashing', async () => {
    render(<Alerts />);
    await waitFor(() => {
      expect(screen.getByTestId('alert-card-ALT-00001')).toBeInTheDocument();
    });

    const ws = mockSockets[0];

    act(() => {
      // Malformed: missing alert_id or null payload
      ws.simulateServerMessage({
        type: 'alert',
        timestamp: '2026-09-12T12:00:00Z',
        camera_id: 'CAM_01',
        data: null,
      });
      // Malformed: frame message should not disturb alert panel
      ws.simulateServerMessage({
        type: 'frame',
        timestamp: '2026-09-12T12:00:00Z',
        camera_id: 'CAM_01',
        data: { encoded_data: 'base64...' },
      });
    });

    // Component remains stable
    expect(screen.getByTestId('alerts-page')).toBeInTheDocument();
    expect(screen.getByTestId('alert-card-ALT-00001')).toBeInTheDocument();
  });

  // 19. WebSocket reconnect/disconnected state
  it('19. reflects WebSocket disconnected and reconnecting states accurately', async () => {
    render(<Alerts />);
    await waitFor(() => {
      expect(screen.getByTestId('ws-status-badge')).toHaveTextContent(/WS STREAM LIVE/i);
    });

    const ws = mockSockets[0];
    act(() => {
      ws.close(1006, 'Abnormal closure');
    });

    await waitFor(() => {
      expect(screen.getByTestId('ws-status-badge')).toHaveTextContent(/WS RECONNECTING|WS CLOSED|WS DISCONNECTED/i);
    });
  });

  // 20. Component cleanup
  it('20. cleanly disconnects WebSocket and removes event listeners on unmount', async () => {
    const { unmount } = render(<Alerts />);
    await waitFor(() => {
      expect(mockSockets.length).toBeGreaterThan(0);
    });

    const ws = mockSockets[0];
    unmount();

    expect(ws.readyState).toBe(MockWebSocket.CLOSED);
  });

  // 21. Existing M19 CCTV page still renders
  it('21. preserves M19 Live CCTV Monitoring page functionality without regression', async () => {
    render(<CCTVMonitoring />);
    expect(screen.getByTestId('cctv-monitoring-page')).toBeInTheDocument();
    expect(screen.getByText(/Live CCTV Monitoring/i)).toBeInTheDocument();
    expect(screen.getByText('M19')).toBeInTheDocument();
  });

  // 22. App navigation between CCTV and Alerts works
  it('22. routes seamlessly between Live CCTV and Alert Center in the App Shell', async () => {
    render(<App />);

    // Default is CCTV
    expect(screen.getByTestId('cctv-monitoring-page')).toBeInTheDocument();

    // Click Alert Center in Shell navigation
    const alertNavBtn = screen.getByRole('button', { name: /Alert Center/i });
    expect(alertNavBtn).not.toBeDisabled();
    fireEvent.click(alertNavBtn);

    await waitFor(() => {
      expect(screen.getByTestId('alerts-page')).toBeInTheDocument();
    });

    // Click back to Live CCTV
    const cctvNavBtn = screen.getByRole('button', { name: /Live CCTV/i });
    fireEvent.click(cctvNavBtn);

    await waitFor(() => {
      expect(screen.getByTestId('cctv-monitoring-page')).toBeInTheDocument();
    });
  });
});
