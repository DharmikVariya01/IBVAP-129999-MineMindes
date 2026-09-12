import React from 'react';
import { cn } from '@/utils/cn';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'critical' | 'high' | 'medium' | 'low' | 'success' | 'info' | 'neutral';
  size?: 'sm' | 'md';
}

export const Badge: React.FC<BadgeProps> = ({
  className,
  variant = 'neutral',
  size = 'md',
  children,
  ...props
}) => {
  const variants = {
    critical: 'bg-tactical-rose/20 text-rose-300 border border-tactical-rose/40',
    high: 'bg-tactical-amber/20 text-amber-300 border border-tactical-amber/40',
    medium: 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/40',
    low: 'bg-tactical-blue/20 text-blue-300 border border-tactical-blue/40',
    success: 'bg-tactical-emerald/20 text-emerald-300 border border-tactical-emerald/40',
    info: 'bg-tactical-cyan/20 text-cyan-300 border border-tactical-cyan/40',
    neutral: 'bg-surveillance-800 text-surveillance-300 border border-surveillance-700',
  };

  const sizes = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-2.5 py-1 text-xs font-semibold',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-mono uppercase tracking-wider',
        variants[variant],
        sizes[size],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
};
