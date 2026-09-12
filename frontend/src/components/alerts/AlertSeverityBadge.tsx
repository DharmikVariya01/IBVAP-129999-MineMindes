import React from 'react';
import { ShieldAlert, AlertTriangle, AlertCircle, Info } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { AlertSeverity } from '@/types/api';

export interface AlertSeverityBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  severity: AlertSeverity | string;
  showIcon?: boolean;
  size?: 'sm' | 'md';
}

export const AlertSeverityBadge: React.FC<AlertSeverityBadgeProps> = ({
  severity,
  showIcon = true,
  size = 'md',
  className,
  ...props
}) => {
  const normSeverity = (severity || 'LOW').toUpperCase();

  const config: Record<
    string,
    {
      label: string;
      icon: React.ComponentType<{ className?: string }>;
      style: string;
    }
  > = {
    CRITICAL: {
      label: 'CRITICAL',
      icon: ShieldAlert,
      style: 'bg-tactical-rose/20 text-rose-300 border border-tactical-rose/50 shadow-sm',
    },
    HIGH: {
      label: 'HIGH',
      icon: AlertTriangle,
      style: 'bg-tactical-amber/20 text-amber-300 border border-tactical-amber/50',
    },
    MEDIUM: {
      label: 'MEDIUM',
      icon: AlertCircle,
      style: 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/50',
    },
    LOW: {
      label: 'LOW',
      icon: Info,
      style: 'bg-tactical-blue/20 text-blue-300 border border-tactical-blue/50',
    },
  };

  const item = config[normSeverity] || config.LOW;
  const Icon = item.icon;

  const sizeStyles = {
    sm: 'px-2 py-0.5 text-[10px] gap-1',
    md: 'px-2.5 py-1 text-xs gap-1.5 font-semibold',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center rounded font-mono uppercase tracking-wider',
        item.style,
        sizeStyles[size],
        className
      )}
      aria-label={`Severity: ${item.label}`}
      data-testid={`severity-badge-${normSeverity.toLowerCase()}`}
      {...props}
    >
      {showIcon && <Icon className={size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5'} aria-hidden="true" />}
      <span>{item.label}</span>
    </span>
  );
};
