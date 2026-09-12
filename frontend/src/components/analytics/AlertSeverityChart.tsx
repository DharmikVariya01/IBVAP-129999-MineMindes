import React from 'react';
import { Card } from '@/components/common/Card';
import { ShieldAlert, ArrowUpRight } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface AlertSeverityChartProps {
  data: Record<string, number>;
  totalAlerts: number;
  onNavigateToAlerts?: () => void;
}

export const AlertSeverityChart: React.FC<AlertSeverityChartProps> = ({
  data,
  totalAlerts,
  onNavigateToAlerts,
}) => {
  // Normalize severity keys to uppercase
  const normalized: Record<string, number> = {};
  Object.entries(data || {}).forEach(([key, count]) => {
    const normKey = (key || 'UNKNOWN').toUpperCase();
    normalized[normKey] = (normalized[normKey] || 0) + (typeof count === 'number' ? count : 0);
  });

  const criticalCount = normalized['CRITICAL'] || 0;
  const highCount = normalized['HIGH'] || 0;
  const mediumCount = normalized['MEDIUM'] || 0;
  const lowCount = normalized['LOW'] || 0;

  const standardKeys = new Set(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']);
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

  const tiers = [
    {
      label: 'Critical',
      count: criticalCount,
      percent: getPercent(criticalCount),
      width: getPercentWidth(criticalCount),
      barColor: 'bg-tactical-rose',
      textColor: 'text-rose-400',
      badgeBg: 'bg-tactical-rose/10 text-tactical-rose border-tactical-rose/30',
    },
    {
      label: 'High',
      count: highCount,
      percent: getPercent(highCount),
      width: getPercentWidth(highCount),
      barColor: 'bg-tactical-amber',
      textColor: 'text-amber-400',
      badgeBg: 'bg-tactical-amber/10 text-tactical-amber border-tactical-amber/30',
    },
    {
      label: 'Medium',
      count: mediumCount,
      percent: getPercent(mediumCount),
      width: getPercentWidth(mediumCount),
      barColor: 'bg-yellow-500',
      textColor: 'text-yellow-400',
      badgeBg: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30',
    },
    {
      label: 'Low',
      count: lowCount,
      percent: getPercent(lowCount),
      width: getPercentWidth(lowCount),
      barColor: 'bg-tactical-blue',
      textColor: 'text-blue-400',
      badgeBg: 'bg-tactical-blue/10 text-tactical-blue border-tactical-blue/30',
    },
    ...customItems.map((ci) => ({
      label: ci.key,
      count: ci.count,
      percent: getPercent(ci.count),
      width: getPercentWidth(ci.count),
      barColor: 'bg-surveillance-500',
      textColor: 'text-surveillance-300',
      badgeBg: 'bg-surveillance-800 text-surveillance-300 border-surveillance-700',
    })),
  ];

  return (
    <Card
      data-testid="alert-severity-chart"
      title="Alert Severity Breakdown"
      subtitle="Threat impact distribution"
      action={
        onNavigateToAlerts && (
          <button
            type="button"
            onClick={onNavigateToAlerts}
            aria-label="View alerts in Alert Center"
            className="flex items-center gap-1 text-xs text-surveillance-400 hover:text-tactical-cyan transition-colors focus:outline-none focus:underline"
          >
            <span>Alert Center</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </button>
        )
      }
    >
      <div className="space-y-3.5">
        {computedTotal === 0 ? (
          <div className="py-4 text-center">
            <ShieldAlert className="w-8 h-8 text-surveillance-600 mx-auto mb-2" aria-hidden="true" />
            <p className="text-xs text-surveillance-400 font-mono">
              No security alerts recorded.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {tiers.map((tier) => (
              <div key={tier.label} className="space-y-1">
                <div className="flex justify-between items-center text-xs">
                  <span className="font-medium text-surveillance-200">{tier.label}</span>
                  <div className="flex items-center gap-2 font-mono">
                    <span className="font-semibold text-surveillance-100">{tier.count}</span>
                    <span className={cn('text-[10px] px-1 py-0.2 rounded border', tier.badgeBg)}>
                      {tier.percent}
                    </span>
                  </div>
                </div>

                <div
                  className="h-2 w-full bg-surveillance-950 rounded-full overflow-hidden border border-surveillance-800/80"
                  role="progressbar"
                  aria-valuenow={tier.count}
                  aria-valuemin={0}
                  aria-valuemax={computedTotal}
                  aria-label={`${tier.label} alerts: ${tier.count} (${tier.percent})`}
                >
                  <div
                    style={{ width: `${tier.width}%` }}
                    className={cn('h-full transition-all duration-300', tier.barColor)}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
};
