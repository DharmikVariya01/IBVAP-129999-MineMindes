/**
 * React hook for IBVAP M19 Live Camera Streaming.
 *
 * Connects to the M17 WebSocket stream (WS /api/v1/ws/{camera_id}) for a selected camera.
 * Dispatches live frames, operational camera status, and streaming statistics.
 * Optimizes performance by allowing frame subscriptions without triggering re-renders of the full layout.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { WebSocketClient } from '@/services/websocket/client';
import type {
  CameraStreamStatus,
  ConnectionState,
  FrameData,
  StatsData,
  WebSocketMessage,
} from '@/types/websocket';

export type FrameListener = (frame: FrameData) => void;

export interface UseCameraStreamReturn {
  connectionState: ConnectionState;
  cameraStatus: CameraStreamStatus | null;
  cameraStatusDetails: string | null;
  stats: StatsData | null;
  latestFrame: FrameData | null;
  error: string | null;
  frameCount: number;
  connect: (targetCameraId?: string) => void;
  disconnect: () => void;
  subscribeFrame: (listener: FrameListener) => () => void;
}

export function useCameraStream(
  cameraId?: string | null,
  options?: { autoConnect?: boolean }
): UseCameraStreamReturn {
  const autoConnect = options?.autoConnect ?? true;
  const clientRef = useRef<WebSocketClient | null>(null);

  if (!clientRef.current) {
    clientRef.current = new WebSocketClient();
  }

  const [connectionState, setConnectionState] = useState<ConnectionState>('DISCONNECTED');
  const [cameraStatus, setCameraStatus] = useState<CameraStreamStatus | null>(null);
  const [cameraStatusDetails, setCameraStatusDetails] = useState<string | null>(null);
  const [stats, setStats] = useState<StatsData | null>(null);
  const [latestFrame, setLatestFrame] = useState<FrameData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [frameCount, setFrameCount] = useState<number>(0);

  const frameListenersRef = useRef<Set<FrameListener>>(new Set());
  const activeCameraIdRef = useRef<string | null>(null);

  const subscribeFrame = useCallback((listener: FrameListener): (() => void) => {
    frameListenersRef.current.add(listener);
    return () => {
      frameListenersRef.current.delete(listener);
    };
  }, []);

  const disconnect = useCallback(() => {
    clientRef.current?.disconnect();
    activeCameraIdRef.current = null;
    setConnectionState('DISCONNECTED');
    setLatestFrame(null);
    setCameraStatus(null);
    setCameraStatusDetails(null);
    setStats(null);
    setError(null);
    setFrameCount(0);
  }, []);

  const connect = useCallback(
    (targetCameraId?: string) => {
      const idToConnect = targetCameraId || cameraId;
      if (!idToConnect || !idToConnect.trim()) {
        setError('Cannot connect: No camera ID provided');
        return;
      }

      const trimmed = idToConnect.trim();

      // Clear stale frame data and statuses on camera switch
      if (activeCameraIdRef.current !== trimmed) {
        setLatestFrame(null);
        setCameraStatus(null);
        setCameraStatusDetails(null);
        setStats(null);
        setError(null);
        setFrameCount(0);
      }

      activeCameraIdRef.current = trimmed;
      setError(null);

      try {
        clientRef.current?.connect(trimmed);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
      }
    },
    [cameraId]
  );

  useEffect(() => {
    const client = clientRef.current;
    if (!client) return;

    const unsubs = [
      client.onStateChange((newState) => {
        setConnectionState(newState);
        if (newState === 'CONNECTED') {
          setError(null);
        }
      }),

      client.onError((err) => {
        const message = err instanceof Error ? err.message : 'WebSocket connection error';
        setError(message);
      }),

      client.onMessage((msg: WebSocketMessage) => {
        if (!msg || !msg.type) return;

        switch (msg.type) {
          case 'frame': {
            const framePayload = msg.data as FrameData;
            if (framePayload && framePayload.encoded_data) {
              setLatestFrame(framePayload);
              setFrameCount((prev) => prev + 1);
              frameListenersRef.current.forEach((listener) => {
                try {
                  listener(framePayload);
                } catch (e) {
                  console.error('[useCameraStream] Error in frame listener:', e);
                }
              });
            }
            break;
          }

          case 'camera_status': {
            const statusPayload = msg.data as { status?: CameraStreamStatus; details?: string };
            if (statusPayload && statusPayload.status) {
              setCameraStatus(statusPayload.status);
              setCameraStatusDetails(statusPayload.details || null);
            }
            break;
          }

          case 'stats': {
            const statsPayload = msg.data as StatsData;
            if (statsPayload) {
              setStats(statsPayload);
            }
            break;
          }

          case 'error': {
            const errorPayload = msg.data as { message?: string; error?: string };
            const safeMsg = errorPayload?.message || errorPayload?.error || 'Stream error reported by backend';
            setError(safeMsg);
            break;
          }

          case 'connection':
          case 'heartbeat':
          default:
            // Heartbeat/connection envelope handled transparently
            break;
        }
      }),
    ];

    if (autoConnect && cameraId) {
      connect(cameraId);
    }

    return () => {
      unsubs.forEach((unsub) => unsub());
      client.disconnect();
    };
  }, [cameraId, autoConnect, connect]);

  return {
    connectionState,
    cameraStatus,
    cameraStatusDetails,
    stats,
    latestFrame,
    error,
    frameCount,
    connect,
    disconnect,
    subscribeFrame,
  };
}
