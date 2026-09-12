import React from 'react';
import { Plus, Minus, Maximize2, RefreshCw, Layers, ListFilter } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface MapControlsProps {
  onZoomIn?: () => void;
  onZoomOut?: () => void;
  onFitBounds?: () => void;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  onToggleLegend?: () => void;
  isLegendVisible?: boolean;
  onToggleUnmapped?: () => void;
  isUnmappedVisible?: boolean;
  unmappedCount?: number;
  className?: string;
}

export const MapControls: React.FC<MapControlsProps> = ({
  onZoomIn,
  onZoomOut,
  onFitBounds,
  onRefresh,
  isRefreshing = false,
  onToggleLegend,
  isLegendVisible = true,
  onToggleUnmapped,
  isUnmappedVisible = false,
  unmappedCount = 0,
  className,
}) => {
  return (
    <div
      role="toolbar"
      aria-label="Map Navigation and Display Controls"
      className={cn('flex flex-col gap-2 pointer-events-auto', className)}
      data-testid="map-controls"
    >
      {/* Zoom Controls */}
      <div className="flex flex-col bg-surveillance-900/95 border border-surveillance-800 rounded-lg shadow-xl overflow-hidden backdrop-blur-sm">
        <button
          type="button"
          onClick={onZoomIn}
          aria-label="Zoom In"
          title="Zoom In"
          className="p-2 hover:bg-surveillance-800 text-surveillance-300 hover:text-surveillance-100 transition-colors border-b border-surveillance-800/80 focus:outline-none focus:ring-1 focus:ring-tactical-emerald"
          data-testid="map-zoom-in-btn"
        >
          <Plus className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={onZoomOut}
          aria-label="Zoom Out"
          title="Zoom Out"
          className="p-2 hover:bg-surveillance-800 text-surveillance-300 hover:text-surveillance-100 transition-colors focus:outline-none focus:ring-1 focus:ring-tactical-emerald"
          data-testid="map-zoom-out-btn"
        >
          <Minus className="w-4 h-4" />
        </button>
      </div>

      {/* Layer / View Actions */}
      <div className="flex flex-col bg-surveillance-900/95 border border-surveillance-800 rounded-lg shadow-xl overflow-hidden backdrop-blur-sm">
        {onFitBounds && (
          <button
            type="button"
            onClick={onFitBounds}
            aria-label="Fit All Cameras in View"
            title="Fit All Cameras in View"
            className="p-2 hover:bg-surveillance-800 text-surveillance-300 hover:text-surveillance-100 transition-colors border-b border-surveillance-800/80 focus:outline-none focus:ring-1 focus:ring-tactical-emerald"
            data-testid="map-fit-bounds-btn"
          >
            <Maximize2 className="w-4 h-4" />
          </button>
        )}

        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={isRefreshing}
            aria-label="Refresh Camera Locations and Alerts"
            title="Refresh Map Telemetry"
            className="p-2 hover:bg-surveillance-800 text-surveillance-300 hover:text-surveillance-100 disabled:opacity-50 transition-colors border-b border-surveillance-800/80 focus:outline-none focus:ring-1 focus:ring-tactical-emerald"
            data-testid="map-refresh-btn"
          >
            <RefreshCw className={cn('w-4 h-4', isRefreshing && 'animate-spin text-tactical-emerald')} />
          </button>
        )}

        {onToggleLegend && (
          <button
            type="button"
            onClick={onToggleLegend}
            aria-label={isLegendVisible ? 'Hide Map Legend' : 'Show Map Legend'}
            title={isLegendVisible ? 'Hide Legend' : 'Show Legend'}
            className={cn(
              'p-2 hover:bg-surveillance-800 transition-colors focus:outline-none focus:ring-1 focus:ring-tactical-emerald',
              isLegendVisible
                ? 'text-tactical-emerald bg-surveillance-850'
                : 'text-surveillance-400 hover:text-surveillance-100'
            )}
            data-testid="map-toggle-legend-btn"
          >
            <Layers className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Unmapped Units Toggle Badge */}
      {unmappedCount > 0 && onToggleUnmapped && (
        <button
          type="button"
          onClick={onToggleUnmapped}
          aria-label={`${unmappedCount} cameras without GPS coordinates. Click to view.`}
          className={cn(
            'flex items-center gap-1.5 px-2 py-1.5 rounded-lg border shadow-xl text-[11px] font-mono transition-colors focus:outline-none focus:ring-1 focus:ring-tactical-amber',
            isUnmappedVisible
              ? 'bg-tactical-amber/20 border-tactical-amber/60 text-amber-300'
              : 'bg-surveillance-900/95 border-surveillance-800 text-surveillance-400 hover:text-surveillance-200'
          )}
          data-testid="map-toggle-unmapped-btn"
        >
          <ListFilter className="w-3.5 h-3.5 text-tactical-amber flex-shrink-0" />
          <span>Unmapped ({unmappedCount})</span>
        </button>
      )}
    </div>
  );
};
