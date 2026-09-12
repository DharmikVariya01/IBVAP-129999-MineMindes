import React from 'react';
import type { PrioritizedCamera } from '@/types/prioritization';
import { CameraPriorityBadge } from './CameraPriorityBadge';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { parseCoordinates } from '@/utils/coordinates';
import {
  Video,
  Bell,
  MapPin,
  Radio,
  Crosshair,
} from 'lucide-react';
import { cn } from '@/utils/cn';

export interface CameraPriorityCardProps {
  item: PrioritizedCamera;
  isSelected?: boolean;
  onSelectCamera: (cameraId: string) => void;
  onNavigateToAlerts?: (alertId: string) => void;
  onNavigateToMap?: (cameraId: string) => void;
  className?: string;
}

export const CameraPriorityCard: React.FC<CameraPriorityCardProps> = ({
  item,
  isSelected = false,
  onSelectCamera,
  onNavigateToAlerts,
  onNavigateToMap,
  className,
}) => {
  const { camera, priorityLevel, activeAlerts, activeAlertCount, rank, isOfflineOrError } = item;

  const hasCoords = Boolean(parseCoordinates(camera.location));
  const primaryAlert = activeAlerts.length > 0 ? activeAlerts[0] : null;

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelectCamera(camera.camera_id);
    }
  };

  const getStatusBadgeVariant = (status: string) => {
    switch (status.toUpperCase()) {
      case 'ONLINE':
        return 'success';
      case 'CONNECTING':
        return 'high';
      case 'OFFLINE':
      case 'ERROR':
        return 'critical';
      default:
        return 'neutral';
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelectCamera(camera.camera_id)}
      onKeyDown={handleKeyDown}
      aria-label={`Camera ${camera.name || camera.camera_id}, Rank #${rank}, Priority ${priorityLevel}, ${activeAlertCount} active alerts, Status ${camera.status}`}
      className={cn(
        'group relative p-3 rounded-lg border transition-all duration-150 cursor-pointer select-none text-left',
        'bg-surveillance-900/90 hover:bg-surveillance-850',
        isSelected
          ? 'border-tactical-emerald ring-1 ring-tactical-emerald/50 bg-surveillance-850/90 shadow-md shadow-tactical-emerald/10'
          : isOfflineOrError
          ? 'border-surveillance-800 opacity-75 hover:opacity-90'
          : priorityLevel === 'CRITICAL'
          ? 'border-tactical-rose/60 hover:border-tactical-rose shadow-sm shadow-tactical-rose/10'
          : priorityLevel === 'HIGH'
          ? 'border-tactical-amber/50 hover:border-tactical-amber'
          : 'border-surveillance-800 hover:border-surveillance-700',
        className
      )}
      data-testid={`priority-card-${camera.camera_id}`}
    >
      {/* 1. Header: Rank, Priority Badge, Status */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5 font-mono">
          <span
            className={cn(
              'px-1.5 py-0.5 rounded text-[11px] font-bold',
              rank === 1 && priorityLevel === 'CRITICAL'
                ? 'bg-tactical-rose/30 text-rose-200 border border-tactical-rose/50'
                : 'bg-surveillance-950 text-surveillance-400 border border-surveillance-800'
            )}
            title={`Priority Rank #${rank}`}
          >
            #{rank}
          </span>
          <CameraPriorityBadge level={priorityLevel} size="sm" />
        </div>

        <div className="flex items-center gap-1.5">
          <Badge variant={getStatusBadgeVariant(camera.status)} size="sm">
            {camera.status}
          </Badge>
          {isSelected && (
            <span
              className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-tactical-emerald/20 border border-tactical-emerald/40 text-[10px] font-mono font-bold text-tactical-emerald tracking-wide"
              title="Currently viewing this camera stream"
            >
              <Radio className="w-2.5 h-2.5 animate-pulse" aria-hidden="true" />
              LIVE
            </span>
          )}
        </div>
      </div>

      {/* 2. Camera Name & Code */}
      <div className="mb-2">
        <h4 className="text-xs font-bold text-surveillance-100 truncate group-hover:text-tactical-cyan transition-colors font-mono">
          {camera.name || camera.camera_id}
        </h4>
        <div className="flex items-center gap-2 text-[11px] text-surveillance-400 font-mono">
          <span className="text-tactical-emerald font-semibold">{camera.camera_id}</span>
          <span>•</span>
          <span className="truncate">{camera.location || 'Perimeter Sector'}</span>
        </div>
      </div>

      {/* 3. Tactical Alert State Summary */}
      <div className="mb-3 pt-2 border-t border-surveillance-800/80">
        {activeAlertCount > 0 ? (
          <div className="space-y-1 text-[11px] font-mono">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1 text-tactical-rose font-bold">
                <Bell className="w-3 h-3 flex-shrink-0 animate-bounce" aria-hidden="true" />
                <span>
                  {activeAlertCount} {activeAlertCount === 1 ? 'ACTIVE ALERT' : 'ACTIVE ALERTS'}
                </span>
              </span>
              {primaryAlert && (
                <span className="text-[10px] text-surveillance-400 uppercase">
                  {primaryAlert.alert_type.replace(/_/g, ' ')}
                </span>
              )}
            </div>
            {primaryAlert && (
              <p className="text-surveillance-300 text-[11px] line-clamp-1 italic">
                "{primaryAlert.message}"
              </p>
            )}
          </div>
        ) : isOfflineOrError ? (
          <div className="text-[11px] font-mono text-surveillance-500 italic">
            Unit non-operational ({camera.status}).
          </div>
        ) : (
          <div className="flex items-center gap-1 text-[11px] font-mono text-tactical-emerald">
            <span>Perimeter secured — 0 active alerts</span>
          </div>
        )}
      </div>

      {/* 4. Action Buttons */}
      <div
        className="flex items-center gap-1.5 pt-1"
        onClick={(e) => e.stopPropagation()} // Prevent card click when clicking action buttons
      >
        {/* Select Feed button */}
        <Button
          size="sm"
          variant={isSelected ? 'secondary' : 'primary'}
          onClick={() => onSelectCamera(camera.camera_id)}
          className="text-[10px] h-6 px-2 flex-1 font-mono tracking-wider uppercase"
          aria-label={`Switch live stream to camera ${camera.camera_id}`}
        >
          <Video className="w-3 h-3 mr-1" aria-hidden="true" />
          {isSelected ? 'Viewing' : 'Select'}
        </Button>

        {/* View in M20 Alert Center (if active alert with real ID exists) */}
        {primaryAlert && onNavigateToAlerts && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => onNavigateToAlerts(primaryAlert.alert_id)}
            title={`View alert ${primaryAlert.alert_id} in Alert Center (M20)`}
            aria-label={`View alert ${primaryAlert.alert_id} in Alert Center`}
            className="text-[10px] h-6 px-1.5 border-tactical-rose/40 text-tactical-rose hover:bg-tactical-rose/20"
            data-testid={`goto-alert-${camera.camera_id}`}
          >
            <Crosshair className="w-3 h-3 mr-0.5" aria-hidden="true" />
            Alerts
          </Button>
        )}

        {/* View on M21 Tactical Map (only if camera has valid coordinates) */}
        {hasCoords && onNavigateToMap && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => onNavigateToMap(camera.camera_id)}
            title={`View camera ${camera.camera_id} on Tactical Map (M21)`}
            aria-label={`View camera ${camera.camera_id} on Tactical Map`}
            className="text-[10px] h-6 px-1.5 border-surveillance-700 text-surveillance-300 hover:text-tactical-cyan hover:border-tactical-cyan/40"
            data-testid={`goto-map-${camera.camera_id}`}
          >
            <MapPin className="w-3 h-3" aria-hidden="true" />
          </Button>
        )}
      </div>
    </div>
  );
};
