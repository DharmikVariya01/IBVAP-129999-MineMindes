import React from 'react';
import { BarChart2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/common/Button';

export interface AnalyticsEmptyProps {
  onRefresh?: () => void;
  isRefreshing?: boolean;
}

export const AnalyticsEmpty: React.FC<AnalyticsEmptyProps> = ({
  onRefresh,
  isRefreshing = false,
}) => {
  return (
    <div
      data-testid="analytics-empty"
      className="bg-surveillance-900 border border-surveillance-800 rounded-lg p-8 sm:p-12 text-center max-w-lg mx-auto my-12 shadow-xl"
    >
      <div className="w-14 h-14 rounded-full bg-surveillance-800 border border-surveillance-700 flex items-center justify-center mx-auto mb-4 text-surveillance-400">
        <BarChart2 className="w-7 h-7" aria-hidden="true" />
      </div>

      <h3 className="text-base font-bold font-mono text-surveillance-200 tracking-wide">
        No statistics available.
      </h3>

      <p className="text-xs text-surveillance-400 mt-1.5 mb-6 max-w-sm mx-auto">
        The platform has not yet registered any cameras, tracks, alerts, or pipeline events, or the backend returned an empty response.
      </p>

      {onRefresh && (
        <Button
          variant="secondary"
          size="sm"
          onClick={onRefresh}
          disabled={isRefreshing}
          className="inline-flex items-center gap-2"
          aria-label="Refresh statistics"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} aria-hidden="true" />
          <span>{isRefreshing ? 'Refreshing...' : 'Refresh'}</span>
        </Button>
      )}
    </div>
  );
};
