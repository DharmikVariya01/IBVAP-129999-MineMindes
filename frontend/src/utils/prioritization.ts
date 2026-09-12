/**
 * Deterministic tactical priority calculation engine for IBVAP M24.
 *
 * Rules:
 * 1. Severity ordering: CRITICAL > HIGH > MEDIUM > LOW
 * 2. Active alerts outrank cameras with no active alerts (CLEAR).
 * 3. Within the same severity: more active alerts = higher priority.
 * 4. Offline/error cameras are classified truthfully as OFFLINE / ERROR and placed below operational cameras.
 * 5. Numerical "risk scores" are NOT invented.
 */

import type { Alert, AlertSeverity, Camera } from '@/types/api';
import type {
  CameraPriorityLevel,
  PrioritizedCamera,
  PrioritySummaryCounts,
} from '@/types/prioritization';

export const SEVERITY_WEIGHTS: Record<AlertSeverity, number> = {
  CRITICAL: 4,
  HIGH: 3,
  MEDIUM: 2,
  LOW: 1,
};

export const PRIORITY_TIER_ORDER: Record<CameraPriorityLevel, number> = {
  CRITICAL: 1,
  HIGH: 2,
  MEDIUM: 3,
  LOW: 4,
  CLEAR: 5,
  OFFLINE: 6,
  ERROR: 7,
};

/**
 * Determine if an alert belongs to a given camera using all available real identifiers.
 */
export function matchesAlertToCamera(alert: Alert, camera: Camera): boolean {
  if (!alert || !camera) return false;

  const targetCamIdStr = String(camera.camera_id || '').trim().toUpperCase();
  const targetIdNum = camera.id;

  // 1. Check numeric or string camera_id field on alert
  if (alert.camera_id !== null && alert.camera_id !== undefined) {
    if (typeof alert.camera_id === 'number' && alert.camera_id === targetIdNum) {
      return true;
    }
    const alertCamStr = String(alert.camera_id).trim().toUpperCase();
    if (alertCamStr === targetCamIdStr || alertCamStr === String(targetIdNum)) {
      return true;
    }
  }

  // 2. Check alert_metadata if present
  if (alert.alert_metadata && typeof alert.alert_metadata === 'object') {
    const metaCamId = alert.alert_metadata.camera_id;
    if (metaCamId !== undefined && metaCamId !== null) {
      const metaStr = String(metaCamId).trim().toUpperCase();
      if (metaStr === targetCamIdStr || metaStr === String(targetIdNum)) {
        return true;
      }
    }

    const metaCamCode = alert.alert_metadata.camera_code;
    if (metaCamCode !== undefined && metaCamCode !== null) {
      const codeStr = String(metaCamCode).trim().toUpperCase();
      if (codeStr === targetCamIdStr || codeStr === String(targetIdNum)) {
        return true;
      }
    }
  }

  return false;
}

/**
 * Calculate the tactical priority details for an individual camera.
 */
export function calculateCameraPriority(camera: Camera, alerts: Alert[]): PrioritizedCamera {
  const isOffline = camera.status === 'OFFLINE';
  const isError = camera.status === 'ERROR';
  const isOfflineOrError = isOffline || isError;

  // Find all ACTIVE alerts matching this camera
  const cameraActiveAlerts = alerts.filter(
    (a) => a.status === 'ACTIVE' && matchesAlertToCamera(a, camera)
  );

  const activeAlertCount = cameraActiveAlerts.length;

  // If camera is offline or in error, it must NOT be presented as operationally healthy
  if (isOfflineOrError) {
    return {
      camera,
      priorityLevel: isError ? 'ERROR' : 'OFFLINE',
      activeAlerts: cameraActiveAlerts,
      activeAlertCount,
      highestSeverity: null,
      rank: 999, // Assigned during sorting
      isOfflineOrError: true,
    };
  }

  // Operational camera with no active alerts
  if (activeAlertCount === 0) {
    return {
      camera,
      priorityLevel: 'CLEAR',
      activeAlerts: [],
      activeAlertCount: 0,
      highestSeverity: null,
      rank: 999,
      isOfflineOrError: false,
    };
  }

  // Find highest active alert severity
  let highestSev: AlertSeverity = 'LOW';
  let maxWeight = 0;

  for (const alert of cameraActiveAlerts) {
    const weight = SEVERITY_WEIGHTS[alert.severity] || 0;
    if (weight > maxWeight) {
      maxWeight = weight;
      highestSev = alert.severity;
    }
  }

  const priorityLevel: CameraPriorityLevel = highestSev;

  return {
    camera,
    priorityLevel,
    activeAlerts: cameraActiveAlerts,
    activeAlertCount,
    highestSeverity: highestSev,
    rank: 999,
    isOfflineOrError: false,
  };
}

