import React from 'react';
import { AlertSeverityBadge } from './AlertSeverityBadge';
import { Button } from '@/components/common/Button';
import { Badge } from '@/components/common/Badge';
import { Camera, CheckCircle2, Clock, Crosshair, ChevronRight } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { Alert } from '@/types/api';

export interface AlertCardProps {
  alert: Alert;
  isNew?: boolean;
  isAcknowledging?: boolean;
  onAcknowledge?: (alertId: string) => void;
  onSelect?: (alert: Alert) => void;
  onViewTimeline?: (trackId: number | string) => void;
  onSelectCamera?: (cameraId: string) => void;
  cameraName?: string;
}

export function formatRelativeTime(dateString: string): string {
  try {
    const timestamp = new Date(dateString).getTime();
    if (isNaN(timestamp)) return dateString;

    const diffSeconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
    if (diffSeconds < 10) return 'just now';
    if (diffSeconds < 60) return `${diffSeconds}s ago`;

    const diffMinutes = Math.floor(diffSeconds / 60);
    if (diffMinutes < 60) return `${diffMinutes}m ago`;

    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours}h ago`;

    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  } catch {
    return dateString;
  }
}

export const AlertCard: React.FC<AlertCardProps> = ({
  alert,
  isNew = false,
  isAcknowledging = false,
  onAcknowledge,
  onSelect,
  onViewTimeline,
  onSelectCamera,
  cameraName,
}) => {
  const isUnacknowledged = alert.status === 'ACTIVE';
  const isAcknowledged = alert.status === 'ACKNOWLEDGED';
  const isResolved = alert.status === 'RESOLVED';

  const cameraDisplay =
    cameraName ||
    (alert.alert_metadata?.camera_code as string) ||
    (alert.camera_id ? `CAM-${alert.camera_id}` : 'CAM_UNKNOWN');

  const formattedType = (alert.alert_type || 'ALERT').replace(/_/g, ' ');

  const handleAcknowledgeClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isUnacknowledged && onAcknowledge && !isAcknowledging) {
      onAcknowledge(alert.alert_id);
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect?.(alert)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect?.(alert);
        }
      }}
      className={cn(
        'group relative bg-surveillance-900 border rounded-lg p-4 transition-all duration-200 cursor-pointer text-left focus:outline-none focus:ring-2 focus:ring-tactical-emerald/60',
        isUnacknowledged
          ? 'border-tactical-rose/40 hover:border-tactical-rose/80 shadow-md bg-surveillance-900/95'
          : 'border-surveillance-800 hover:border-surveillance-700 bg-surveillance-900/80',
        isNew && 'ring-1 ring-tactical-rose/50 animate-pulse-subtle'
      )}
      data-testid={`alert-card-${alert.alert_id}`}
      aria-label={`Alert ${alert.alert_id}: ${alert.severity} ${formattedType}`}
    >
      {/* Top Header Row: Severity, Type, New Indicator, Relative Time */}
      <div className="flex items-center justify-between gap-2 mb-2.5">
        <div className="flex items-center gap-2 flex-wrap">
          <AlertSeverityBadge severity={alert.severity} size="sm" />
          <span className="text-xs font-semibold text-surveillance-100 uppercase tracking-wide font-mono">
            {formattedType}
          </span>
          {isNew && (
            <span
              className="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-tactical-rose text-white uppercase tracking-wider animate-pulse"
              data-testid="new-alert-badge"
            >
              NEW
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5 text-[11px] font-mono text-surveillance-400">
          <Clock className="w-3.5 h-3.5 text-surveillance-500" aria-hidden="true" />
          <span>{formatRelativeTime(alert.alert_timestamp)}</span>
        </div>
      </div>

      {/* Alert Message */}
      <p className="text-xs font-medium text-surveillance-200 line-clamp-2 mb-3 leading-relaxed">
        {alert.message}
      </p>

      {/* Metadata Row: Camera, Track ID, Status, and Action */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-surveillance-800/80 text-[11px] font-mono">
        <div className="flex items-center gap-3 text-surveillance-400">
          {onSelectCamera ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                const targetCam = (alert.alert_metadata?.camera_code as string) || (alert.camera_id ? String(alert.camera_id) : 'CAM_01');
                onSelectCamera(targetCam);
              }}
              className="flex items-center gap-1 hover:text-tactical-emerald underline decoration-tactical-emerald/40 hover:decoration-tactical-emerald transition-colors"
              title={`Switch CCTV to ${cameraDisplay}`}
              data-testid={`alert-camera-link-${alert.alert_id}`}
            >
              <Camera className="w-3 h-3 text-tactical-emerald" aria-hidden="true" />
              <span className="text-surveillance-300 font-semibold">{cameraDisplay}</span>
            </button>
          ) : (
            <div className="flex items-center gap-1">
              <Camera className="w-3 h-3 text-surveillance-500" aria-hidden="true" />
              <span className="text-surveillance-300 font-semibold">{cameraDisplay}</span>
            </div>
          )}

          {alert.track_id !== null && alert.track_id !== undefined && (
            onViewTimeline ? (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onViewTimeline(alert.track_id!);
                }}
                className="flex items-center gap-1 hover:text-tactical-cyan underline decoration-tactical-cyan/40 hover:decoration-tactical-cyan transition-colors"
                title={`Inspect track #${alert.track_id} timeline`}
                aria-label={`Inspect event timeline for track ${alert.track_id}`}
                data-testid={`alert-track-link-${alert.alert_id}`}
              >
                <Crosshair className="w-3 h-3 text-tactical-cyan" aria-hidden="true" />
                <span>Track: #{alert.track_id}</span>
              </button>
            ) : (
              <div className="flex items-center gap-1">
                <Crosshair className="w-3 h-3 text-tactical-cyan" aria-hidden="true" />
                <span>Track: #{alert.track_id}</span>
              </div>
            )
          )}

          <span className="text-surveillance-600">•</span>
          <span className="text-surveillance-500">{alert.alert_id}</span>
        </div>

        <div className="flex items-center gap-2">
          {/* Status Badge */}
          {isAcknowledged && (
            <Badge variant="info" size="sm" className="gap-1">
              <CheckCircle2 className="w-3 h-3" aria-hidden="true" />
              ACKNOWLEDGED
            </Badge>
          )}

          {isResolved && (
            <Badge variant="success" size="sm">
              RESOLVED
            </Badge>
          )}

          {/* Acknowledge Button */}
          {isUnacknowledged && (
            <Button
              variant="secondary"
              size="sm"
              isLoading={isAcknowledging}
              disabled={isAcknowledging}
              onClick={handleAcknowledgeClick}
              className="text-[11px] px-2.5 py-1 bg-tactical-amber/10 text-amber-300 hover:bg-tactical-amber/20 border-tactical-amber/40 focus:ring-tactical-amber font-mono tracking-wider font-semibold"
              aria-label={`Acknowledge alert ${alert.alert_id}`}
              data-testid={`acknowledge-btn-${alert.alert_id}`}
            >
              ACKNOWLEDGE
            </Button>
          )}

          <ChevronRight className="w-4 h-4 text-surveillance-500 group-hover:text-surveillance-300 transition-colors" />
        </div>
      </div>
    </div>
  );
};
