import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { WebSocketClient } from '@/services/websocket/client';
import type { WebSocketMessage } from '@/types/websocket';

// Mock browser WebSocket
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
    setTimeout(() => {
      if (this.readyState === MockWebSocket.CONNECTING) {
        this.readyState = MockWebSocket.OPEN;
        this.onopen?.(new Event('open'));
      }
    }, 10);
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
      this.onmessage(new MessageEvent('message', {
        data: typeof messageObj === 'string' ? messageObj : JSON.stringify(messageObj),
      }));
    }
  }

  simulateError(): void {
    this.onerror?.(new Event('error'));
  }
}

describe('WebSocketClient (M17 WebSocket Real-Time Layer)', () => {
  let originalWebSocket: typeof WebSocket;

  beforeEach(() => {
    originalWebSocket = global.WebSocket;
    global.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    vi.useFakeTimers();
  });

  afterEach(() => {
    global.WebSocket = originalWebSocket;
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('builds correct camera URL with encoded camera identifier', () => {
    const client = new WebSocketClient({ baseUrl: 'ws://surveillance-host:8000/api/v1' });
    const url = client.buildUrl('CAM-01');
    expect(url).toBe('ws://surveillance-host:8000/api/v1/ws/CAM-01');

    const encodedUrl = client.buildUrl('SECTOR/NORTH-01');
    expect(encodedUrl).toBe('ws://surveillance-host:8000/api/v1/ws/SECTOR%2FNORTH-01');
  });

  it('handles connection state transitions correctly', async () => {
    const client = new WebSocketClient({ baseUrl: 'ws://localhost:8000/api/v1' });
    const states: string[] = [];
    client.onStateChange((state) => states.push(state));

    expect(client.getState()).toBe('DISCONNECTED');

    client.connect('CAM-01');
    expect(client.getState()).toBe('CONNECTING');

    // Fast forward to trigger mock WebSocket onopen
    await vi.advanceTimersByTimeAsync(15);
    expect(client.getState()).toBe('CONNECTED');

    client.disconnect();
    expect(client.getState()).toBe('DISCONNECTED');
  });

  it('parses valid JSON WebSocket message envelope and notifies handlers', async () => {
    const client = new WebSocketClient({ baseUrl: 'ws://localhost:8000/api/v1' });
    let receivedMessage: WebSocketMessage | null = null;
    client.onMessage((msg) => {
      receivedMessage = msg;
    });

    client.connect('CAM-01');
    await vi.advanceTimersByTimeAsync(15);

    // Access underlying mock socket
    const mockWs = (client as unknown as { ws: MockWebSocket }).ws;
    expect(mockWs).toBeDefined();

    mockWs.simulateServerMessage({
      type: 'alert',
      timestamp: '2026-09-12T15:00:00Z',
      camera_id: 'CAM-01',
      data: {
        alert_id: 'ALT-100',
        alert_type: 'FENCE_BREACH',
        severity: 'CRITICAL',
      },
    });

    expect(receivedMessage).not.toBeNull();
    expect(receivedMessage!.type).toBe('alert');
    expect(receivedMessage!.camera_id).toBe('CAM-01');
    expect((receivedMessage!.data as { alert_id: string }).alert_id).toBe('ALT-100');
  });

  it('handles unknown message types without crashing', async () => {
    const client = new WebSocketClient({ baseUrl: 'ws://localhost:8000/api/v1' });
    let receivedMessage: WebSocketMessage | null = null;
    client.onMessage((msg) => {
      receivedMessage = msg;
    });

    client.connect('CAM-01');
    await vi.advanceTimersByTimeAsync(15);

    const mockWs = (client as unknown as { ws: MockWebSocket }).ws;

    // Send unknown message type
    expect(() => {
      mockWs.simulateServerMessage({
        type: 'future_quantum_radar_event',
        timestamp: '2026-09-12T15:00:00Z',
        camera_id: 'CAM-01',
        data: { custom: 'future_data' },
      });
    }).not.toThrow();

    expect(receivedMessage).not.toBeNull();
    expect(receivedMessage!.type).toBe('future_quantum_radar_event');
  });

  it('handles malformed JSON without crashing', async () => {
    const client = new WebSocketClient({ baseUrl: 'ws://localhost:8000/api/v1' });
    const spyWarn = vi.spyOn(console, 'warn').mockImplementation(() => {});

    client.connect('CAM-01');
    await vi.advanceTimersByTimeAsync(15);

    const mockWs = (client as unknown as { ws: MockWebSocket }).ws;

    expect(() => {
      mockWs.simulateServerMessage('{ malformed json! ]');
    }).not.toThrow();

    expect(spyWarn).toHaveBeenCalled();
  });

  it('disconnect cleans up listeners, socket, and timers', async () => {
    const client = new WebSocketClient({
      baseUrl: 'ws://localhost:8000/api/v1',
      heartbeatIntervalMs: 5000,
    });

    client.connect('CAM-01');
    await vi.advanceTimersByTimeAsync(15);

    const mockWs = (client as unknown as { ws: MockWebSocket }).ws;
    expect(mockWs.readyState).toBe(MockWebSocket.OPEN);

    client.disconnect();

    expect(client.getState()).toBe('DISCONNECTED');
    expect(client.getCameraId()).toBeNull();
    expect((client as unknown as { ws: MockWebSocket | null }).ws).toBeNull();
  });

  it('executes bounded reconnect strategy and stops after max attempts', async () => {
    const maxRetries = 3;
    const client = new WebSocketClient({
      baseUrl: 'ws://localhost:8000/api/v1',
      maxReconnectAttempts: maxRetries,
      initialReconnectDelayMs: 100,
      backoffFactor: 2.0,
    });

    let errorReported: Error | null = null;
    client.onError((err) => {
      if (err instanceof Error) {
        errorReported = err;
      }
    });

    client.connect('CAM-01');
    await vi.advanceTimersByTimeAsync(15);

    // Trigger unexpected close to initiate reconnect loop
    const firstWs = (client as unknown as { ws: MockWebSocket }).ws;
    firstWs.close(1006, 'Abnormal closure');

    // Retry 1: delay 100ms
    await vi.advanceTimersByTimeAsync(105);
    expect(client.getState()).toBe('RECONNECTING');

    const retry1Ws = (client as unknown as { ws: MockWebSocket }).ws;
    retry1Ws.close(1006, 'Abnormal closure');

    // Retry 2: delay 200ms
    await vi.advanceTimersByTimeAsync(205);
    const retry2Ws = (client as unknown as { ws: MockWebSocket }).ws;
    retry2Ws.close(1006, 'Abnormal closure');

    // Retry 3: delay 400ms
    await vi.advanceTimersByTimeAsync(405);
    const retry3Ws = (client as unknown as { ws: MockWebSocket }).ws;
    retry3Ws.close(1006, 'Abnormal closure');

    // Next iteration exceeds maxRetries -> should transition to CLOSED
    expect(client.getState()).toBe('CLOSED');
    expect(errorReported).not.toBeNull();
    expect(errorReported!.message).toContain(`reconnect failed after ${maxRetries} attempts`);
  });
});
