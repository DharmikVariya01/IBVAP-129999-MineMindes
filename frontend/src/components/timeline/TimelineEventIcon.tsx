import React from 'react';
import {
  ShieldAlert,
  Clock,
  Layers,
  Activity,
  Bell,
  CircleDot,
  Eye,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import type { TimelineFilterCategory } from '@/types/timeline';

export interface TimelineEventIconProps {
  category: TimelineFilterCategory;
  eventType?: string;
  isFirst?: boolean;
  className?: string;
}

export const TimelineEventIcon: React.FC<TimelineEventIconProps> = ({
  category,
  eventType,
  isFirst = false,
  className,
}) => {
  const upperType = (eventType || '').toUpperCase();

  // Pick tactical icon and color tokens based on normalized category
  switch (category) {
    case 'BREACH':
      return (
        <div
          className={cn(
            'flex items-center justify-center w-7 h-7 rounded-full border shadow-sm',
            'bg-tactical-rose/20 text-tactical-rose border-tactical-rose/60 ring-2 ring-tactical-rose/20',
            isFirst && 'animate-pulse',
            className
          )}
          aria-label={`Critical Fence Breach Icon: ${upperType}`}
          data-testid="timeline-icon-breach"
        >
          <ShieldAlert className="w-4 h-4" aria-hidden="true" />
        </div>
      );

    case 'LOITERING':
      return (
        <div
          className={cn(
            'flex items-center justify-center w-7 h-7 rounded-full border shadow-sm',
            'bg-tactical-amber/20 text-tactical-amber border-tactical-amber/60 ring-2 ring-tactical-amber/20',
            isFirst && 'animate-pulse',
            className
          )}
          aria-label={`Loitering Event Icon: ${upperType}`}
          data-testid="timeline-icon-loitering"
        >
          <Clock className="w-4 h-4" aria-hidden="true" />
        </div>
      );

    case 'ZONE':
      return (
        <div
          className={cn(
            'flex items-center justify-center w-7 h-7 rounded-full border shadow-sm',
            'bg-tactical-cyan/20 text-tactical-cyan border-tactical-cyan/60 ring-2 ring-tactical-cyan/20',
            className
          )}
          aria-label={`Zone Event Icon: ${upperType}`}
          data-testid="timeline-icon-zone"
        >
          <Layers className="w-4 h-4" aria-hidden="true" />
        </div>
      );

    case 'MOVEMENT':
      return (
        <div
          className={cn(
            'flex items-center justify-center w-7 h-7 rounded-full border shadow-sm',
            'bg-tactical-emerald/20 text-tactical-emerald border-tactical-emerald/60 ring-2 ring-tactical-emerald/20',
            className
          )}
          aria-label={`Movement Tracking Icon: ${upperType}`}
          data-testid="timeline-icon-movement"
        >
          <Activity className="w-4 h-4" aria-hidden="true" />
        </div>
      );

    case 'ALERTS':
      return (
        <div
          className={cn(
            'flex items-center justify-center w-7 h-7 rounded-full border shadow-sm',
            'bg-tactical-rose/20 text-tactical-rose border-tactical-rose/60 ring-2 ring-tactical-rose/20',
            className
          )}
          aria-label={`Alert Trigger Icon: ${upperType}`}
          data-testid="timeline-icon-alerts"
        >
          <Bell className="w-4 h-4" aria-hidden="true" />
        </div>
      );

    case 'ALL':
    case 'OTHER':
    default:
      if (upperType.includes('CREATE') || upperType.includes('FIRST')) {
        return (
          <div
            className={cn(
              'flex items-center justify-center w-7 h-7 rounded-full border shadow-sm',
              'bg-blue-500/20 text-blue-400 border-blue-500/60 ring-2 ring-blue-500/20',
              className
            )}
            aria-label={`Observation Init Icon: ${upperType}`}
            data-testid="timeline-icon-init"
          >
            <Eye className="w-4 h-4" aria-hidden="true" />
          </div>
        );
      }

      return (
        <div
          className={cn(
            'flex items-center justify-center w-7 h-7 rounded-full border shadow-sm',
            'bg-surveillance-800 text-surveillance-300 border-surveillance-700',
            className
          )}
          aria-label={`Pipeline Event Icon: ${upperType || 'UNKNOWN'}`}
          data-testid="timeline-icon-default"
        >
          <CircleDot className="w-3.5 h-3.5" aria-hidden="true" />
        </div>
      );
  }
};
