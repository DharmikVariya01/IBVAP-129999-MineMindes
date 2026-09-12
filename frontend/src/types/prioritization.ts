/**
 * TypeScript data contracts and types for IBVAP M24 — Camera Prioritization & Tactical Alert Sorting.
 */

import type { Alert, AlertSeverity, Camera } from '@/types/api';

export type CameraPriorityLevel =
  | 'CRITICAL'
  | 'HIGH'
  | 'MEDIUM'
  | 'LOW'
  | 'CLEAR'
  | 'OFFLINE'
  | 'ERROR';

export interface PrioritizedCamera {
  camera: Camera;
  priorityLevel: CameraPriorityLevel;
  activeAlerts: Alert[];
  activeAlertCount: number;
  highestSeverity: AlertSeverity | null;
  rank: number;
  isOfflineOrError: boolean;
}

export interface PrioritySummaryCounts {
  criticalCount: number;
  highCount: number;
  mediumCount: number;
  lowCount: number;
  clearCount: number;
  offlineCount: number;
  totalActiveAlerts: number;
  totalCameras: number;
}
