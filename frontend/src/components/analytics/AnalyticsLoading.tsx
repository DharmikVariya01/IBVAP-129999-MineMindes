import React from 'react';
import { Loader2 } from 'lucide-react';

export const AnalyticsLoading: React.FC = () => {
  return (
    <div
      data-testid="analytics-loading"
      role="status"
      aria-live="polite"
      className="flex flex-col items-center justify-center min-h-[400px] p-8 text-center"
    >
      <div className="relative mb-4">
        <div className="w-16 h-16 rounded-full border-2 border-tactical-cyan/20 animate-ping absolute inset-0" />
        <div className="w-16 h-16 rounded-full border-2 border-t-tactical-cyan border-r-transparent border-b-tactical-cyan/30 border-l-transparent animate-spin flex items-center justify-center bg-surveillance-900 shadow-xl">
          <Loader2 className="w-6 h-6 text-tactical-cyan animate-pulse" aria-hidden="true" />
        </div>
      </div>
      <h3 className="text-base font-semibold font-mono text-surveillance-100 tracking-wide">
        Loading statistics...
      </h3>
      <p className="text-xs text-surveillance-400 mt-1 max-w-sm">
        Querying M16 REST backend for aggregate operational metrics and sensor distributions.
      </p>
    </div>
  );
};
