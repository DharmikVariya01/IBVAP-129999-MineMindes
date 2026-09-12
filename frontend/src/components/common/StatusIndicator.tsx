import React from 'react';
import { cn } from '@/utils/cn';

export type StatusType = 'online' | 'offline' | 'connecting' | 'error';

export interface StatusIndicatorProps extends React.HTMLAttributes<HTMLDivElement> {
  status: StatusType;
  label?: string;
  pulse?: boolean;
}

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({
  status,
  label,
  pulse = true,
  className,
  ...props
}) => {
  const dotColors: Record<StatusType, string> = {
    online: 'bg-tactical-emerald shadow-[0_0_8px_rgba(16,185,129,0.6)]',
    offline: 'bg-surveillance-500',
    connecting: 'bg-tactical-amber shadow-[0_0_8px_rgba(245,158,11,0.6)]',
    error: 'bg-tactical-rose shadow-[0_0_8px_rgba(244,63,94,0.6)]',
  };

  const pingColors: Record<StatusType, string> = {
    online: 'bg-emerald-400',
    offline: 'hidden',
    connecting: 'bg-amber-400',
    error: 'bg-rose-400',
  };

  const defaultLabels: Record<StatusType, string> = {
    online: 'Online',
    offline: 'Offline',
    connecting: 'Connecting',
    error: 'Error',
  };

  const displayLabel = label ?? defaultLabels[status];

  return (
    <div
      role="status"
      aria-label={`Status: ${displayLabel}`}
      className={cn('inline-flex items-center gap-2 text-xs font-mono', className)}
      {...props}
    >
      <span className="relative flex h-2.5 w-2.5">
        {pulse && status !== 'offline' && (
          <span
            className={cn(
              'animate-ping absolute inline-flex h-full w-full rounded-full opacity-75',
              pingColors[status]
            )}
          />
        )}
        <span className={cn('relative inline-flex rounded-full h-2.5 w-2.5', dotColors[status])} />
      </span>
      {displayLabel && <span className="text-surveillance-300 capitalize">{displayLabel}</span>}
    </div>
  );
};
