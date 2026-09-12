import React from 'react';
import { LucideIcon, ArrowUpRight } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface StatCardProps {
  title: string;
  value: number | string;
  subtitle?: string;
  icon: LucideIcon;
  badge?: string;
  variant?: 'cyan' | 'emerald' | 'amber' | 'rose' | 'blue' | 'purple' | 'neutral';
  onClick?: () => void;
  actionLabel?: string;
  testId?: string;
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  subtitle,
  icon: Icon,
  badge,
  variant = 'cyan',
  onClick,
  actionLabel,
  testId,
}) => {
  const variantStyles = {
    cyan: {
      border: 'border-surveillance-800 hover:border-tactical-cyan/50',
      iconBg: 'bg-tactical-cyan/10 text-tactical-cyan border border-tactical-cyan/20',
      textAccent: 'text-tactical-cyan',
      badgeBg: 'bg-tactical-cyan/10 text-tactical-cyan border-tactical-cyan/30',
    },
    emerald: {
      border: 'border-surveillance-800 hover:border-tactical-emerald/50',
      iconBg: 'bg-tactical-emerald/10 text-tactical-emerald border border-tactical-emerald/20',
      textAccent: 'text-tactical-emerald',
      badgeBg: 'bg-tactical-emerald/10 text-tactical-emerald border-tactical-emerald/30',
    },
    amber: {
      border: 'border-surveillance-800 hover:border-tactical-amber/50',
      iconBg: 'bg-tactical-amber/10 text-tactical-amber border border-tactical-amber/20',
      textAccent: 'text-tactical-amber',
      badgeBg: 'bg-tactical-amber/10 text-tactical-amber border-tactical-amber/30',
    },
    rose: {
      border: 'border-surveillance-800 hover:border-tactical-rose/50',
      iconBg: 'bg-tactical-rose/10 text-tactical-rose border border-tactical-rose/20',
      textAccent: 'text-tactical-rose',
      badgeBg: 'bg-tactical-rose/10 text-tactical-rose border-tactical-rose/30',
    },
    blue: {
      border: 'border-surveillance-800 hover:border-tactical-blue/50',
      iconBg: 'bg-tactical-blue/10 text-tactical-blue border border-tactical-blue/20',
      textAccent: 'text-tactical-blue',
      badgeBg: 'bg-tactical-blue/10 text-tactical-blue border-tactical-blue/30',
    },
    purple: {
      border: 'border-surveillance-800 hover:border-purple-500/50',
      iconBg: 'bg-purple-500/10 text-purple-400 border border-purple-500/20',
      textAccent: 'text-purple-400',
      badgeBg: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
    },
    neutral: {
      border: 'border-surveillance-800 hover:border-surveillance-700',
      iconBg: 'bg-surveillance-800 text-surveillance-300 border border-surveillance-700',
      textAccent: 'text-surveillance-100',
      badgeBg: 'bg-surveillance-800 text-surveillance-400 border-surveillance-700',
    },
  };

  const style = variantStyles[variant];

  const CardWrapper = onClick ? 'button' : 'div';

  return (
    <CardWrapper
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      data-testid={testId}
      aria-label={actionLabel || `${title}: ${value}`}
      className={cn(
        'w-full text-left bg-surveillance-900 border rounded-lg p-4 sm:p-5 shadow-lg transition-all duration-200 flex flex-col justify-between relative group',
        style.border,
        onClick && 'cursor-pointer hover:bg-surveillance-850 hover:shadow-cyan-950/20 active:scale-[0.99] focus:outline-none focus:ring-2 focus:ring-tactical-cyan/40'
      )}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-mono uppercase tracking-wider text-surveillance-400 truncate">
            {title}
          </p>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-2xl sm:text-3xl font-bold font-mono text-surveillance-100 tracking-tight">
              {value}
            </span>
            {badge && (
              <span className={cn('text-[10px] px-1.5 py-0.5 rounded font-mono border uppercase tracking-wider', style.badgeBg)}>
                {badge}
              </span>
            )}
          </div>
        </div>
        <div className={cn('p-2.5 rounded-lg shrink-0 flex items-center justify-center', style.iconBg)}>
          <Icon className="w-5 h-5" aria-hidden="true" />
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 pt-2 border-t border-surveillance-800/60 text-xs">
        {subtitle ? (
          <span className="text-surveillance-400 truncate">{subtitle}</span>
        ) : (
          <span className="text-surveillance-500 font-mono text-[11px]">Aggregated</span>
        )}

        {onClick && (
          <span className="inline-flex items-center gap-0.5 text-xs text-surveillance-400 group-hover:text-surveillance-200 font-medium transition-colors shrink-0">
            <span>{actionLabel || 'View'}</span>
            <ArrowUpRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </span>
        )}
      </div>
    </CardWrapper>
  );
};
