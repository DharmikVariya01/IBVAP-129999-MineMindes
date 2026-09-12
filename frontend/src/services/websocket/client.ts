/**
 * WebSocket client for IBVAP Real-Time Camera Streaming (M17).
 *
 * Provides camera-specific connection, lifecycle management, bounded exponential
 * backoff reconnect strategy, robust error handling, and clean teardown.
 */

import { config } from '@/config/env';
import type {
  ClientMessage,
  ConnectionState,
  WebSocketMessage,
} from '@/types/websocket';

export type MessageHandler<T = unknown> = (message: WebSocketMessage<T>) => void;
export type StateChangeHandler = (state: ConnectionState) => void;
export type OpenHandler = (event: Event) => void;
export type CloseHandler = (event: CloseEvent) => void;
export type ErrorHandler = (error: Event | Error) => void;

export interface WebSocketClientOptions {
  baseUrl?: string;
  maxReconnectAttempts?: number;
  initialReconnectDelayMs?: number;
  maxReconnectDelayMs?: number;
  backoffFactor?: number;
  heartbeatIntervalMs?: number;
}

export class WebSocketClient {
  private baseUrl: string;
  private ws: WebSocket | null = null;
  private currentCameraId: string | null = null;
  private state: ConnectionState = 'DISCONNECTED';

  private messageHandlers: Set<MessageHandler> = new Set();
  private stateChangeHandlers: Set<StateChangeHandler> = new Set();
  private openHandlers: Set<OpenHandler> = new Set();
  private closeHandlers: Set<CloseHandler> = new Set();
  private errorHandlers: Set<ErrorHandler> = new Set();

  private reconnectAttempts = 0;
  private readonly maxReconnectAttempts: number;
  private readonly initialReconnectDelayMs: number;
  private readonly maxReconnectDelayMs: number;
  private readonly backoffFactor: number;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  private heartbeatIntervalMs: number;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private intentionalDisconnect = false;

  constructor(options: WebSocketClientOptions = {}) {
    this.baseUrl = (options.baseUrl || config.wsBaseUrl).replace(/\/+$/, '');
    this.maxReconnectAttempts = options.maxReconnectAttempts ?? 5;
    this.initialReconnectDelayMs = options.initialReconnectDelayMs ?? 1000;
    this.maxReconnectDelayMs = options.maxReconnectDelayMs ?? 15000;
    this.backoffFactor = options.backoffFactor ?? 2.0;
    this.heartbeatIntervalMs = options.heartbeatIntervalMs ?? 30000;
  }

  public getState(): ConnectionState {
    return this.state;
  }

  public getCameraId(): string | null {
    return this.currentCameraId;
  }

  public buildUrl(cameraId: string): string {
    const cleanBase = this.baseUrl.replace(/\/+$/, '');
    const cleanCam = encodeURIComponent(cameraId.trim());
    return `${cleanBase}/ws/${cleanCam}`;
  }

  private setState(newState: ConnectionState): void {
    if (this.state !== newState) {
      this.state = newState;
      this.stateChangeHandlers.forEach((handler) => {
        try {
          handler(newState);
        } catch (e) {
          console.error('[IBVAP WS] Error in stateChangeHandler:', e);
        }
      });
    }
  }

  /**
   * Connect to real-time stream for specified camera.
   */
  public connect(cameraId: string): void {
    if (!cameraId || !cameraId.trim()) {
      throw new Error('Camera ID must be a non-empty string');
    }

    const trimmed = cameraId.trim();

    // If already connected to the same camera, do nothing
    if (this.ws && this.currentCameraId === trimmed && (this.state === 'CONNECTED' || this.state === 'CONNECTING')) {
      return;
    }

    // Cleanly close any existing socket
    this.cleanupSocket();
    this.clearReconnectTimer();

    this.currentCameraId = trimmed;
    this.intentionalDisconnect = false;
    this.reconnectAttempts = 0;

    this.initiateConnection();
  }

