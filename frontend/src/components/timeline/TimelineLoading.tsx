import React from 'react';
import { Clock } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface TimelineLoadingProps {
  message?: string;
  className?: string;
}

export const TimelineLoading: React.FC<TimelineLoadingProps> = ({
  message = 'Loading event history...',
  className,
}) => {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className={cn(
        'flex flex-col items-center justify-center p-12 bg-surveillance-900/60 border border-surveillance-800 rounded-lg space-y-4 font-mono text-center',
        className
      )}
      data-testid="timeline-loading-state"
    >
      <div className="relative flex items-center justify-center">
        <div className="w-12 h-12 rounded-full border-2 border-tactical-emerald/20 border-t-tactical-emerald animate-spin" />
        <Clock className="w-5 h-5 text-tactical-emerald absolute" aria-hidden="true" />
      </div>
      <div>
        <p className="text-sm font-semibold text-surveillance-100 tracking-wider uppercase">
          {message}
        </p>
        <p className="text-xs text-surveillance-400 mt-1">
          Querying persistent M16 event ledger...
        </p>
      </div>
      {/* Visual skeleton pulses resembling timeline nodes */}
      <div className="w-full max-w-md pt-4 space-y-3 opacity-40">
        <div className="flex items-center gap-3">
          <div className="w-4 h-4 rounded-full bg-surveillance-700 animate-pulse" />
          <div className="flex-1 h-3 rounded bg-surveillance-800 animate-pulse" />
          <div className="w-16 h-3 rounded bg-surveillance-800 animate-pulse" />
        </div>
        <div className="flex items-center gap-3 pl-4">
          <div className="w-3 h-3 rounded-full bg-surveillance-700 animate-pulse" />
          <div className="w-2/3 h-3 rounded bg-surveillance-800 animate-pulse" />
        </div>
      </div>
    </div>
  );
};
