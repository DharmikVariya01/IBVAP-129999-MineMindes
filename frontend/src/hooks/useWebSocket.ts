/**
 * React hook for IBVAP WebSocket camera streaming.
 *
 * Wraps WebSocketClient to provide reactive state management, automatic
 * lifecycle subscription/unsubscription, and clean teardown.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { WebSocketClient } from '@/services/websocket/client';
import type {
  ClientMessage,
  ConnectionState,
  WebSocketMessage,
} from '@/types/websocket';

export interface UseWebSocketReturn {
  connected: boolean;
  connecting: boolean;
  state: ConnectionState;
  error: string | null;
  lastMessage: WebSocketMessage | null;
  connect: (id?: string) => void;
  disconnect: () => void;
  sendMessage: (message: ClientMessage | string) => boolean;
}

export function useWebSocket(
  cameraId?: string | null,
  options?: { autoConnect?: boolean }
): UseWebSocketReturn {
  const autoConnect = options?.autoConnect ?? true;
  const clientRef = useRef<WebSocketClient | null>(null);

  if (!clientRef.current) {
    clientRef.current = new WebSocketClient();
  }

  const [state, setState] = useState<ConnectionState>('DISCONNECTED');
  const [error, setError] = useState<string | null>(null);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);

  const connect = useCallback((targetCameraId?: string) => {
    const idToConnect = targetCameraId || cameraId;
    if (!idToConnect) {
      setError('Cannot connect: No camera ID provided');
      return;
    }
    setError(null);
    try {
      clientRef.current?.connect(idToConnect);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [cameraId]);

  const disconnect = useCallback(() => {
    clientRef.current?.disconnect();
    setError(null);
  }, []);

  const sendMessage = useCallback((message: ClientMessage | string): boolean => {
    return clientRef.current?.send(message) ?? false;
  }, []);

  useEffect(() => {
    const client = clientRef.current;
    if (!client) return;

    const unsubs = [
      client.onStateChange((newState) => {
        setState(newState);
        if (newState === 'CONNECTED') {
          setError(null);
        }
      }),
      client.onMessage((msg) => {
        setLastMessage(msg);
      }),
      client.onError((err) => {
        const message = err instanceof Error ? err.message : 'WebSocket connection error';
        setError(message);
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
    connected: state === 'CONNECTED',
    connecting: state === 'CONNECTING' || state === 'RECONNECTING',
    state,
    error,
    lastMessage,
    connect,
    disconnect,
    sendMessage,
  };
}