  private initiateConnection(): void {
    if (!this.currentCameraId || this.intentionalDisconnect) {
      return;
    }

    const targetUrl = this.buildUrl(this.currentCameraId);
    this.setState(this.reconnectAttempts > 0 ? 'RECONNECTING' : 'CONNECTING');

    try {
      this.ws = new WebSocket(targetUrl);
    } catch (err: unknown) {
      const error = err instanceof Error ? err : new Error(String(err));
      this.notifyError(error);
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = (event: Event) => {
      this.reconnectAttempts = 0;
      this.setState('CONNECTED');
      this.startHeartbeat();

      this.openHandlers.forEach((handler) => {
        try {
          handler(event);
        } catch (e) {
          console.error('[IBVAP WS] Error in openHandler:', e);
        }
      });
    };

    this.ws.onmessage = (event: MessageEvent) => {
      this.handleIncomingMessage(event.data);
    };

    this.ws.onerror = (event: Event) => {
      this.notifyError(event);
    };

    this.ws.onclose = (event: CloseEvent) => {
      this.stopHeartbeat();
      this.closeHandlers.forEach((handler) => {
        try {
          handler(event);
        } catch (e) {
          console.error('[IBVAP WS] Error in closeHandler:', e);
        }
      });

      if (this.intentionalDisconnect) {
        this.setState('CLOSED');
      } else {
        this.scheduleReconnect();
      }
    };
  }

  private handleIncomingMessage(rawData: unknown): void {
    if (typeof rawData !== 'string') {
      // Binary or unsupported payload
      return;
    }

    try {
      const parsed = JSON.parse(rawData);

      // Validate envelope structure safely
      if (parsed && typeof parsed === 'object' && typeof parsed.type === 'string') {
        const message: WebSocketMessage = {
          type: parsed.type,
          timestamp: typeof parsed.timestamp === 'string' ? parsed.timestamp : new Date().toISOString(),
          camera_id: typeof parsed.camera_id === 'string' ? parsed.camera_id : (this.currentCameraId || ''),
          data: parsed.data ?? {},
        };

        this.messageHandlers.forEach((handler) => {
          try {
            handler(message);
          } catch (e) {
            console.error('[IBVAP WS] Error in messageHandler:', e);
          }
        });
      }
    } catch (parseError) {
      // Malformed JSON: log and discard without crashing
      console.warn('[IBVAP WS] Received malformed JSON from server, ignoring:', parseError);
    }
  }

  private scheduleReconnect(): void {
    this.clearReconnectTimer();

    if (this.intentionalDisconnect || !this.currentCameraId) {
      this.setState('DISCONNECTED');
      return;
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.setState('CLOSED');
      this.notifyError(new Error(`WebSocket reconnect failed after ${this.maxReconnectAttempts} attempts.`));
      return;
    }

    this.reconnectAttempts++;
    const delay = Math.min(
      this.initialReconnectDelayMs * Math.pow(this.backoffFactor, this.reconnectAttempts - 1),
      this.maxReconnectDelayMs
    );

    this.setState('RECONNECTING');

    this.reconnectTimer = setTimeout(() => {
      this.initiateConnection();
    }, delay);
  }

  public disconnect(): void {
    this.intentionalDisconnect = true;
    this.clearReconnectTimer();
    this.stopHeartbeat();
    this.cleanupSocket();
    this.setState('DISCONNECTED');
    this.currentCameraId = null;
  }

  public send(payload: ClientMessage | string): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return false;
    }

    try {
      const serialized = typeof payload === 'string' ? payload : JSON.stringify(payload);
      this.ws.send(serialized);
      return true;
    } catch (err) {
      console.error('[IBVAP WS] Send failed:', err);
      return false;
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    if (this.heartbeatIntervalMs <= 0) return;

    this.heartbeatTimer = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.send({
          type: 'ping',
          camera_id: this.currentCameraId,
        });
      }
    }, this.heartbeatIntervalMs);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private cleanupSocket(): void {
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onerror = null;
      this.ws.onclose = null;

      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        try {
          this.ws.close(1000, 'Client disconnect');
        } catch {
          // ignore
        }
      }
      this.ws = null;
    }
  }

  private notifyError(error: Event | Error): void {
    this.errorHandlers.forEach((handler) => {
      try {
        handler(error);
      } catch (e) {
        console.error('[IBVAP WS] Error in errorHandler:', e);
      }
    });
  }

  // --- Listener Subscriptions ---

  public onMessage(handler: MessageHandler): () => void {
    this.messageHandlers.add(handler);
    return () => this.messageHandlers.delete(handler);
  }

  public onStateChange(handler: StateChangeHandler): () => void {
    this.stateChangeHandlers.add(handler);
    return () => this.stateChangeHandlers.delete(handler);
  }

  public onOpen(handler: OpenHandler): () => void {
    this.openHandlers.add(handler);
    return () => this.openHandlers.delete(handler);
  }

  public onClose(handler: CloseHandler): () => void {
    this.closeHandlers.add(handler);
    return () => this.closeHandlers.delete(handler);
  }

  public onError(handler: ErrorHandler): () => void {
    this.errorHandlers.add(handler);
    return () => this.errorHandlers.delete(handler);
  }

  public removeAllListeners(): void {
    this.messageHandlers.clear();
    this.stateChangeHandlers.clear();
    this.openHandlers.clear();
    this.closeHandlers.clear();
    this.errorHandlers.clear();
  }
}

export const webSocketClient = new WebSocketClient();
