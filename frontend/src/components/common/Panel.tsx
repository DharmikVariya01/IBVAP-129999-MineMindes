import React from 'react';
import { cn } from '@/utils/cn';

export interface PanelProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
}

export const Panel: React.FC<PanelProps> = ({
  className,
  title,
  badge,
  actions,
  children,
  ...props
}) => {
  return (
    <section
      className={cn(
        'bg-surveillance-900/90 backdrop-blur border border-surveillance-800 rounded-md flex flex-col',
        className
      )}
      {...props}
    >
      {(title || badge || actions) && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-surveillance-800/80 bg-surveillance-850/50">
          <div className="flex items-center gap-2.5">
            {title && (
              <h2 className="text-xs font-bold uppercase tracking-wider text-surveillance-200 font-mono">
                {title}
              </h2>
            )}
            {badge}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className="p-4 flex-1">{children}</div>
    </section>
  );
};
