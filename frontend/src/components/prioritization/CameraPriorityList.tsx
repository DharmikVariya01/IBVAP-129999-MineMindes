import React, { useState, useMemo } from 'react';
import type { PrioritizedCamera, PrioritySummaryCounts } from '@/types/prioritization';
import { CameraPriorityCard } from './CameraPriorityCard';
import { PriorityLegend } from './PriorityLegend';
import { Button } from '@/components/common/Button';
import { LoadingState } from '@/components/common/LoadingState';
import {
  ShieldAlert,
  RefreshCw,
  ArrowUpDown,
  Filter,
  CheckCircle2,
  AlertCircle,
  Camera as CameraIcon,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { cn } from '@/utils/cn';

export interface CameraPriorityListProps {
  prioritizedCameras: PrioritizedCamera[];
  summaryCounts: PrioritySummaryCounts;
  selectedCameraId: string | null;
  loading: boolean;
  error: string | null;
  sortByPriority: boolean;
  onToggleSortByPriority: () => void;
  onSelectCamera: (cameraId: string) => void;
  onRefresh: () => void;
  onNavigateToAlerts?: (alertId: string) => void;
  onNavigateToMap?: (cameraId: string) => void;
  className?: string;
}

export const CameraPriorityList: React.FC<CameraPriorityListProps> = ({
  prioritizedCameras,
  summaryCounts,
  selectedCameraId,
  loading,
  error,
  sortByPriority,
  onToggleSortByPriority,
  onSelectCamera,
  onRefresh,
  onNavigateToAlerts,
  onNavigateToMap,
  className,
}) => {
  const [filterLevel, setFilterLevel] = useState<string>('ALL');
  const [isExpanded, setIsExpanded] = useState<boolean>(true);

  // Filtered cameras based on priority filter
  const displayedCameras = useMemo(() => {
    let list = [...prioritizedCameras];

    if (!sortByPriority) {
      // Sort alphabetically by camera_id when priority sort is toggled off
      list.sort((a, b) => (a.camera.camera_id || '').localeCompare(b.camera.camera_id || ''));
    }

    if (filterLevel === 'ALL') {
      return list;
    }
    if (filterLevel === 'ALERTED') {
      return list.filter((item) => item.activeAlertCount > 0);
    }
    if (filterLevel === 'CLEAR') {
      return list.filter((item) => item.priorityLevel === 'CLEAR');
    }
    if (filterLevel === 'OFFLINE') {
      return list.filter((item) => item.isOfflineOrError);
    }
    return list.filter((item) => item.priorityLevel === filterLevel);
  }, [prioritizedCameras, sortByPriority, filterLevel]);

  return (
    <div
      className={cn(
        'p-3.5 bg-surveillance-900/90 border border-surveillance-800 rounded-lg shadow-sm space-y-3',
        className
      )}
      data-testid="camera-priority-panel"
      aria-label="Tactical Camera Prioritization Panel"
    >
      {/* 1. Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 bg-tactical-amber/10 border border-tactical-amber/30 rounded text-tactical-amber">
            <ShieldAlert className="w-4 h-4" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xs font-bold tracking-wider text-surveillance-100 uppercase font-mono">
                Tactical Camera Prioritization
              </h2>
              <span className="text-[10px] px-1.5 py-0.2 rounded bg-surveillance-800 border border-surveillance-700 text-surveillance-400 font-mono">
                M24
              </span>
            </div>
            <p className="text-[11px] text-surveillance-400 font-mono">
              Threat-ordered surveillance units • Real-time deterministic alert ranking
            </p>
          </div>
        </div>

        {/* Action Controls: Sort Toggle, Collapse Toggle, Refresh */}
        <div className="flex items-center gap-2 flex-wrap">
          <Button
            size="sm"
            variant="outline"
            onClick={onToggleSortByPriority}
            className={cn(
              'text-[11px] h-7 px-2 font-mono',
              sortByPriority
                ? 'border-tactical-cyan/40 text-tactical-cyan bg-tactical-cyan/10'
                : 'border-surveillance-700 text-surveillance-400'
            )}
            title={sortByPriority ? 'Currently sorted by tactical priority' : 'Currently sorted by camera ID'}
            aria-label={`Toggle sort order. Currently ${sortByPriority ? 'Tactical Priority' : 'Camera ID'}`}
            data-testid="toggle-priority-sort-btn"
          >
            <ArrowUpDown className="w-3 h-3 mr-1" aria-hidden="true" />
            {sortByPriority ? 'Priority Sorted' : 'ID Order'}
          </Button>

          <Button
            size="sm"
            variant="ghost"
            onClick={onRefresh}
            isLoading={loading}
            title="Refresh priorities"
            aria-label="Refresh priorities"
            className="text-surveillance-400 hover:text-surveillance-200 h-7 w-7 p-0"
            data-testid="refresh-priorities-btn"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} aria-hidden="true" />
          </Button>

          <Button
            size="sm"
            variant="ghost"
            onClick={() => setIsExpanded((prev) => !prev)}
            title={isExpanded ? 'Collapse priority panel' : 'Expand priority panel'}
            aria-label={isExpanded ? 'Collapse priority panel' : 'Expand priority panel'}
            className="text-surveillance-400 hover:text-surveillance-200 h-7 w-7 p-0"
          >
            {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </Button>
        </div>
      </div>

      {/* 2. Priority Hierarchy Legend & Summary Badges */}
      {isExpanded && (
        <>
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 pt-1 border-t border-surveillance-800/60">
            <PriorityLegend />

            {/* Quick Filter Buttons */}
            <div className="flex items-center gap-1 overflow-x-auto text-[10px] font-mono scrollbar-none">
              <span className="text-surveillance-500 mr-1 flex items-center gap-0.5">
                <Filter className="w-3 h-3" /> Filter:
              </span>
              {[
                { id: 'ALL', label: `All (${summaryCounts.totalCameras})` },
                { id: 'ALERTED', label: `Alerts (${summaryCounts.totalActiveAlerts})` },
                { id: 'CRITICAL', label: `Crit (${summaryCounts.criticalCount})`, disabled: summaryCounts.criticalCount === 0 },
                { id: 'HIGH', label: `High (${summaryCounts.highCount})`, disabled: summaryCounts.highCount === 0 },
                { id: 'CLEAR', label: `Clear (${summaryCounts.clearCount})` },
                { id: 'OFFLINE', label: `Offline (${summaryCounts.offlineCount})` },
              ].map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setFilterLevel(f.id)}
                  disabled={f.disabled}
                  className={cn(
                    'px-2 py-0.5 rounded border transition-colors whitespace-nowrap',
                    filterLevel === f.id
                      ? 'bg-tactical-cyan/20 border-tactical-cyan/60 text-cyan-200 font-bold'
                      : 'bg-surveillance-950/60 border-surveillance-800 text-surveillance-400 hover:text-surveillance-200',
                    f.disabled && 'opacity-40 cursor-not-allowed'
                  )}
                  aria-label={`Filter by ${f.label}`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          {/* 3. States & Camera Cards Grid */}
          {loading && prioritizedCameras.length === 0 ? (
            <div className="py-8 flex items-center justify-center bg-surveillance-950/40 border border-surveillance-850 rounded">
              <LoadingState message="Calculating tactical camera priorities..." />
            </div>
          ) : error ? (
            <div
              role="alert"
              className="p-3 bg-tactical-rose/10 border border-tactical-rose/30 rounded flex items-center justify-between gap-3 text-xs text-tactical-rose font-mono"
              data-testid="priority-error-banner"
            >
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{error}</span>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={onRefresh}
                className="text-[11px] h-6 px-2 border-tactical-rose/40 text-tactical-rose hover:bg-tactical-rose/20"
              >
                Retry
              </Button>
            </div>
          ) : prioritizedCameras.length === 0 ? (
            <div
              className="py-8 text-center bg-surveillance-950/40 border border-surveillance-850 rounded font-mono text-xs text-surveillance-400"
              data-testid="priority-empty-state"
            >
              <CameraIcon className="w-6 h-6 mx-auto text-surveillance-600 mb-2" />
              <p>No cameras registered in perimeter network.</p>
            </div>
          ) : (
            <div className="space-y-2.5">
              {/* No-active-alert Truthful Advisory Banner */}
              {summaryCounts.totalActiveAlerts === 0 && (
                <div
                  className="flex items-center gap-2 p-2 bg-tactical-emerald/10 border border-tactical-emerald/30 rounded text-xs font-mono text-emerald-300"
                  data-testid="no-active-alerts-banner"
                >
                  <CheckCircle2 className="w-4 h-4 text-tactical-emerald flex-shrink-0" aria-hidden="true" />
                  <span>No active security alerts — all operational cameras currently clear.</span>
                </div>
              )}

              {/* Grid of Prioritized Camera Cards */}
              <div
                className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2.5"
                data-testid="prioritized-cameras-grid"
              >
                {displayedCameras.map((item) => (
                  <CameraPriorityCard
                    key={item.camera.camera_id}
                    item={item}
                    isSelected={item.camera.camera_id === selectedCameraId}
                    onSelectCamera={onSelectCamera}
                    onNavigateToAlerts={onNavigateToAlerts}
                    onNavigateToMap={onNavigateToMap}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};
