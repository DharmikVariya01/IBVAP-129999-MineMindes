import React from 'react';
import { cn } from '@/utils/cn';

export interface LoadingStateProps extends React.HTMLAttributes<HTMLDivElement> {
  message?: string;
  size?: 'sm' | 'md' | 'lg';
}

export const LoadingState: React.FC<LoadingStateProps> = ({
  message = 'Loading surveillance data...',
  size = 'md',
  className,
  ...props
}) => {
  const spinnerSizes = {
    sm: 'h-4 w-4 border-2',
    md: 'h-8 w-8 border-2',
    lg: 'h-12 w-12 border-3',
  };

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn('flex flex-col items-center justify-center p-8 gap-3 text-center', className)}
      {...props}
    >
      <div
        className={cn(
          'animate-spin rounded-full border-tactical-cyan/20 border-t-tactical-cyan',
          spinnerSizes[size]
        )}
      />
      <span className="text-xs font-mono text-surveillance-400 tracking-wide">{message}</span>
    </div>
  );
};
