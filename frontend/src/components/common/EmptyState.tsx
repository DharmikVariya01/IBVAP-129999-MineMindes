import React from 'react';
import { Inbox } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface EmptyStateProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string;
  message?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = 'No Records Found',
  message = 'There are no active entries or telemetry to display at this time.',
  icon,
  action,
  className,
  ...props
}) => {
  return (
    <div
      className={cn(
        'border border-dashed border-surveillance-800 rounded-lg p-8 flex flex-col items-center justify-center text-center max-w-sm mx-auto my-4',
        className
      )}
      {...props}
    >
      <div className="h-10 w-10 rounded-full bg-surveillance-800/80 text-surveillance-400 flex items-center justify-center mb-3">
        {icon || <Inbox className="h-5 w-5" aria-hidden="true" />}
      </div>
      <h3 className="text-sm font-medium text-surveillance-200 tracking-wide mb-1">{title}</h3>
      <p className="text-xs text-surveillance-400 max-w-xs mb-3">{message}</p>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
};
