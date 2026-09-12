import React from 'react';
import { ArrowDownUp, ArrowUp, ArrowDown, ShieldAlert, Clock, Layers, Activity, Bell, ListFilter } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { TimelineFilterCategory, TimelineSortOrder } from '@/types/timeline';

export interface TimelineFiltersProps {
  activeCategory: TimelineFilterCategory;
  onSelectCategory: (category: TimelineFilterCategory) => void;
  sortOrder: TimelineSortOrder;
  onToggleSortOrder: () => void;
  categoryCounts: Record<TimelineFilterCategory, number>;
  className?: string;
}

interface FilterButtonDef {
  id: TimelineFilterCategory;
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
}

const FILTER_BUTTONS: FilterButtonDef[] = [
  { id: 'ALL', label: 'All' },
  { id: 'ALERTS', label: 'Alerts / Critical', icon: Bell },
  { id: 'BREACH', label: 'Fence Breach', icon: ShieldAlert },
  { id: 'LOITERING', label: 'Loitering', icon: Clock },
  { id: 'ZONE', label: 'Zone', icon: Layers },
  { id: 'MOVEMENT', label: 'Movement', icon: Activity },
  { id: 'OTHER', label: 'Other' },
];

export const TimelineFilters: React.FC<TimelineFiltersProps> = ({
  activeCategory,
  onSelectCategory,
  sortOrder,
  onToggleSortOrder,
  categoryCounts,
  className,
}) => {
  return (
    <div
      className={cn(
        'flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-3 bg-surveillance-900/80 border border-surveillance-800 rounded-lg text-xs font-mono',
        className
      )}
      data-testid="timeline-filters-bar"
    >
      {/* 1. Category Filter Buttons */}
      <div
        role="group"
        aria-label="Filter events by category"
        className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto pb-1 sm:pb-0 scrollbar-none"
      >
        <span className="text-surveillance-400 flex items-center gap-1 mr-1 text-[11px] uppercase tracking-wider flex-shrink-0">
          <ListFilter className="w-3.5 h-3.5" aria-hidden="true" />
          Filter:
        </span>

        {FILTER_BUTTONS.map((btn) => {
          const count = categoryCounts[btn.id] ?? 0;
          const isActive = activeCategory === btn.id;
          const Icon = btn.icon;

          return (
            <button
              key={btn.id}
              type="button"
              onClick={() => onSelectCategory(btn.id)}
              aria-pressed={isActive}
              aria-label={`Filter by ${btn.label}, ${count} events available`}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 rounded text-xs transition-colors whitespace-nowrap border focus:outline-none focus:ring-1 focus:ring-tactical-emerald',
                isActive
                  ? 'bg-tactical-emerald/15 text-tactical-emerald border-tactical-emerald/50 font-bold'
                  : 'bg-surveillance-950/80 text-surveillance-400 hover:text-surveillance-200 border-surveillance-800 hover:bg-surveillance-850'
              )}
              data-testid={`timeline-filter-${btn.id.toLowerCase()}`}
            >
              {Icon && <Icon className="w-3 h-3 flex-shrink-0" />}
              <span>{btn.label}</span>
              <span
                className={cn(
                  'text-[10px] px-1 py-0.2 rounded font-semibold',
                  isActive
                    ? 'bg-tactical-emerald/20 text-tactical-emerald'
                    : 'bg-surveillance-800 text-surveillance-500'
                )}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* 2. Chronological Sort Order Toggle */}
      <div className="flex items-center gap-2 self-end sm:self-auto flex-shrink-0">
        <button
          type="button"
          onClick={onToggleSortOrder}
          aria-label={`Sort order: ${sortOrder === 'newest' ? 'Newest first' : 'Oldest first'}. Click to toggle.`}
          className="flex items-center gap-1.5 px-2.5 py-1 bg-surveillance-950/80 hover:bg-surveillance-850 text-surveillance-200 border border-surveillance-800 hover:border-surveillance-700 rounded transition-colors focus:outline-none focus:ring-1 focus:ring-tactical-emerald"
          data-testid="timeline-sort-toggle-btn"
        >
          <ArrowDownUp className="w-3.5 h-3.5 text-surveillance-400" aria-hidden="true" />
          <span>
            {sortOrder === 'newest' ? 'Newest First' : 'Oldest First'}
          </span>
          {sortOrder === 'newest' ? (
            <ArrowDown className="w-3 h-3 text-tactical-emerald ml-0.5" aria-hidden="true" />
          ) : (
            <ArrowUp className="w-3 h-3 text-tactical-cyan ml-0.5" aria-hidden="true" />
          )}
        </button>
      </div>
    </div>
  );
};
