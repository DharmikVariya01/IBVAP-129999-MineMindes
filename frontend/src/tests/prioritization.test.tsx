import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import {
  calculateCameraPriority,
  sortCamerasByPriority,
  matchesAlertToCamera,
} from '@/utils/prioritization';
import { CameraPriorityBadge } from '@/components/prioritization/CameraPriorityBadge';
import { PriorityLegend } from '@/components/prioritization/PriorityLegend';
import { CameraPriorityCard } from '@/components/prioritization/CameraPriorityCard';
import { CameraPriorityList } from '@/components/prioritization/CameraPriorityList';
import { CameraSelector } from '@/components/cctv/CameraSelector';
import { CCTVMonitoring } from '@/pages/CCTVMonitoring';
import type { Camera, Alert } from '@/types/api';
import type { PrioritizedCamera, PrioritySummaryCounts } from '@/types/prioritization';

// Mock WebSocket implementation for real-time testing
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

// Canonical real test cameras
const testCameras: Camera[] = [
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
  {
    id: 3,
    camera_id: 'CAM_03',
    name: 'South Watchtower',
    source_type: 'RTSP',
    source_reference: 'rtsp://10.0.0.3/live',
    location: null, // Unmapped
    status: 'ONLINE',
    created_at: '2026-09-12T00:00:00Z',
    updated_at: '2026-09-12T00:00:00Z',
  },
  {
    id: 4,
    camera_id: 'CAM_04',
    name: 'West Border Ridge',
    source_type: 'RTSP',
    source_reference: 'rtsp://10.0.0.4/live',
    location: '28.6120, 77.2080',
    status: 'OFFLINE',
    created_at: '2026-09-12T00:00:00Z',
    updated_at: '2026-09-12T00:00:00Z',
  },
];

// Helper to create test alerts
function createAlert(overrides: Partial<Alert>): Alert {
  return {
    id: 101,
    alert_id: 'ALT-101',
    camera_id: 1,
    track_id: 10,
    event_id: 201,
    zone_id: 1,
    alert_type: 'FENCE_BREACH',
    severity: 'MEDIUM',
    status: 'ACTIVE',
    message: 'Motion detected along perimeter',
    alert_timestamp: '2026-09-12T12:00:00Z',
    alert_metadata: {},
    acknowledged_at: null,
    acknowledged_by: null,
    resolved_at: null,
    resolved_by: null,
    created_at: '2026-09-12T12:00:00Z',
    updated_at: '2026-09-12T12:00:00Z',
    ...overrides,
  };
}

