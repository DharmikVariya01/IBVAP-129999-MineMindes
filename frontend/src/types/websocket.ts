/**
 * WebSocket message contracts and types for IBVAP M17 Real-Time Streaming.
 */

export type WebSocketMessageType =
  | 'connection'
  | 'heartbeat'
  | 'frame'
  | 'alert'
  | 'camera_status'
  | 'stats'
  | 'error'
  | (string & {});

export type CameraStreamStatus = 'ONLINE' | 'OFFLINE' | 'CONNECTING' | 'ERROR';

export interface ConnectionData {
  status: string;
  client_id?: string | null;
  message: string;
  [key: string]: unknown;
}

export interface HeartbeatData {
  reply?: string | null;
  [key: string]: unknown;
}

export interface FrameData {
  frame_id?: number | null;
  encoded_data: string;
  width?: number | null;
  height?: number | null;
  metadata?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface AlertData {
  alert_id: number | string;
  camera_id: string;
  track_id?: number | null;
  alert_type: string;
  severity: string;
  status: string;
  message: string;
  timestamp: string;
  zone_info?: Record<string, unknown> | null;
  evidence_reference?: string | null;
  [key: string]: unknown;
}

export interface CameraStatusData {
  status: CameraStreamStatus;
  details?: string | null;
  [key: string]: unknown;
}

export interface StatsData {
  active_tracks: number;
  total_detections: number;
  active_alerts: number;
  fps: number;
  connected_clients: number;
  [key: string]: unknown;
}

export interface ErrorData {
  error: string;
  message: string;
  [key: string]: unknown;
}

/** Canonical WebSocket Envelope matching M17 backend */
export interface WebSocketMessage<T = unknown> {
  type: WebSocketMessageType;
  timestamp: string;
  camera_id: string;
  data: T;
}

/** Outbound message schema for client -> server commands */
export interface ClientMessage {
  type: string;
  camera_id?: string | null;
  data?: Record<string, unknown>;
}

export type ConnectionState =
  | 'DISCONNECTED'
  | 'CONNECTING'
  | 'CONNECTED'
  | 'RECONNECTING'
  | 'CLOSED';
