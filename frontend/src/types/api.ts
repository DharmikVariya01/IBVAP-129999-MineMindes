/**
 * API data contracts and interfaces for IBVAP M16 REST resources.
 */

export type CameraSourceType = 'RTSP' | 'WEBCAM' | 'VIDEO_FILE' | 'IMAGE_DIR';
export type CameraStatus = 'ONLINE' | 'OFFLINE' | 'ERROR';

export interface Camera {
  id: number;
  camera_id: string;
  name: string;
  source_type: CameraSourceType;
  source_reference: string;
  location: string | null;
  status: CameraStatus;
  created_at: string;
  updated_at: string;
}

export type AlertType = 'FENCE_BREACH' | 'LOITERING';
export type AlertSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
export type AlertStatus = 'ACTIVE' | 'ACKNOWLEDGED' | 'RESOLVED';

export interface Alert {
  id: number;
  alert_id: string;
  camera_id: number | null;
  track_id: number | null;
  event_id: number | null;
  zone_id: number | null;
  alert_type: AlertType;
  severity: AlertSeverity;
  status: AlertStatus;
  message: string;
  alert_timestamp: string;
  alert_metadata: Record<string, unknown>;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlertUpdatePayload {
  status?: AlertStatus;
  acknowledged_by?: string;
  resolved_by?: string;
}

export type TrackStatus = 'ACTIVE' | 'LOST' | 'COMPLETED';

export interface Track {
  id: number;
  track_id: number;
  camera_id: number | null;
  class_id: number;
  class_name: string;
  first_seen: string;
  last_seen: string;
  frame_count: number;
  last_confidence: number;
  bbox_x1: number | null;
  bbox_y1: number | null;
  bbox_x2: number | null;
  bbox_y2: number | null;
  last_center_x: number | null;
  last_center_y: number | null;
  status: TrackStatus;
  observation_metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  events_count?: number | null;
  alerts_count?: number | null;
}

export type EventType = 'FENCE_BREACH' | 'LOITERING';

export interface Event {
  id: number;
  event_id: string | null;
  camera_id: number | null;
  track_id: number | null;
  zone_id: number | null;
  event_type: EventType;
  frame_id: number | null;
  timestamp: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface Evidence {
  id: number;
  evidence_id: string;
  alert_id: number;
  camera_id: number | null;
  track_id: number | null;
  file_path: string;
  filename: string;
  frame_width: number;
  frame_height: number;
  capture_timestamp: string;
  alert_timestamp: string | null;
  evidence_metadata: Record<string, unknown>;
  created_at: string;
}

export interface PlatformStats {
  cameras: number;
  tracks: number;
  events: number;
  alerts: number;
  evidence: number;
  alerts_by_status: Record<string, number>;
  alerts_by_severity: Record<string, number>;
  cameras_by_status: Record<string, number>;
  tracks_by_status: Record<string, number>;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface PaginationParams {
  page?: number;
  page_size?: number;
}
