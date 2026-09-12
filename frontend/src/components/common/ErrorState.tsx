import React from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';
import { Button } from './Button';
import { cn } from '@/utils/cn';

export interface ErrorStateProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string;
  message?: string;
  onRetry?: () => void;
  retryLabel?: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'Service Unavailable',
  message = 'Unable to communicate with the surveillance platform. Please verify connection.',
  onRetry,
  retryLabel = 'Retry Connection',
  className,
  ...props
}) => {
  return (
    <div
      role="alert"
      className={cn(
        'bg-tactical-rose/10 border border-tactical-rose/30 rounded-lg p-6 flex flex-col items-center justify-center text-center max-w-md mx-auto',
        className
      )}
      {...props}
    >
      <div className="h-10 w-10 rounded-full bg-tactical-rose/20 text-tactical-rose flex items-center justify-center mb-3">
        <AlertTriangle className="h-5 w-5" aria-hidden="true" />
      </div>
      <h3 className="text-sm font-semibold text-rose-200 tracking-wide mb-1">{title}</h3>
      <p className="text-xs text-surveillance-300 mb-4">{message}</p>
      {onRetry && (
        <Button variant="danger" size="sm" onClick={onRetry}>
          <RotateCcw className="h-3.5 w-3.5 mr-1" aria-hidden="true" />
          {retryLabel}
        </Button>
      )}
    </div>
  );
};