/**
 * Sort cameras by tactical priority order:
 * 1. Active alert severity (CRITICAL > HIGH > MEDIUM > LOW)
 * 2. Active alert count (more alerts = higher priority)
 * 3. Clear operational cameras (0 active alerts)
 * 4. Offline / Error cameras
 */
export function sortCamerasByPriority(cameras: Camera[], alerts: Alert[]): PrioritizedCamera[] {
  const prioritized = cameras.map((c) => calculateCameraPriority(c, alerts));

  prioritized.sort((a, b) => {
    // 1. Compare tier order (1: CRITICAL, 2: HIGH, 3: MEDIUM, 4: LOW, 5: CLEAR, 6: OFFLINE, 7: ERROR)
    const tierA = PRIORITY_TIER_ORDER[a.priorityLevel] ?? 99;
    const tierB = PRIORITY_TIER_ORDER[b.priorityLevel] ?? 99;

    if (tierA !== tierB) {
      return tierA - tierB;
    }

    // 2. Within the same active alert severity tier, more active alerts outrank fewer
    if (a.activeAlertCount !== b.activeAlertCount) {
      return b.activeAlertCount - a.activeAlertCount;
    }

    // 3. If same alert count, most recent active alert first
    if (a.activeAlerts.length > 0 && b.activeAlerts.length > 0) {
      const getLatestTime = (items: Alert[]) =>
        Math.max(
          ...items.map((i) => {
            const time = new Date(i.alert_timestamp || i.created_at).getTime();
            return isNaN(time) ? 0 : time;
          })
        );
      const timeA = getLatestTime(a.activeAlerts);
      const timeB = getLatestTime(b.activeAlerts);
      if (timeA !== timeB) {
        return timeB - timeA;
      }
    }

    // 4. Deterministic fallback by camera_id
    return (a.camera.camera_id || '').localeCompare(b.camera.camera_id || '');
  });

  // Assign sequential 1-based ranks
  return prioritized.map((item, index) => ({
    ...item,
    rank: index + 1,
  }));
}

/**
 * Calculate aggregate summary statistics across prioritized cameras.
 */
export function calculatePrioritySummary(
  prioritizedCameras: PrioritizedCamera[]
): PrioritySummaryCounts {
  const summary: PrioritySummaryCounts = {
    criticalCount: 0,
    highCount: 0,
    mediumCount: 0,
    lowCount: 0,
    clearCount: 0,
    offlineCount: 0,
    totalActiveAlerts: 0,
    totalCameras: prioritizedCameras.length,
  };

  for (const item of prioritizedCameras) {
    summary.totalActiveAlerts += item.activeAlertCount;
    switch (item.priorityLevel) {
      case 'CRITICAL':
        summary.criticalCount++;
        break;
      case 'HIGH':
        summary.highCount++;
        break;
      case 'MEDIUM':
        summary.mediumCount++;
        break;
      case 'LOW':
        summary.lowCount++;
        break;
      case 'CLEAR':
        summary.clearCount++;
        break;
      case 'OFFLINE':
      case 'ERROR':
        summary.offlineCount++;
        break;
    }
  }

  return summary;
}
