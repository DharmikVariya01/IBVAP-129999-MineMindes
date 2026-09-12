import React, { useEffect } from 'react';
import { AlertSeverityBadge } from './AlertSeverityBadge';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import {
  X,
  Camera,
  Crosshair,
  Clock,
  ShieldAlert,
  UserCheck,
  CheckCircle2,
  Calendar,
  Layers,
  Activity,
} from 'lucide-react';
import type { Alert } from '@/types/api';

export interface AlertDetailProps {
  alert: Alert | null;
  isOpen: boolean;
  onClose: () => void;
  onAcknowledge?: (alertId: string) => void;
  isAcknowledging?: boolean;
  cameraName?: string;
}

export const AlertDetail: React.FC<AlertDetailProps> = ({
  alert,
  isOpen,
  onClose,
  onAcknowledge,
  isAcknowledging = false,
  cameraName,
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !alert) return null;

  const isUnacknowledged = alert.status === 'ACTIVE';
  const isAcknowledged = alert.status === 'ACKNOWLEDGED';
  const isResolved = alert.status === 'RESOLVED';

  const cameraDisplay =
    cameraName ||
    (alert.alert_metadata?.camera_code as string) ||
    (alert.camera_id ? `CAM-${alert.camera_id}` : 'CAM_UNKNOWN');

  const formattedType = (alert.alert_type || 'ALERT').replace(/_/g, ' ');

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="alert-detail-title"
      onClick={handleBackdropClick}
      className="fixed inset-0 z-50 flex items-center justify-center sm:justify-end bg-black/70 backdrop-blur-sm p-4 sm:p-0 transition-opacity"
      data-testid="alert-detail-modal"
    >
      <div
        className="w-full sm:max-w-xl h-full sm:max-h-screen bg-surveillance-900 border-l border-surveillance-800 shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-right duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-4 sm:p-5 border-b border-surveillance-800 flex items-center justify-between bg-surveillance-950/80">
          <div className="flex items-center gap-2.5">
            <ShieldAlert className="w-5 h-5 text-tactical-rose" aria-hidden="true" />
            <div>
              <div className="flex items-center gap-2">
                <h2 id="alert-detail-title" className="text-sm font-bold tracking-wider text-surveillance-100 uppercase font-mono">
                  {alert.alert_id}
                </h2>
                <AlertSeverityBadge severity={alert.severity} size="sm" />
              </div>
              <p className="text-xs text-surveillance-400 font-mono mt-0.5">
                {formattedType} • Security Event Detail
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close alert details"
            className="p-1.5 text-surveillance-400 hover:text-white bg-surveillance-800/80 hover:bg-surveillance-800 rounded transition-colors focus:outline-none focus:ring-2 focus:ring-tactical-emerald"
            data-testid="alert-detail-close-btn"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6 text-xs font-mono">
          {/* 1. Primary Message Box */}
          <div className="bg-surveillance-950 border border-surveillance-800 rounded-lg p-4 space-y-2">
            <span className="text-[10px] text-surveillance-400 font-semibold tracking-wider uppercase">
              Incident Message
            </span>
            <p className="text-sm text-surveillance-100 font-sans leading-relaxed">
              {alert.message}
            </p>
          </div>

          {/* 2. Core Operational Telemetry Grid */}
          <div className="space-y-3">
            <span className="text-[10px] text-surveillance-400 font-semibold tracking-wider uppercase flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-tactical-emerald" />
              Telemetry & Spatial Assignment
            </span>

            <div className="grid grid-cols-2 gap-3">
              <div className="bg-surveillance-950/60 border border-surveillance-850 rounded p-3">
                <div className="flex items-center gap-1.5 text-surveillance-400 mb-1">
                  <Camera className="w-3 h-3 text-surveillance-500" />
                  <span className="text-[10px] uppercase">Camera</span>
                </div>
                <div className="text-surveillance-100 font-bold">{cameraDisplay}</div>
                {alert.camera_id && (
                  <div className="text-[10px] text-surveillance-500 mt-0.5">DB ID: #{alert.camera_id}</div>
                )}
              </div>

              <div className="bg-surveillance-950/60 border border-surveillance-850 rounded p-3">
                <div className="flex items-center gap-1.5 text-surveillance-400 mb-1">
                  <Crosshair className="w-3 h-3 text-tactical-cyan" />
                  <span className="text-[10px] uppercase">Track Target</span>
                </div>
                <div className="text-surveillance-100 font-bold">
                  {alert.track_id !== null && alert.track_id !== undefined ? `#${alert.track_id}` : 'None'}
                </div>
                {alert.event_id && (
                  <div className="text-[10px] text-surveillance-500 mt-0.5">Event: #{alert.event_id}</div>
                )}
              </div>

              <div className="bg-surveillance-950/60 border border-surveillance-850 rounded p-3">
                <div className="flex items-center gap-1.5 text-surveillance-400 mb-1">
                  <Layers className="w-3 h-3 text-surveillance-500" />
                  <span className="text-[10px] uppercase">Zone Assignment</span>
                </div>
                <div className="text-surveillance-100 font-bold">
                  {alert.zone_id ? `Zone #${alert.zone_id}` : 'Perimeter'}
                </div>
              </div>

              <div className="bg-surveillance-950/60 border border-surveillance-850 rounded p-3">
                <div className="flex items-center gap-1.5 text-surveillance-400 mb-1">
                  <CheckCircle2 className="w-3 h-3 text-surveillance-500" />
                  <span className="text-[10px] uppercase">Lifecycle Status</span>
                </div>
                <div className="mt-0.5">
                  {isUnacknowledged && (
                    <Badge variant="critical" size="sm">
                      ACTIVE (UNACK)
                    </Badge>
                  )}
                  {isAcknowledged && (
                    <Badge variant="info" size="sm">
                      ACKNOWLEDGED
                    </Badge>
                  )}
                  {isResolved && (
                    <Badge variant="success" size="sm">
                      RESOLVED
                    </Badge>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* 3. Timestamps & Audit Section */}
          <div className="space-y-3">
            <span className="text-[10px] text-surveillance-400 font-semibold tracking-wider uppercase flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-tactical-amber" />
              Event Timing & Audit Trail
            </span>

            <div className="bg-surveillance-950/60 border border-surveillance-850 rounded divide-y divide-surveillance-850 text-[11px]">
              <div className="p-2.5 flex items-center justify-between">
                <span className="text-surveillance-400 flex items-center gap-1.5">
                  <Calendar className="w-3 h-3" />
                  Alert Triggered (UTC)
                </span>
                <span className="text-surveillance-200 font-mono">{alert.alert_timestamp}</span>
              </div>

              {alert.acknowledged_at && (
                <div className="p-2.5 flex items-center justify-between">
                  <span className="text-surveillance-400 flex items-center gap-1.5">
                    <UserCheck className="w-3 h-3 text-tactical-cyan" />
                    Acknowledged By
                  </span>
                  <span className="text-surveillance-200">
                    {alert.acknowledged_by || 'Unknown'} ({alert.acknowledged_at})
                  </span>
                </div>
              )}

              {alert.resolved_at && (
                <div className="p-2.5 flex items-center justify-between">
                  <span className="text-surveillance-400 flex items-center gap-1.5">
                    <CheckCircle2 className="w-3 h-3 text-tactical-emerald" />
                    Resolved By
                  </span>
                  <span className="text-surveillance-200">
                    {alert.resolved_by || 'Unknown'} ({alert.resolved_at})
                  </span>
                </div>
              )}

              <div className="p-2.5 flex items-center justify-between text-surveillance-500 text-[10px]">
                <span>Record Created / Updated</span>
                <span>{alert.created_at}</span>
              </div>
            </div>
          </div>

          {/* 4. Telemetry Context Metadata */}
          {alert.alert_metadata && Object.keys(alert.alert_metadata).length > 0 && (
            <div className="space-y-2">
              <span className="text-[10px] text-surveillance-400 font-semibold tracking-wider uppercase">
                Contextual Metadata (M10 Telemetry)
              </span>
              <pre className="p-3 bg-surveillance-950 border border-surveillance-800 rounded text-[10px] text-surveillance-300 overflow-x-auto font-mono">
                {JSON.stringify(alert.alert_metadata, null, 2)}
              </pre>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="p-4 border-t border-surveillance-800 bg-surveillance-950/90 flex items-center justify-between gap-3">
          <Button variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>

          {isUnacknowledged && onAcknowledge && (
            <Button
              variant="primary"
              size="sm"
              isLoading={isAcknowledging}
              disabled={isAcknowledging}
              onClick={() => onAcknowledge(alert.alert_id)}
              className="bg-tactical-amber hover:bg-amber-400 text-surveillance-950 font-bold font-mono"
              data-testid="detail-acknowledge-btn"
            >
              <UserCheck className="w-4 h-4 mr-1.5" />
              ACKNOWLEDGE ALERT
            </Button>
          )}

          {isAcknowledged && (
            <div className="text-[11px] font-mono text-tactical-cyan flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4" />
              <span>Acknowledged by {alert.acknowledged_by || 'Operator'}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
