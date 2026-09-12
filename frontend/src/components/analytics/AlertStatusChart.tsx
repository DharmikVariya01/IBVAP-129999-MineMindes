import React from 'react';
import { Card } from '@/components/common/Card';
import { Bell, CheckCircle2, Eye, ShieldCheck, ArrowUpRight } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface AlertStatusChartProps {
  data: Record<string, number>;
  totalAlerts: number;
  onNavigateToAlerts?: () => void;
}

export const AlertStatusChart: React.FC<AlertStatusChartProps> = ({
  data,
  totalAlerts,
  onNavigateToAlerts,
}) => {
  const normalized: Record<string, number> = {};
  Object.entries(data || {}).forEach(([key, count]) => {
    const normKey = (key || 'UNKNOWN').toUpperCase();
    normalized[normKey] = (normalized[normKey] || 0) + (typeof count === 'number' ? count : 0);
  });

  const activeCount = normalized['ACTIVE'] || 0;
  const ackCount = normalized['ACKNOWLEDGED'] || 0;
  const resolvedCount = normalized['RESOLVED'] || 0;

  const standardKeys = new Set(['ACTIVE', 'ACKNOWLEDGED', 'RESOLVED']);
  const customItems = Object.entries(normalized)
    .filter(([key]) => !standardKeys.has(key))
    .map(([key, count]) => ({ key, count }));

  const computedTotal = totalAlerts > 0
    ? totalAlerts
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
      label: 'Active (Unresolved)',
      count: activeCount,
      percent: getPercent(activeCount),
      width: getPercentWidth(activeCount),
      barColor: 'bg-tactical-amber',
      badgeBg: 'bg-tactical-amber/10 text-tactical-amber border-tactical-amber/30',
      icon: Bell,
    },
    {
      label: 'Acknowledged',
      count: ackCount,
      percent: getPercent(ackCount),
      width: getPercentWidth(ackCount),
      barColor: 'bg-tactical-blue',
      badgeBg: 'bg-tactical-blue/10 text-tactical-blue border-tactical-blue/30',
      icon: Eye,
    },
    {
      label: 'Resolved',
      count: resolvedCount,
      percent: getPercent(resolvedCount),
      width: getPercentWidth(resolvedCount),
      barColor: 'bg-tactical-emerald',
      badgeBg: 'bg-tactical-emerald/10 text-tactical-emerald border-tactical-emerald/30',
      icon: CheckCircle2,
    },
    ...customItems.map((ci) => ({
      label: ci.key,
      count: ci.count,
      percent: getPercent(ci.count),
      width: getPercentWidth(ci.count),
      barColor: 'bg-surveillance-500',
      badgeBg: 'bg-surveillance-800 text-surveillance-300 border-surveillance-700',
      icon: ShieldCheck,
    })),
  ];

  return (
    <Card
      data-testid="alert-status-chart"
      title="Alert Resolution Lifecycle"
      subtitle="Operator triage & mitigation workflow"
      action={
        onNavigateToAlerts && (
          <button
            type="button"
            onClick={onNavigateToAlerts}
            aria-label="Manage alerts in Alert Center"
            className="flex items-center gap-1 text-xs text-surveillance-400 hover:text-tactical-cyan transition-colors focus:outline-none focus:underline"
          >
            <span>Alert Center</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </button>
        )
      }
    >
      <div className="space-y-4">
        {computedTotal === 0 ? (
          <div className="py-4 text-center">
            <ShieldCheck className="w-8 h-8 text-surveillance-600 mx-auto mb-2" aria-hidden="true" />
            <p className="text-xs text-surveillance-400 font-mono">
              No alert triage history recorded.
            </p>
          </div>
        ) : (
          <>
            <div className="space-y-1.5">
              <div className="flex justify-between items-center text-xs font-mono text-surveillance-400">
                <span>TRIAGE STATUS</span>
                <span className="text-surveillance-200">{computedTotal} Total</span>
              </div>
              <div
                className="h-3 w-full bg-surveillance-950 rounded-full overflow-hidden flex border border-surveillance-800"
                role="progressbar"
                aria-valuenow={activeCount}
                aria-valuemin={0}
                aria-valuemax={computedTotal}
                aria-label={`Alert triage: ${activeCount} active, ${ackCount} acknowledged, ${resolvedCount} resolved`}
              >
                {items.map((item) =>
                  item.count > 0 ? (
                    <div
                      key={item.label}
                      style={{ width: `${item.width}%` }}
                      className={cn('h-full transition-all duration-300', item.barColor)}
                      title={`${item.label}: ${item.count} (${item.percent})`}
                    />
                  ) : null
                )}
              </div>
            </div>

            <ul className="divide-y divide-surveillance-800/60 pt-1">
              {items.map((item) => {
                const Icon = item.icon;
                return (
                  <li key={item.label} className="py-2 flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
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
          </>
        )}
      </div>
    </Card>
  );
};
