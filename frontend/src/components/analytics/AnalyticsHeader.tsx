import React from 'react';
import { BarChart3, RefreshCw, Clock } from 'lucide-react';
import { Button } from '@/components/common/Button';

export interface AnalyticsHeaderProps {
  lastUpdated: Date | null;
  onRefresh: () => void;
  isRefreshing: boolean;
}

export const AnalyticsHeader: React.FC<AnalyticsHeaderProps> = ({
  lastUpdated,
  onRefresh,
  isRefreshing,
}) => {
  const formatTime = (date: Date | null): string => {
    if (!date) return '--:--:--';
    return date.toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  };

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-surveillance-800">
      <div>
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-tactical-cyan/10 border border-tactical-cyan/20 text-tactical-cyan">
            <BarChart3 className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl sm:text-2xl font-bold font-mono tracking-wide text-surveillance-100">
                TACTICAL STATISTICS &amp; ANALYTICS
              </h1>
              <span className="hidden sm:inline-block px-2 py-0.5 text-[10px] font-mono uppercase bg-tactical-cyan/10 text-tactical-cyan border border-tactical-cyan/30 rounded">
                M23 CONSOLE
              </span>
            </div>
            <p className="text-xs text-surveillance-400 mt-0.5">
              Live aggregate operational metrics computed from M16 REST backend
            </p>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {lastUpdated && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-surveillance-900 border border-surveillance-800 text-[11px] font-mono text-surveillance-400">
            <Clock className="w-3.5 h-3.5 text-surveillance-500" aria-hidden="true" />
            <span>UPDATED:</span>
            <span className="text-surveillance-200">{formatTime(lastUpdated)}</span>
          </div>
        )}

        <Button
          variant="secondary"
          size="sm"
          onClick={onRefresh}
          disabled={isRefreshing}
          aria-label={isRefreshing ? 'Refreshing statistics' : 'Refresh statistics'}
          className="flex items-center gap-1.5 border-surveillance-700 hover:border-surveillance-600 bg-surveillance-850 hover:bg-surveillance-800 text-surveillance-200"
        >
          <RefreshCw
            className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-tactical-cyan' : ''}`}
            aria-hidden="true"
          />
          <span>{isRefreshing ? 'Refreshing...' : 'Refresh'}</span>
        </Button>
      </div>
    </div>
  );
};
