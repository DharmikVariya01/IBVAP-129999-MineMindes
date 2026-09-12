import React from 'react';
import { Search, Filter, RotateCcw, ArrowUpDown } from 'lucide-react';
import type { AlertSeverity, AlertStatus, AlertType } from '@/types/api';

export interface AlertFilterValues {
  status: AlertStatus | 'ALL';
  severity: AlertSeverity | 'ALL';
  alertType: AlertType | 'ALL';
  search: string;
  sortBy: 'newest' | 'oldest' | 'severity';
}

export interface AlertFiltersProps {
  values: AlertFilterValues;
  onChange: (values: AlertFilterValues) => void;
  onReset: () => void;
  activeCount?: number;
  totalCount?: number;
}

export const AlertFilters: React.FC<AlertFiltersProps> = ({
  values,
  onChange,
  onReset,
  activeCount,
  totalCount,
}) => {
  const handleFieldChange = <K extends keyof AlertFilterValues>(
    field: K,
    value: AlertFilterValues[K]
  ) => {
    onChange({
      ...values,
      [field]: value,
    });
  };

  const isFiltered =
    values.status !== 'ALL' ||
    values.severity !== 'ALL' ||
    values.alertType !== 'ALL' ||
    values.search.trim() !== '' ||
    values.sortBy !== 'newest';

  return (
    <div
      className="bg-surveillance-900 border border-surveillance-800 rounded-lg p-3.5 space-y-3"
      data-testid="alert-filters"
    >
      {/* Top Filter Controls Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2.5">
        {/* 1. Search Query Input */}
        <div className="relative">
          <label htmlFor="alert-search" className="sr-only">
            Search alerts
          </label>
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-surveillance-500" aria-hidden="true" />
          <input
            id="alert-search"
            type="text"
            value={values.search}
            onChange={(e) => handleFieldChange('search', e.target.value)}
            placeholder="Search alerts, camera, ID..."
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-surveillance-950 border border-surveillance-700 rounded text-surveillance-100 placeholder-surveillance-500 focus:outline-none focus:ring-1 focus:ring-tactical-emerald focus:border-tactical-emerald font-mono"
            data-testid="filter-search-input"
          />
        </div>

        {/* 2. Status Filter */}
        <div>
          <label htmlFor="filter-status" className="sr-only">
            Filter by status
          </label>
          <select
            id="filter-status"
            value={values.status}
            onChange={(e) => handleFieldChange('status', e.target.value as AlertFilterValues['status'])}
            className="w-full px-2.5 py-1.5 text-xs bg-surveillance-950 border border-surveillance-700 rounded text-surveillance-100 focus:outline-none focus:ring-1 focus:ring-tactical-emerald focus:border-tactical-emerald font-mono"
            data-testid="filter-status-select"
          >
            <option value="ALL">Status: All Statuses</option>
            <option value="ACTIVE">Status: Active (Unacknowledged)</option>
            <option value="ACKNOWLEDGED">Status: Acknowledged</option>
            <option value="RESOLVED">Status: Resolved</option>
          </select>
        </div>

        {/* 3. Severity Filter */}
        <div>
          <label htmlFor="filter-severity" className="sr-only">
            Filter by severity
          </label>
          <select
            id="filter-severity"
            value={values.severity}
            onChange={(e) => handleFieldChange('severity', e.target.value as AlertFilterValues['severity'])}
            className="w-full px-2.5 py-1.5 text-xs bg-surveillance-950 border border-surveillance-700 rounded text-surveillance-100 focus:outline-none focus:ring-1 focus:ring-tactical-emerald focus:border-tactical-emerald font-mono"
            data-testid="filter-severity-select"
          >
            <option value="ALL">Severity: All Levels</option>
            <option value="CRITICAL">Severity: CRITICAL</option>
            <option value="HIGH">Severity: HIGH</option>
            <option value="MEDIUM">Severity: MEDIUM</option>
            <option value="LOW">Severity: LOW</option>
          </select>
        </div>

        {/* 4. Alert Type Filter */}
        <div>
          <label htmlFor="filter-alert-type" className="sr-only">
            Filter by alert type
          </label>
          <select
            id="filter-alert-type"
            value={values.alertType}
            onChange={(e) => handleFieldChange('alertType', e.target.value as AlertFilterValues['alertType'])}
            className="w-full px-2.5 py-1.5 text-xs bg-surveillance-950 border border-surveillance-700 rounded text-surveillance-100 focus:outline-none focus:ring-1 focus:ring-tactical-emerald focus:border-tactical-emerald font-mono"
            data-testid="filter-type-select"
          >
            <option value="ALL">Category: All Types</option>
            <option value="FENCE_BREACH">Fence Breach</option>
            <option value="LOITERING">Loitering</option>
          </select>
        </div>

        {/* 5. Sort By Control */}
        <div className="flex items-center gap-1.5">
          <label htmlFor="sort-alerts" className="sr-only">
            Sort order
          </label>
          <div className="relative flex-1">
            <ArrowUpDown className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-surveillance-500" aria-hidden="true" />
            <select
              id="sort-alerts"
              value={values.sortBy}
              onChange={(e) => handleFieldChange('sortBy', e.target.value as AlertFilterValues['sortBy'])}
              className="w-full pl-8 pr-2.5 py-1.5 text-xs bg-surveillance-950 border border-surveillance-700 rounded text-surveillance-100 focus:outline-none focus:ring-1 focus:ring-tactical-emerald focus:border-tactical-emerald font-mono"
              data-testid="sort-select"
            >
              <option value="newest">Sort: Newest First</option>
              <option value="severity">Sort: Highest Severity</option>
              <option value="oldest">Sort: Oldest First</option>
            </select>
          </div>

          {isFiltered && (
            <button
              type="button"
              onClick={onReset}
              title="Reset all filters"
              aria-label="Reset all filters"
              className="px-2 py-1.5 bg-surveillance-800 hover:bg-surveillance-700 text-surveillance-300 hover:text-white rounded border border-surveillance-700 transition-colors"
              data-testid="filter-reset-btn"
            >
              <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      {/* Summary Filter Meta Bar */}
      <div className="flex items-center justify-between text-[11px] font-mono text-surveillance-400 pt-1 border-t border-surveillance-800/60">
        <div className="flex items-center gap-2">
          <Filter className="w-3 h-3 text-surveillance-500" aria-hidden="true" />
          <span>
            Showing <strong className="text-surveillance-200">{activeCount ?? 0}</strong> of{' '}
            <strong className="text-surveillance-200">{totalCount ?? 0}</strong> loaded alerts
          </span>
          {isFiltered && (
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-tactical-emerald/10 text-tactical-emerald border border-tactical-emerald/20">
              FILTER APPLIED
            </span>
          )}
        </div>

        <div className="hidden sm:block text-surveillance-500">
          AUTO-SORT ACTIVE
        </div>
      </div>
    </div>
  );
};
