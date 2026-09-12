import React from 'react';
import type { CameraStreamStatus } from '@/types/websocket';
import { Badge, type BadgeProps } from '@/components/common/Badge';
import { cn } from '@/utils/cn';

export interface CameraStatusProps {
  status: CameraStreamStatus | null;
  details?: string | null;
  className?: string;
}

export const CameraStatus: React.FC<CameraStatusProps> = ({
  status,
  details,
  className,
}) => {
  const getBadgeVariant = (s: CameraStreamStatus | null): NonNullable<BadgeProps['variant']> => {
    if (!s) return 'neutral';
    switch (s) {
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

  const displayStatus = status || 'UNKNOWN';

  return (
    <div
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-1 bg-surveillance-900 border border-surveillance-800 rounded text-xs font-mono',
        className
      )}
      title={details || `Camera hardware is ${displayStatus}`}
      data-testid="camera-status-indicator"
    >
      <span className="text-surveillance-400 text-[11px] uppercase tracking-wider">
        Camera:
      </span>
      <Badge variant={getBadgeVariant(status)} size="sm">
        {displayStatus}
      </Badge>
    </div>
  );
};
