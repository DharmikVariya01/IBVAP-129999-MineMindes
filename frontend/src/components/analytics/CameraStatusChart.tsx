import React from 'react';
import { Card } from '@/components/common/Card';
import { Video, ShieldCheck, AlertTriangle, ShieldAlert, ArrowUpRight } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface CameraStatusChartProps {
  data: Record<string, number>;
  totalCameras: number;
  onNavigateToMap?: () => void;
}

export const CameraStatusChart: React.FC<CameraStatusChartProps> = ({
  data,
  totalCameras,
  onNavigateToMap,
}) => {
  // Normalize status keys to uppercase
  const normalized: Record<string, number> = {};
  Object.entries(data || {}).forEach(([key, count]) => {
    const normKey = (key || 'UNKNOWN').toUpperCase();
    normalized[normKey] = (normalized[normKey] || 0) + (typeof count === 'number' ? count : 0);
  });

  const onlineCount = normalized['ONLINE'] || 0;
  const offlineCount = normalized['OFFLINE'] || 0;
  const errorCount = normalized['ERROR'] || 0;

  // Track any extra categories
  const standardKeys = new Set(['ONLINE', 'OFFLINE', 'ERROR']);
  const customItems = Object.entries(normalized)
    .filter(([key]) => !standardKeys.has(key))
    .map(([key, count]) => ({ key, count }));

  const computedTotal = totalCameras > 0 
    ? totalCameras 
    : Object.values(normalized).reduce((acc, v) => acc + v, 0);

  const getPercent = (count: number): string => {
    if (computedTotal <= 0) return '0%';
    return `${Math.round((count / computedTotal) * 100)}%`;
  };

  const getPercentWidth = (count: number): number => {
    if (computedTotal <= 0) return 0;
    return Math.max(0, Math.min(100, (count / computedTotal) * 100));
  };

  const items = [
    {
      label: 'Online',
      count: onlineCount,
      percent: getPercent(onlineCount),
      color: 'bg-tactical-emerald',
      textColor: 'text-emerald-400',
      badgeBg: 'bg-tactical-emerald/10 text-tactical-emerald border-tactical-emerald/30',
      icon: ShieldCheck,
    },
    {
      label: 'Offline',
      count: offlineCount,
      percent: getPercent(offlineCount),
      color: 'bg-tactical-amber',
      textColor: 'text-amber-400',
      badgeBg: 'bg-tactical-amber/10 text-tactical-amber border-tactical-amber/30',
      icon: AlertTriangle,
    },
    {
      label: 'Error',
      count: errorCount,
      percent: getPercent(errorCount),
      color: 'bg-tactical-rose',
      textColor: 'text-rose-400',
      badgeBg: 'bg-tactical-rose/10 text-tactical-rose border-tactical-rose/30',
      icon: ShieldAlert,
    },
    ...customItems.map((ci) => ({
      label: ci.key,
      count: ci.count,
      percent: getPercent(ci.count),
      color: 'bg-surveillance-500',
      textColor: 'text-surveillance-300',
      badgeBg: 'bg-surveillance-800 text-surveillance-300 border-surveillance-700',
      icon: Video,
    })),
  ];

  return (
    <Card
      data-testid="camera-status-chart"
      title="Camera Operational Status"
      subtitle="Deployment distribution by health state"
      action={
        onNavigateToMap && (
          <button
            type="button"
            onClick={onNavigateToMap}
            aria-label="View cameras on Tactical Map"
            className="flex items-center gap-1 text-xs text-surveillance-400 hover:text-tactical-cyan transition-colors focus:outline-none focus:underline"
          >
            <span>Tactical Map</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </button>
        )
      }
    >
      <div className="space-y-4">
        {/* Composite Segmented Progress Bar */}
        <div className="space-y-1.5">
          <div className="flex justify-between items-center text-xs font-mono text-surveillance-400">
            <span>AVAILABILITY DISTRIBUTION</span>
            <span className="text-surveillance-200">{computedTotal} Total</span>
          </div>

          <div
            className="h-3 w-full bg-surveillance-950 rounded-full overflow-hidden flex border border-surveillance-800"
            role="progressbar"
            aria-valuenow={onlineCount}
            aria-valuemin={0}
            aria-valuemax={computedTotal || 1}
            aria-label={`Camera status distribution: ${onlineCount} online, ${offlineCount} offline, ${errorCount} error`}
          >
            {computedTotal === 0 ? (
              <div className="w-full h-full bg-surveillance-800/60" />
            ) : (
              <>
                {onlineCount > 0 && (
                  <div
                    style={{ width: `${getPercentWidth(onlineCount)}%` }}
                    className="h-full bg-tactical-emerald transition-all duration-300"
                    title={`Online: ${onlineCount} (${getPercent(onlineCount)})`}
                  />
                )}
                {offlineCount > 0 && (
                  <div
                    style={{ width: `${getPercentWidth(offlineCount)}%` }}
                    className="h-full bg-tactical-amber transition-all duration-300"
                    title={`Offline: ${offlineCount} (${getPercent(offlineCount)})`}
                  />
                )}
                {errorCount > 0 && (
                  <div
                    style={{ width: `${getPercentWidth(errorCount)}%` }}
                    className="h-full bg-tactical-rose transition-all duration-300"
                    title={`Error: ${errorCount} (${getPercent(errorCount)})`}
                  />
                )}
                {customItems.map((ci) => (
                  <div
                    key={ci.key}
                    style={{ width: `${getPercentWidth(ci.count)}%` }}
                    className="h-full bg-surveillance-500 transition-all duration-300"
                    title={`${ci.key}: ${ci.count} (${getPercent(ci.count)})`}
                  />
                ))}
              </>
            )}
          </div>
        </div>

        {/* Accessible Data List & Metrics Breakdown */}
        {computedTotal === 0 ? (
          <p className="text-xs text-surveillance-500 font-mono text-center py-2">
            No camera assets currently registered.
          </p>
        ) : (
          <ul className="divide-y divide-surveillance-800/60 pt-1">
            {items.map((item) => {
              const Icon = item.icon;
              return (
                <li
                  key={item.label}
                  className="py-2 flex items-center justify-between gap-3 text-xs"
                >
                  <div className="flex items-center gap-2">
                    <span className={cn('w-2 h-2 rounded-full shrink-0', item.color)} />
                    <Icon className="w-3.5 h-3.5 text-surveillance-400" aria-hidden="true" />
                    <span className="font-medium text-surveillance-200">{item.label}</span>
                  </div>
                  <div className="flex items-center gap-3 font-mono">
                    <span className="font-semibold text-surveillance-100">{item.count}</span>
                    <span className={cn('text-[11px] px-1.5 py-0.5 rounded border', item.badgeBg)}>
                      {item.percent}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Card>
  );
};
