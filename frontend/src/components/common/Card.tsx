import React from 'react';
import { cn } from '@/utils/cn';

export interface CardProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
  footer?: React.ReactNode;
}

export const Card: React.FC<CardProps> = ({
  className,
  title,
  subtitle,
  action,
  footer,
  children,
  ...props
}) => {
  return (
    <div
      className={cn(
        'bg-surveillance-900 border border-surveillance-800 rounded-lg shadow-lg overflow-hidden flex flex-col',
        className
      )}
      {...props}
    >
      {(title || subtitle || action) && (
        <div className="px-5 py-4 border-b border-surveillance-800/80 flex items-center justify-between gap-4">
          <div>
            {title && <h3 className="text-sm font-semibold text-surveillance-100 tracking-wide">{title}</h3>}
            {subtitle && <p className="text-xs text-surveillance-400 mt-0.5">{subtitle}</p>}
          </div>
          {action && <div className="flex items-center gap-2">{action}</div>}
        </div>
      )}
      <div className="p-5 flex-1">{children}</div>
      {footer && (
        <div className="px-5 py-3 bg-surveillance-950/40 border-t border-surveillance-800 text-xs text-surveillance-400">
          {footer}
        </div>
      )}
    </div>
  );
};
