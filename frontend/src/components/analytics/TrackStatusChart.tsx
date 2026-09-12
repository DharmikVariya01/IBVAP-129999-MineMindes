import React from 'react';
import { Card } from '@/components/common/Card';
import { Crosshair, CheckCircle2, HelpCircle, ArrowUpRight } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface TrackStatusChartProps {
  data: Record<string, number>;
  totalTracks: number;
  onNavigateToTimeline?: () => void;
}

export const TrackStatusChart: React.FC<TrackStatusChartProps> = ({
  data,
  totalTracks,
  onNavigateToTimeline,
}) => {
  const normalized: Record<string, number> = {};
  Object.entries(data || {}).forEach(([key, count]) => {
    const normKey = (key || 'UNKNOWN').toUpperCase();
    normalized[normKey] = (normalized[normKey] || 0) + (typeof count === 'number' ? count : 0);
  });

  const activeCount = normalized['ACTIVE'] || 0;
  const lostCount = normalized['LOST'] || 0;
  const completedCount = normalized['COMPLETED'] || 0;

  const standardKeys = new Set(['ACTIVE', 'LOST', 'COMPLETED']);
  const customItems = Object.entries(normalized)
    .filter(([key]) => !standardKeys.has(key))
    .map(([key, count]) => ({ key, count }));

  const computedTotal = totalTracks > 0
    ? totalTracks
    : Object.values(normalized).reduce((acc, v) => acc + v, 0);

  const getPercent = (count: number): string => {
    if (computedTotal <= 0) return '0%';
    return `${Math.round((count / computedTotal) * 100)}%`;
  };

  const getPercentWidth = (count: number): number => {
    if (computedTotal <= 0) return 0;
    return Math.max(0, Math.min(100, (count / computedTotal) * 100));
  };

  const categories = [
    {
      label: 'Active Tracking',
      count: activeCount,
      percent: getPercent(activeCount),
      width: getPercentWidth(activeCount),
      barColor: 'bg-tactical-cyan',
      badgeBg: 'bg-tactical-cyan/10 text-tactical-cyan border-tactical-cyan/30',
      icon: Crosshair,
    },
    {
      label: 'Lost Signal',
      count: lostCount,
      percent: getPercent(lostCount),
      width: getPercentWidth(lostCount),
      barColor: 'bg-tactical-amber',
      badgeBg: 'bg-tactical-amber/10 text-tactical-amber border-tactical-amber/30',
      icon: HelpCircle,
    },
    {
      label: 'Completed / Exited',
      count: completedCount,
      percent: getPercent(completedCount),
      width: getPercentWidth(completedCount),
      barColor: 'bg-surveillance-500',
      badgeBg: 'bg-surveillance-800 text-surveillance-300 border-surveillance-700',
      icon: CheckCircle2,
    },
    ...customItems.map((ci) => ({
      label: ci.key,
      count: ci.count,
      percent: getPercent(ci.count),
      width: getPercentWidth(ci.count),
      barColor: 'bg-purple-500',
      badgeBg: 'bg-purple-500/10 text-purple-300 border-purple-500/30',
      icon: Crosshair,
    })),
  ];

  return (
    <Card
      data-testid="track-status-chart"
      title="Target Tracking Activity"
      subtitle="Lifecycle status of tracked border entities"
      action={
        onNavigateToTimeline && (
          <button
            type="button"
            onClick={onNavigateToTimeline}
            aria-label="View tracks in Event Timeline"
            className="flex items-center gap-1 text-xs text-surveillance-400 hover:text-tactical-cyan transition-colors focus:outline-none focus:underline"
          >
            <span>Timeline</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </button>
        )
      }
    >
      <div className="space-y-4">
        {computedTotal === 0 ? (
          <div className="py-4 text-center">
            <Crosshair className="w-8 h-8 text-surveillance-600 mx-auto mb-2" aria-hidden="true" />
            <p className="text-xs text-surveillance-400 font-mono">
              No tracking entities currently recorded.
            </p>
          </div>
        ) : (
          <>
            <div className="space-y-1.5">
              <div className="flex justify-between items-center text-xs font-mono text-surveillance-400">
                <span>LIFECYCLE PROPORTION</span>
                <span className="text-surveillance-200">{computedTotal} Total</span>
              </div>
              <div
                className="h-3 w-full bg-surveillance-950 rounded-full overflow-hidden flex border border-surveillance-800"
                role="progressbar"
                aria-valuenow={activeCount}
                aria-valuemin={0}
                aria-valuemax={computedTotal}
                aria-label={`Tracks: ${activeCount} active, ${lostCount} lost, ${completedCount} completed`}
              >
                {categories.map((cat) =>
                  cat.count > 0 ? (
                    <div
                      key={cat.label}
                      style={{ width: `${cat.width}%` }}
                      className={cn('h-full transition-all duration-300', cat.barColor)}
                      title={`${cat.label}: ${cat.count} (${cat.percent})`}
                    />
                  ) : null
                )}
              </div>
            </div>

            <ul className="divide-y divide-surveillance-800/60 pt-1">
              {categories.map((cat) => {
                const Icon = cat.icon;
                return (
                  <li key={cat.label} className="py-2 flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <Icon className="w-3.5 h-3.5 text-surveillance-400" aria-hidden="true" />
                      <span className="font-medium text-surveillance-200">{cat.label}</span>
                    </div>
                    <div className="flex items-center gap-3 font-mono">
                      <span className="font-semibold text-surveillance-100">{cat.count}</span>
                      <span className={cn('text-[11px] px-1.5 py-0.5 rounded border', cat.badgeBg)}>
                        {cat.percent}
                      </span>
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>
    </Card>
  );
};