describe('IBVAP M24 — Camera Prioritization & Tactical Alert Sorting', () => {
  let originalWebSocket: typeof WebSocket;
  let originalFetch: typeof fetch;

  beforeEach(() => {
    mockSockets = [];
    originalWebSocket = global.WebSocket;
    global.WebSocket = MockWebSocket as unknown as typeof WebSocket;

    originalFetch = global.fetch;
    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      const urlStr = String(url);

      if (urlStr.includes('/api/v1/cameras')) {
        return {
          ok: true,
          json: async () => ({
            items: testCameras,
            total: testCameras.length,
            page: 1,
            page_size: 100,
            total_pages: 1,
          }),
        };
      }

      if (urlStr.includes('/api/v1/alerts')) {
        return {
          ok: true,
          json: async () => ({
            items: [],
            total: 0,
            page: 1,
            page_size: 100,
            total_pages: 1,
          }),
        };
      }

      return {
        ok: true,
        json: async () => ({}),
      };
    });
  });

  afterEach(() => {
    global.WebSocket = originalWebSocket;
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  // Test 1: Cameras are rendered
  it('1. renders cameras in tactical prioritization list', async () => {
    const alerts: Alert[] = [];
    const prioritized = sortCamerasByPriority(testCameras, alerts);
    const summary: PrioritySummaryCounts = {
      criticalCount: 0,
      highCount: 0,
      mediumCount: 0,
      lowCount: 0,
      clearCount: 3,
      offlineCount: 1,
      totalActiveAlerts: 0,
      totalCameras: 4,
    };

    render(
      <CameraPriorityList
        prioritizedCameras={prioritized}
        summaryCounts={summary}
        selectedCameraId="CAM_01"
        loading={false}
        error={null}
        sortByPriority={true}
        onToggleSortByPriority={vi.fn()}
        onSelectCamera={vi.fn()}
        onRefresh={vi.fn()}
      />
    );

    expect(screen.getByText(/Tactical Camera Prioritization/i)).toBeInTheDocument();
    expect(screen.getByText(/North Gate Perimeter/i)).toBeInTheDocument();
    expect(screen.getByText(/East Fence Outpost/i)).toBeInTheDocument();
    expect(screen.getByText(/South Watchtower/i)).toBeInTheDocument();
    expect(screen.getByText(/West Border Ridge/i)).toBeInTheDocument();
  });

  // Test 2: Critical alert camera ranks above lower severity
  it('2. ranks camera with CRITICAL active alert above lower severity cameras', () => {
    const alerts: Alert[] = [
      createAlert({ alert_id: 'ALT-1', camera_id: 1, severity: 'CRITICAL', status: 'ACTIVE' }),
      createAlert({ alert_id: 'ALT-2', camera_id: 2, severity: 'HIGH', status: 'ACTIVE' }),
      createAlert({ alert_id: 'ALT-3', camera_id: 3, severity: 'MEDIUM', status: 'ACTIVE' }),
    ];

    const sorted = sortCamerasByPriority(testCameras, alerts);

    expect(sorted[0].camera.camera_id).toBe('CAM_01');
    expect(sorted[0].priorityLevel).toBe('CRITICAL');
    expect(sorted[0].rank).toBe(1);
    expect(sorted[1].camera.camera_id).toBe('CAM_02');
    expect(sorted[1].priorityLevel).toBe('HIGH');
  });

  // Test 3: High ranks above medium
  it('3. ranks HIGH alert camera above MEDIUM alert camera', () => {
    const alerts: Alert[] = [
      createAlert({ alert_id: 'ALT-1', camera_id: 2, severity: 'HIGH', status: 'ACTIVE' }),
      createAlert({ alert_id: 'ALT-2', camera_id: 1, severity: 'MEDIUM', status: 'ACTIVE' }),
    ];

    const sorted = sortCamerasByPriority(testCameras, alerts);

    expect(sorted[0].camera.camera_id).toBe('CAM_02');
    expect(sorted[0].priorityLevel).toBe('HIGH');
    expect(sorted[1].camera.camera_id).toBe('CAM_01');
    expect(sorted[1].priorityLevel).toBe('MEDIUM');
  });

  // Test 4: Medium ranks above low
  it('4. ranks MEDIUM alert camera above LOW alert camera', () => {
    const alerts: Alert[] = [
      createAlert({ alert_id: 'ALT-1', camera_id: 3, severity: 'MEDIUM', status: 'ACTIVE' }),
      createAlert({ alert_id: 'ALT-2', camera_id: 2, severity: 'LOW', status: 'ACTIVE' }),
    ];

    const sorted = sortCamerasByPriority(testCameras, alerts);

    expect(sorted[0].camera.camera_id).toBe('CAM_03');
    expect(sorted[0].priorityLevel).toBe('MEDIUM');
    expect(sorted[1].camera.camera_id).toBe('CAM_02');
    expect(sorted[1].priorityLevel).toBe('LOW');
  });

  // Test 5: Active-alert camera ranks above clear camera
  it('5. ranks active-alert camera above clear camera', () => {
    const alerts: Alert[] = [
      createAlert({ alert_id: 'ALT-1', camera_id: 2, severity: 'LOW', status: 'ACTIVE' }),
    ];

    const sorted = sortCamerasByPriority(testCameras, alerts);

    // CAM_02 has a LOW alert; CAM_01 and CAM_03 are CLEAR; CAM_04 is OFFLINE
    expect(sorted[0].camera.camera_id).toBe('CAM_02');
    expect(sorted[0].priorityLevel).toBe('LOW');
    expect(sorted[1].priorityLevel).toBe('CLEAR');
    expect(sorted[2].priorityLevel).toBe('CLEAR');
  });

  // Test 6: Multiple active alerts affect ordering (more alerts = higher priority within same severity)
  it('6. orders cameras with same severity by number of active alerts (more alerts = higher priority)', () => {
    const alerts: Alert[] = [
      createAlert({ alert_id: 'ALT-1', camera_id: 1, severity: 'HIGH', status: 'ACTIVE' }),
      createAlert({ alert_id: 'ALT-2', camera_id: 2, severity: 'HIGH', status: 'ACTIVE' }),
      createAlert({ alert_id: 'ALT-3', camera_id: 2, severity: 'HIGH', status: 'ACTIVE' }),
    ];

    // CAM_02 has 2 HIGH alerts, CAM_01 has 1 HIGH alert
    const sorted = sortCamerasByPriority(testCameras, alerts);

    expect(sorted[0].camera.camera_id).toBe('CAM_02');
    expect(sorted[0].activeAlertCount).toBe(2);
    expect(sorted[0].priorityLevel).toBe('HIGH');

    expect(sorted[1].camera.camera_id).toBe('CAM_01');
    expect(sorted[1].activeAlertCount).toBe(1);
    expect(sorted[1].priorityLevel).toBe('HIGH');
  });

  // Test 7: Clear cameras remain below alerted cameras
  it('7. ensures clear cameras remain strictly below alerted cameras', () => {
    const alerts: Alert[] = [
      createAlert({ alert_id: 'ALT-1', camera_id: 3, severity: 'LOW', status: 'ACTIVE' }),
    ];

    const sorted = sortCamerasByPriority(testCameras, alerts);

    const alertedIdx = sorted.findIndex((c) => c.camera.camera_id === 'CAM_03');
    const clearIdx1 = sorted.findIndex((c) => c.camera.camera_id === 'CAM_01');
    const clearIdx2 = sorted.findIndex((c) => c.camera.camera_id === 'CAM_02');

    expect(alertedIdx).toBeLessThan(clearIdx1);
    expect(alertedIdx).toBeLessThan(clearIdx2);
  });

  // Test 8: Offline/error state is represented correctly
  it('8. correctly represents OFFLINE / ERROR state at the bottom and never presents as healthy', () => {
    // CAM_04 is OFFLINE, and even with a historical/active alert in DB, it remains classified as OFFLINE
    const alerts: Alert[] = [
      createAlert({ alert_id: 'ALT-HIST', camera_id: 4, severity: 'CRITICAL', status: 'ACTIVE' }),
    ];

    const prio = calculateCameraPriority(testCameras[3], alerts);
    expect(prio.priorityLevel).toBe('OFFLINE');
    expect(prio.isOfflineOrError).toBe(true);

    const sorted = sortCamerasByPriority(testCameras, alerts);
    const lastItem = sorted[sorted.length - 1];
    expect(lastItem.camera.camera_id).toBe('CAM_04');
    expect(lastItem.priorityLevel).toBe('OFFLINE');
  });

  // Test 9: New alert updates camera priority
  it('9. dynamically updates camera priority when new alert arrives via WebSocket', async () => {
    // Initial fetch returns CAM_01 as CLEAR
    (global.fetch as any).mockImplementation(async (url: string) => {
      const urlStr = String(url);
      if (urlStr.includes('/api/v1/cameras')) {
        return {
          ok: true,
          json: async () => ({ items: testCameras, total: 4, page: 1, page_size: 50, total_pages: 1 }),
        };
      }
      if (urlStr.includes('/api/v1/alerts')) {
        return {
          ok: true,
          json: async () => ({ items: [], total: 0, page: 1, page_size: 50, total_pages: 1 }),
        };
      }
      return { ok: true, json: async () => ({}) };
    });

    render(<CCTVMonitoring initialCameraId="CAM_01" />);

    // Wait for initial load
    await waitFor(() => {
      expect(screen.getByText(/No active security alerts/i)).toBeInTheDocument();
    });

    // Simulate incoming real-time M17 CRITICAL alert for CAM_02 via WebSocket
    await act(async () => {
      if (mockSockets.length > 0) {
        mockSockets[0].simulateServerMessage({
          type: 'alert',
          camera_id: 'CAM_02',
          data: {
            alert_id: 'ALT-REALTIME-999',
            camera_id: 'CAM_02',
            severity: 'CRITICAL',
            status: 'ACTIVE',
            alert_type: 'FENCE_BREACH',
            message: 'Critical boundary breach detected!',
            timestamp: new Date().toISOString(),
          },
        });
      }
    });

    // Verify CAM_02 promoted to CRITICAL in priority panel
    await waitFor(() => {
      const card = screen.getByTestId('priority-card-CAM_02');
      expect(card).toBeInTheDocument();
      expect(card).toHaveTextContent(/Critical boundary breach detected!/i);
      expect(card).toHaveTextContent(/CRITICAL/i);
      expect(card).toHaveTextContent(/#1/i);
    });
  });

  // Test 10: Acknowledgement/resolution updates priority correctly
  it('10. updates camera priority from active alert severity to CLEAR when alert is acknowledged', () => {
    const activeAlert = createAlert({ alert_id: 'ALT-1', camera_id: 1, severity: 'HIGH', status: 'ACTIVE' });
    const prioBefore = calculateCameraPriority(testCameras[0], [activeAlert]);
    expect(prioBefore.priorityLevel).toBe('HIGH');
    expect(prioBefore.activeAlertCount).toBe(1);

    // After operator acknowledges alert, its status becomes ACKNOWLEDGED
    const ackedAlert = { ...activeAlert, status: 'ACKNOWLEDGED' as const };
    const prioAfter = calculateCameraPriority(testCameras[0], [ackedAlert]);
    expect(prioAfter.priorityLevel).toBe('CLEAR');
    expect(prioAfter.activeAlertCount).toBe(0);
  });

  // Test 11: Clicking a camera selects/navigates to M19
  it('11. triggers camera selection when clicking a priority card or select button', () => {
    const onSelectCamera = vi.fn();
    const alerts: Alert[] = [
      createAlert({ alert_id: 'ALT-1', camera_id: 2, severity: 'HIGH', status: 'ACTIVE' }),
    ];
    const prioritized = sortCamerasByPriority(testCameras, alerts);

    render(
      <CameraPriorityCard
        item={prioritized[0]}
        isSelected={false}
        onSelectCamera={onSelectCamera}
      />
    );

    const card = screen.getByTestId('priority-card-CAM_02');
    fireEvent.click(card);

    expect(onSelectCamera).toHaveBeenCalledWith('CAM_02');
  });

  // Test 12: No fake camera/alert data is introduced
  it('12. strictly matches real alerts to real cameras without inventing risk scores or fake IDs', () => {
    const realCamera = testCameras[0];
    const matchingAlert = createAlert({ camera_id: 1 });
    const nonMatchingAlert = createAlert({ camera_id: 999, alert_metadata: { camera_id: 'CAM_UNKNOWN' } });

    expect(matchesAlertToCamera(matchingAlert, realCamera)).toBe(true);
    expect(matchesAlertToCamera(nonMatchingAlert, realCamera)).toBe(false);

    const prio = calculateCameraPriority(realCamera, [matchingAlert]);
    // Verifies no numeric risk score property was invented
    expect((prio as any).riskScore).toBeUndefined();
    expect((prio as any).numerical_score).toBeUndefined();
    expect(prio.priorityLevel).toBe('MEDIUM');
  });

  // Test 13: Accessibility labels are present
  it('13. includes accessible roles and ARIA attributes for badges and cards', () => {
    render(<CameraPriorityBadge level="CRITICAL" />);
    const badge = screen.getByRole('status');
    expect(badge).toHaveAttribute('aria-label', 'Tactical Priority: CRITICAL');

    const prioItem: PrioritizedCamera = {
      camera: testCameras[0],
      priorityLevel: 'HIGH',
      activeAlerts: [createAlert({ camera_id: 1, severity: 'HIGH' })],
      activeAlertCount: 1,
      highestSeverity: 'HIGH',
      rank: 1,
      isOfflineOrError: false,
    };

    render(
      <CameraPriorityCard
        item={prioItem}
        isSelected={false}
        onSelectCamera={vi.fn()}
      />
    );

    const card = screen.getByRole('button', { name: /Camera North Gate Perimeter/i });
    expect(card).toBeInTheDocument();
    expect(card).toHaveAttribute('tabIndex', '0');
  });

  // Test 14: Empty state works
  it('14. displays truthful empty state when no cameras are registered', () => {
    render(
      <CameraPriorityList
        prioritizedCameras={[]}
        summaryCounts={{
          criticalCount: 0,
          highCount: 0,
          mediumCount: 0,
          lowCount: 0,
          clearCount: 0,
          offlineCount: 0,
          totalActiveAlerts: 0,
          totalCameras: 0,
        }}
        selectedCameraId={null}
        loading={false}
        error={null}
        sortByPriority={true}
        onToggleSortByPriority={vi.fn()}
        onSelectCamera={vi.fn()}
        onRefresh={vi.fn()}
      />
    );

    expect(screen.getByTestId('priority-empty-state')).toBeInTheDocument();
    expect(screen.getByText(/No cameras registered/i)).toBeInTheDocument();
  });

  // Test 15: API error state works
  it('15. displays truthful error banner with retry option on API failure', () => {
    const onRefresh = vi.fn();

    render(
      <CameraPriorityList
        prioritizedCameras={[]}
        summaryCounts={{
          criticalCount: 0,
          highCount: 0,
          mediumCount: 0,
          lowCount: 0,
          clearCount: 0,
          offlineCount: 0,
          totalActiveAlerts: 0,
          totalCameras: 0,
        }}
        selectedCameraId={null}
        loading={false}
        error="Gateway timeout connecting to perimeter cameras"
        sortByPriority={true}
        onToggleSortByPriority={vi.fn()}
        onSelectCamera={vi.fn()}
        onRefresh={onRefresh}
      />
    );

    expect(screen.getByTestId('priority-error-banner')).toBeInTheDocument();
    expect(screen.getByText(/Gateway timeout connecting to perimeter cameras/i)).toBeInTheDocument();

    const retryBtn = screen.getByRole('button', { name: /Retry/i });
    fireEvent.click(retryBtn);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  // Test 16: Existing camera filtering/selection still works
  it('16. preserves camera selector functionality and supports priority sorting', () => {
    const onSelectCamera = vi.fn();
    const onToggleSort = vi.fn();

    const alerts: Alert[] = [
      createAlert({ alert_id: 'ALT-1', camera_id: 2, severity: 'CRITICAL', status: 'ACTIVE' }),
    ];
    const prioritized = sortCamerasByPriority(testCameras, alerts);

    render(
      <CameraSelector
        selectedCameraId="CAM_02"
        onSelectCamera={onSelectCamera}
        prioritizedCameras={prioritized}
        sortByPriority={true}
        onToggleSortByPriority={onToggleSort}
      />
    );

    const select = screen.getByLabelText(/Select camera feed/i) as HTMLSelectElement;
    expect(select).toBeInTheDocument();
    expect(select.value).toBe('CAM_02');

    // Change camera selection
    fireEvent.change(select, { target: { value: 'CAM_01' } });
    expect(onSelectCamera).toHaveBeenCalledWith('CAM_01');

    // Toggle sort order button
    const sortBtn = screen.getByTestId('cctv-sort-toggle-btn');
    fireEvent.click(sortBtn);
    expect(onToggleSort).toHaveBeenCalledTimes(1);
  });

  // Test 17: Cross-links to M20 Alert Center and M21 Tactical Map
  it('17. provides cross-links to M20 Alert Center and M21 Tactical Map when real data is available', () => {
    const onNavigateToAlerts = vi.fn();
    const onNavigateToMap = vi.fn();

    const prioItemWithGpsAndAlert: PrioritizedCamera = {
      camera: testCameras[0], // Has GPS "28.6139, 77.2090"
      priorityLevel: 'CRITICAL',
      activeAlerts: [createAlert({ alert_id: 'ALT-999', camera_id: 1, severity: 'CRITICAL' })],
      activeAlertCount: 1,
      highestSeverity: 'CRITICAL',
      rank: 1,
      isOfflineOrError: false,
    };

    render(
      <CameraPriorityCard
        item={prioItemWithGpsAndAlert}
        isSelected={true}
        onSelectCamera={vi.fn()}
        onNavigateToAlerts={onNavigateToAlerts}
        onNavigateToMap={onNavigateToMap}
      />
    );

    // M20 Alert navigation button
    const alertBtn = screen.getByTestId('goto-alert-CAM_01');
    fireEvent.click(alertBtn);
    expect(onNavigateToAlerts).toHaveBeenCalledWith('ALT-999');

    // M21 Map navigation button
    const mapBtn = screen.getByTestId('goto-map-CAM_01');
    fireEvent.click(mapBtn);
    expect(onNavigateToMap).toHaveBeenCalledWith('CAM_01');
  });

  // Test 18: Unmapped cameras do not fake GPS or show map link
  it('18. does not display Tactical Map link for unmapped cameras', () => {
    const prioUnmapped: PrioritizedCamera = {
      camera: testCameras[2], // CAM_03 has location: null
      priorityLevel: 'CLEAR',
      activeAlerts: [],
      activeAlertCount: 0,
      highestSeverity: null,
      rank: 3,
      isOfflineOrError: false,
    };

    render(
      <CameraPriorityCard
        item={prioUnmapped}
        isSelected={false}
        onSelectCamera={vi.fn()}
        onNavigateToMap={vi.fn()}
      />
    );

    expect(screen.queryByTestId('goto-map-CAM_03')).not.toBeInTheDocument();
  });

  // Test 19: Priority hierarchy legend component
  it('19. renders priority hierarchy legend with all levels', () => {
    render(<PriorityLegend />);
    expect(screen.getByTestId('priority-legend')).toBeInTheDocument();
    expect(screen.getByText('CRITICAL')).toBeInTheDocument();
    expect(screen.getByText('HIGH')).toBeInTheDocument();
    expect(screen.getByText('MEDIUM')).toBeInTheDocument();
    expect(screen.getByText('LOW')).toBeInTheDocument();
    expect(screen.getByText('CLEAR')).toBeInTheDocument();
    expect(screen.getByText('OFFLINE')).toBeInTheDocument();
  });
});
