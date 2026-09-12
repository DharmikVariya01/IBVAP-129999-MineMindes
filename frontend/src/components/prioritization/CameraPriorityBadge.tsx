import React from 'react';
import type { CameraPriorityLevel } from '@/types/prioritization';
import { cn } from '@/utils/cn';
import { ShieldAlert, AlertTriangle, AlertCircle, Info, ShieldCheck, WifiOff } from 'lucide-react';

export interface CameraPriorityBadgeProps {
  level: CameraPriorityLevel;
  size?: 'sm' | 'md' | 'lg';
  showIcon?: boolean;
  className?: string;
}

export const CameraPriorityBadge: React.FC<CameraPriorityBadgeProps> = ({
  level,
  size = 'md',
  showIcon = true,
  className,
}) => {
  const getBadgeConfig = () => {
    switch (level) {
      case 'CRITICAL':
        return {
          label: 'CRITICAL',
          icon: ShieldAlert,
          classes:
            'bg-tactical-rose/20 text-rose-300 border-tactical-rose/60 shadow-[0_0_10px_rgba(244,63,94,0.3)] animate-pulse',
          iconColor: 'text-tactical-rose',
        };
      case 'HIGH':
        return {
          label: 'HIGH',
          icon: AlertTriangle,
          classes: 'bg-tactical-amber/20 text-amber-300 border-tactical-amber/50',
          iconColor: 'text-tactical-amber',
        };
      case 'MEDIUM':
        return {
          label: 'MEDIUM',
          icon: AlertCircle,
          classes: 'bg-tactical-cyan/15 text-cyan-300 border-tactical-cyan/40',
          iconColor: 'text-tactical-cyan',
        };
      case 'LOW':
        return {
          label: 'LOW',
          icon: Info,
          classes: 'bg-blue-500/15 text-blue-300 border-blue-500/40',
          iconColor: 'text-blue-400',
        };
      case 'CLEAR':
        return {
          label: 'CLEAR',
          icon: ShieldCheck,
          classes: 'bg-tactical-emerald/15 text-emerald-300 border-tactical-emerald/40',
          iconColor: 'text-tactical-emerald',
        };
      case 'OFFLINE':
        return {
          label: 'OFFLINE',
          icon: WifiOff,
          classes: 'bg-surveillance-800/80 text-surveillance-400 border-surveillance-700',
          iconColor: 'text-surveillance-500',
        };
      case 'ERROR':
        return {
          label: 'ERROR',
          icon: AlertTriangle,
          classes: 'bg-tactical-rose/10 text-rose-400 border-rose-900/60',
          iconColor: 'text-tactical-rose',
        };
      default:
        return {
          label: level,
          icon: Info,
          classes: 'bg-surveillance-800 text-surveillance-300 border-surveillance-700',
          iconColor: 'text-surveillance-400',
        };
    }
  };

  const config = getBadgeConfig();
  const IconComponent = config.icon;

  const sizeClasses = {
    sm: 'text-[10px] px-1.5 py-0.5 gap-1',
    md: 'text-xs px-2 py-0.5 gap-1.5',
    lg: 'text-sm px-2.5 py-1 gap-2',
  }[size];

  const iconSizes = {
    sm: 'w-3 h-3',
    md: 'w-3.5 h-3.5',
    lg: 'w-4 h-4',
  }[size];

  return (
    <span
      role="status"
      aria-label={`Tactical Priority: ${config.label}`}
      className={cn(
        'inline-flex items-center rounded font-mono font-bold tracking-wider uppercase border select-none',
        sizeClasses,
        config.classes,
        className
      )}
      data-testid={`priority-badge-${level.toLowerCase()}`}
    >
      {showIcon && <IconComponent className={cn(iconSizes, config.iconColor, 'flex-shrink-0')} aria-hidden="true" />}
      <span>{config.label}</span>
    </span>
  );
};
