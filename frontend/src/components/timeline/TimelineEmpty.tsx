import React from 'react';
import { CalendarX, RefreshCw, FilterX } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { cn } from '@/utils/cn';

export interface TimelineEmptyProps {
  message?: string;
  isFiltered?: boolean;
  onClearFilters?: () => void;
  onRefresh?: () => void;
  className?: string;
}

export const TimelineEmpty: React.FC<TimelineEmptyProps> = ({
  message = 'No events recorded for this track.',
  isFiltered = false,
  onClearFilters,
  onRefresh,
  className,
}) => {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'flex flex-col items-center justify-center p-12 bg-surveillance-900/40 border border-dashed border-surveillance-800 rounded-lg text-center font-mono space-y-3',
        className
      )}
      data-testid="timeline-empty-state"
    >
      <div className="p-3 bg-surveillance-800/60 rounded-full text-surveillance-400 border border-surveillance-700">
        {isFiltered ? (
          <FilterX className="w-6 h-6 text-tactical-amber" aria-hidden="true" />
        ) : (
          <CalendarX className="w-6 h-6 text-surveillance-400" aria-hidden="true" />
        )}
      </div>

      <div>
        <h3 className="text-sm font-bold text-surveillance-200 uppercase tracking-wider">
          {message}
        </h3>
        <p className="text-xs text-surveillance-400 mt-1 max-w-sm">
          {isFiltered
            ? 'No events match the active category filter for this tracked target.'
            : 'This target has been registered by ByteTrack, but no pipeline events (breach, loitering, zone transitions) have been recorded yet.'}
        </p>
      </div>

      <div className="flex items-center gap-2 pt-2">
        {isFiltered && onClearFilters && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onClearFilters}
            className="text-xs font-mono"
            aria-label="Clear active event filters"
            data-testid="timeline-clear-filters-btn"
          >
            Clear Filters
          </Button>
        )}

        {onRefresh && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onRefresh}
            className="text-xs font-mono"
            aria-label="Refresh track events"
            data-testid="timeline-refresh-empty-btn"
          >
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" aria-hidden="true" />
            Check Again
          </Button>
        )}
      </div>
    </div>
  );
};
