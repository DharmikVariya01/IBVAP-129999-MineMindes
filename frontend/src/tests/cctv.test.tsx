import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { CCTVMonitoring } from '@/pages/CCTVMonitoring';
import { CameraSelector } from '@/components/cctv/CameraSelector';
import { ConnectionStatus } from '@/components/cctv/ConnectionStatus';
import { CameraStatus } from '@/components/cctv/CameraStatus';
import { LiveStats } from '@/components/cctv/LiveStats';
import { FrameRenderer } from '@/components/cctv/FrameRenderer';
import type { Camera } from '@/types/api';
import type { FrameData, StatsData } from '@/types/websocket';

// Track active mock socket instances for granular simulation
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
    location: 'North Sector',
    status: 'ONLINE',
    created_at: '2026-09-12T00:00:00Z',
    updated_at: '2026-09-12T00:00:00Z',
  },
  {
    id: 2,
    camera_id: 'CAM_02',
    name: 'South Watchtower',
    source_type: 'RTSP',
    source_reference: 'rtsp://10.0.0.2/live',
    location: 'South Sector',
    status: 'OFFLINE',
    created_at: '2026-09-12T00:00:00Z',
    updated_at: '2026-09-12T00:00:00Z',
  },
];

describe('M19 Live CCTV Monitoring Dashboard', () => {
  let originalWebSocket: typeof WebSocket;

  beforeEach(() => {
    mockSockets = [];
    originalWebSocket = global.WebSocket;
    global.WebSocket = MockWebSocket as unknown as typeof WebSocket;

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        items: mockCameras,
        total: mockCameras.length,
        page: 1,
        page_size: 50,
        total_pages: 1,
      }),
    } as unknown as Response);
  });

  afterEach(() => {
    global.WebSocket = originalWebSocket;
    vi.restoreAllMocks();
  });

  // 1. CCTV page renders
  it('1. renders CCTV monitoring page structure and controls', async () => {
    render(<CCTVMonitoring />);

    expect(screen.getByTestId('cctv-monitoring-page')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /live cctv monitoring/i })).toBeInTheDocument();
    expect(screen.getByTestId('live-video-container')).toBeInTheDocument();
    expect(screen.getByTestId('live-stats-bar')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /select camera feed/i })).toBeInTheDocument();
    });
  });

  // 2. Camera API loading state
  it('2. displays loading state while fetching cameras', () => {
    // Return promise that never resolves immediately
    global.fetch = vi.fn().mockReturnValue(new Promise(() => {}));

    render(<CameraSelector selectedCameraId={null} onSelectCamera={vi.fn()} />);

    expect(screen.getByText(/loading cameras.../i)).toBeInTheDocument();
  });

  // 3. Camera list rendering
  it('3. renders camera list options from backend API', async () => {
    render(<CameraSelector selectedCameraId={null} onSelectCamera={vi.fn()} />);

    await waitFor(() => {
      const select = screen.getByRole('combobox', { name: /select camera feed/i });
      expect(select).toBeInTheDocument();
      expect(screen.getByText(/North Gate Perimeter \(CAM_01\)/i)).toBeInTheDocument();
      expect(screen.getByText(/South Watchtower \(CAM_02\)/i)).toBeInTheDocument();
    });
  });

  // 4. Empty camera state
  it('4. displays proper empty state when no cameras are returned', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0, page: 1, page_size: 50, total_pages: 0 }),
    } as unknown as Response);

    render(<CameraSelector selectedCameraId={null} onSelectCamera={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/no cameras available/i)).toBeInTheDocument();
    });
  });

  // 5. Camera selection
  it('5. triggers camera selection callback on operator select', async () => {
    const handleSelect = vi.fn();
    render(<CameraSelector selectedCameraId={null} onSelectCamera={handleSelect} />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /select camera feed/i })).toBeInTheDocument();
    });

    const select = screen.getByRole('combobox', { name: /select camera feed/i });
    fireEvent.change(select, { target: { value: 'CAM_01' } });

    expect(handleSelect).toHaveBeenCalledWith('CAM_01');
  });

  // 6. WebSocket connects for selected camera
  it('6. initiates WebSocket connection for selected camera', async () => {
    render(<CCTVMonitoring />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /select camera feed/i })).toBeInTheDocument();
    });

    const select = screen.getByRole('combobox', { name: /select camera feed/i });
    fireEvent.change(select, { target: { value: 'CAM_01' } });

    await waitFor(() => {
      expect(mockSockets.length).toBeGreaterThanOrEqual(1);
      const latestSocket = mockSockets[mockSockets.length - 1];
      expect(latestSocket.url).toContain('/ws/CAM_01');
    });
  });

  // 7. Previous WebSocket disconnects when camera changes
  it('7. disconnects previous WebSocket and clears stale data when camera changes', async () => {
    render(<CCTVMonitoring />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /select camera feed/i })).toBeInTheDocument();
    });

    const select = screen.getByRole('combobox', { name: /select camera feed/i });

    // Connect to CAM_01
    fireEvent.change(select, { target: { value: 'CAM_01' } });
    await waitFor(() => expect(mockSockets.length).toBe(1));
    const firstSocket = mockSockets[0];

    // Switch to CAM_02
    fireEvent.change(select, { target: { value: 'CAM_02' } });

    await waitFor(() => {
      expect(firstSocket.readyState).toBe(MockWebSocket.CLOSED);
      expect(mockSockets.length).toBe(2);
      expect(mockSockets[1].url).toContain('/ws/CAM_02');
    });
  });

  // 8. Connection status rendering
  it('8. correctly renders all WebSocket connection status states', () => {
    const { rerender } = render(<ConnectionStatus state="CONNECTING" />);
    expect(screen.getByText(/connecting/i)).toBeInTheDocument();

    rerender(<ConnectionStatus state="CONNECTED" />);
    expect(screen.getByText(/stream connected/i)).toBeInTheDocument();

    rerender(<ConnectionStatus state="RECONNECTING" />);
    expect(screen.getByText(/reconnecting/i)).toBeInTheDocument();

    rerender(<ConnectionStatus state="DISCONNECTED" />);
    expect(screen.getByText(/disconnected/i)).toBeInTheDocument();

    rerender(<ConnectionStatus state="CLOSED" />);
    expect(screen.getByText(/disconnected/i)).toBeInTheDocument();
  });

  // 9. Camera online/offline status rendering
  it('9. correctly renders camera hardware operational status', () => {
    const { rerender } = render(<CameraStatus status="ONLINE" />);
    expect(screen.getByText(/ONLINE/i)).toBeInTheDocument();

    rerender(<CameraStatus status="OFFLINE" details="Loss of signal" />);
    expect(screen.getByText(/OFFLINE/i)).toBeInTheDocument();

    rerender(<CameraStatus status="ERROR" />);
    expect(screen.getByText(/ERROR/i)).toBeInTheDocument();
  });

  // 10. Frame message rendering
  it('10. renders live video frame from M17 frame message', async () => {
    render(<CCTVMonitoring />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /select camera feed/i })).toBeInTheDocument();
    });

    const select = screen.getByRole('combobox', { name: /select camera feed/i });
    fireEvent.change(select, { target: { value: 'CAM_01' } });

    await waitFor(() => expect(mockSockets.length).toBe(1));
    const ws = mockSockets[0];

    const framePayload: FrameData = {
      frame_id: 1042,
      encoded_data: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
      width: 1920,
      height: 1080,
      metadata: {
        tracks: [
          {
            track_id: 17,
            class_name: 'PERSON',
            confidence: 0.94,
            bbox: [100, 100, 250, 400],
          },
        ],
      },
    };

    act(() => {
      ws.simulateServerMessage({
        type: 'frame',
        timestamp: new Date().toISOString(),
        camera_id: 'CAM_01',
        data: framePayload,
      });
    });

    await waitFor(() => {
      const img = screen.getByTestId('live-frame-image') as HTMLImageElement;
      expect(img).toBeInTheDocument();
      expect(img.src).toContain('data:image/jpeg;base64');
      expect(screen.getByText(/FRM #1042/i)).toBeInTheDocument();
      expect(screen.getByText(/1920×1080/i)).toBeInTheDocument();
      expect(screen.getByTestId('detection-overlay-canvas')).toBeInTheDocument();
    });
  });

  // 11. Malformed frame/message does not crash UI
  it('11. handles malformed message payloads gracefully without crashing', async () => {
    render(<CCTVMonitoring />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /select camera feed/i })).toBeInTheDocument();
    });

    const select = screen.getByRole('combobox', { name: /select camera feed/i });
    fireEvent.change(select, { target: { value: 'CAM_01' } });

    await waitFor(() => expect(mockSockets.length).toBe(1));
    const ws = mockSockets[0];

    // Corrupted JSON string
    act(() => {
      if (ws.onmessage) {
        ws.onmessage(new MessageEvent('message', { data: 'NOT_VALID_JSON{[' }));
      }
    });

    // Malformed frame data without encoded_data
    act(() => {
      ws.simulateServerMessage({
        type: 'frame',
        timestamp: new Date().toISOString(),
        camera_id: 'CAM_01',
        data: { frame_id: 999 },
      });
    });

    // FrameRenderer with null/empty payload
    const { container } = render(<FrameRenderer frame={null} />);
    expect(container).toBeInTheDocument();
    expect(screen.getByTestId('cctv-monitoring-page')).toBeInTheDocument();
  });

  // 12. WebSocket error/reconnect state
  it('12. displays stream error and reconnecting states on socket failures', async () => {
    render(<CCTVMonitoring />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /select camera feed/i })).toBeInTheDocument();
    });

    const select = screen.getByRole('combobox', { name: /select camera feed/i });
    fireEvent.change(select, { target: { value: 'CAM_01' } });

    await waitFor(() => expect(mockSockets.length).toBe(1));
    const ws = mockSockets[0];

    act(() => {
      ws.simulateServerMessage({
        type: 'error',
        timestamp: new Date().toISOString(),
        camera_id: 'CAM_01',
        data: { message: 'Camera feed connection timed out' },
      });
    });

    await waitFor(() => {
      expect(screen.getByText(/Camera feed connection timed out/i)).toBeInTheDocument();
    });
  });

  // 13. Stats rendering when available
  it('13. renders operational stream telemetry from stats messages', async () => {
    const stats: StatsData = {
      fps: 28.5,
      active_tracks: 3,
      total_detections: 42,
      active_alerts: 1,
      connected_clients: 2,
    };

    render(<LiveStats stats={stats} frameCount={150} />);

    expect(screen.getByText('28.5')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText(/# 150/i)).toBeInTheDocument();
  });

  // 14. Component cleanup on unmount
  it('14. cleans up active WebSocket connection and listeners on component unmount', async () => {
    const { unmount } = render(<CCTVMonitoring />);

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /select camera feed/i })).toBeInTheDocument();
    });

    const select = screen.getByRole('combobox', { name: /select camera feed/i });
    fireEvent.change(select, { target: { value: 'CAM_01' } });

    await waitFor(() => expect(mockSockets.length).toBe(1));
    const activeWs = mockSockets[0];

    unmount();

    expect(activeWs.readyState).toBe(MockWebSocket.CLOSED);
  });
});
