import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/common/Button';

export interface AnalyticsErrorProps {
  message?: string;
  onRetry: () => void;
  isRetrying?: boolean;
}

export const AnalyticsError: React.FC<AnalyticsErrorProps> = ({
  message = 'Unable to load statistics.',
  onRetry,
  isRetrying = false,
}) => {
  return (
    <div
      data-testid="analytics-error"
      role="alert"
      className="bg-tactical-rose/10 border border-tactical-rose/40 rounded-lg p-6 sm:p-8 text-center max-w-xl mx-auto my-8 shadow-xl"
    >
      <div className="w-12 h-12 rounded-full bg-tactical-rose/20 border border-tactical-rose/40 flex items-center justify-center mx-auto mb-3 text-tactical-rose">
        <AlertTriangle className="w-6 h-6" aria-hidden="true" />
      </div>

      <h3 className="text-base font-bold font-mono text-rose-200 tracking-wide">
        Unable to load statistics.
      </h3>

      <p className="text-xs text-rose-300/80 mt-1.5 mb-5 font-mono">
        {message}
      </p>

      <Button
        variant="danger"
        size="sm"
        onClick={onRetry}
        disabled={isRetrying}
        className="inline-flex items-center gap-2"
        aria-label="Retry loading statistics"
      >
        <RefreshCw className={`w-4 h-4 ${isRetrying ? 'animate-spin' : ''}`} aria-hidden="true" />
        <span>{isRetrying ? 'Retrying...' : 'Retry'}</span>
      </Button>
    </div>
  );
};
