import React from 'react';
import { Video, VideoOff, AlertTriangle, Radio } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface MapLegendProps {
  className?: string;
  isCompact?: boolean;
}

export const MapLegend: React.FC<MapLegendProps> = ({ className, isCompact = false }) => {
  const legendItems = [
    {
      id: 'online',
      label: 'Online Camera',
      description: 'Active streaming & heartbeat',
      icon: Video,
      colorClasses: 'text-tactical-emerald bg-tactical-emerald/10 border-tactical-emerald/40',
      indicator: 'h-2 w-2 rounded-full bg-tactical-emerald',
    },
    {
      id: 'offline',
      label: 'Offline Camera',
      description: 'Stream disconnected or unreachable',
      icon: VideoOff,
      colorClasses: 'text-surveillance-400 bg-surveillance-800/80 border-surveillance-700',
      indicator: 'h-2 w-2 rounded-full bg-surveillance-500',
    },
    {
      id: 'alert',
      label: 'Active Threat Alert',
      description: 'Unacknowledged security alarm',
      icon: AlertTriangle,
      colorClasses: 'text-tactical-rose bg-tactical-rose/10 border-tactical-rose/60 animate-pulse',
      indicator: 'h-2 w-2 rounded-full bg-tactical-rose animate-ping',
    },
    {
      id: 'activity',
      label: 'Live Activity (Unit)',
      description: 'Camera-level real-time activity',
      icon: Radio,
      colorClasses: 'text-tactical-cyan bg-tactical-cyan/10 border-tactical-cyan/40',
      indicator: 'h-2 w-2 rounded-full bg-tactical-cyan',
    },
  ];

  return (
    <div
      role="region"
      aria-label="Tactical Map Legend"
      data-testid="map-legend"
      className={cn(
        'p-3 bg-surveillance-900/95 border border-surveillance-800 rounded-lg shadow-xl backdrop-blur-sm text-xs font-mono',
        className
      )}
    >
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-surveillance-800/80">
        <span className="text-[11px] font-bold uppercase tracking-wider text-surveillance-300 flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-tactical-emerald" />
          Tactical Map Symbology
        </span>
        <span className="text-[9px] px-1.5 py-0.5 rounded bg-surveillance-800 text-surveillance-400">
          M21
        </span>
      </div>

      <div className={cn('grid gap-2', isCompact ? 'grid-cols-2' : 'grid-cols-1')}>
        {legendItems.map((item) => {
          const Icon = item.icon;
          return (
            <div
              key={item.id}
              className="flex items-center gap-2 p-1.5 rounded bg-surveillance-950/60 border border-surveillance-850"
              data-testid={`legend-item-${item.id}`}
            >
              <div
                className={cn(
                  'p-1 rounded border flex items-center justify-center flex-shrink-0',
                  item.colorClasses
                )}
              >
                <Icon className="w-3.5 h-3.5" aria-hidden="true" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className={item.indicator} aria-hidden="true" />
                  <span className="font-semibold text-surveillance-200 truncate">
                    {item.label}
                  </span>
                </div>
                {!isCompact && (
                  <p className="text-[10px] text-surveillance-500 truncate">
                    {item.description}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
