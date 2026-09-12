import React, { useEffect, useState } from 'react';
import { apiClient } from '@/services/api/client';
import type { Camera } from '@/types/api';
import { Badge, type BadgeProps } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { Camera as CameraIcon, RefreshCw, AlertCircle } from 'lucide-react';
import { cn } from '@/utils/cn';

import type { PrioritizedCamera } from '@/types/prioritization';
import { CameraPriorityBadge } from '@/components/prioritization/CameraPriorityBadge';
import { ArrowUpDown } from 'lucide-react';

export interface CameraSelectorProps {
  selectedCameraId: string | null;
  onSelectCamera: (cameraId: string) => void;
  disabled?: boolean;
  className?: string;
  prioritizedCameras?: PrioritizedCamera[];
  sortByPriority?: boolean;
  onToggleSortByPriority?: () => void;
}

export const CameraSelector: React.FC<CameraSelectorProps> = ({
  selectedCameraId,
  onSelectCamera,
  disabled = false,
  className,
  prioritizedCameras,
  sortByPriority = false,
  onToggleSortByPriority,
}) => {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState<boolean>(!prioritizedCameras);
  const [error, setError] = useState<string | null>(null);

  const fetchCameras = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.getCameras({ page: 1, page_size: 50 });
      setCameras(response.items || []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to fetch camera list';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (prioritizedCameras) {
      setCameras(prioritizedCameras.map((p) => p.camera));
      setLoading(false);
    } else {
      fetchCameras();
    }
  }, [prioritizedCameras]);

  const getStatusVariant = (status: string): NonNullable<BadgeProps['variant']> => {
    switch (status.toUpperCase()) {
      case 'ONLINE':
        return 'success';
      case 'CONNECTING':
        return 'high';
      case 'OFFLINE':
      case 'ERROR':
        return 'critical';
      default:
        return 'neutral';
    }
  };

  return (
    <div className={cn('flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5', className)}>
      <div className="flex items-center gap-2 text-surveillance-300 text-xs font-mono">
        <CameraIcon className="w-4 h-4 text-tactical-emerald flex-shrink-0" />
        <span className="font-semibold tracking-wide uppercase text-surveillance-200">Camera Feed:</span>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-surveillance-900 border border-surveillance-800 rounded text-xs text-surveillance-400 font-mono">
          <RefreshCw className="w-3.5 h-3.5 animate-spin text-tactical-emerald" />
          <span>Loading cameras...</span>
        </div>
      ) : error ? (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-tactical-rose/10 border border-tactical-rose/30 rounded text-xs text-tactical-rose font-mono">
          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
          <span className="truncate max-w-[200px]">{error}</span>
          <Button
            size="sm"
            variant="outline"
            onClick={fetchCameras}
            className="ml-1 text-[11px] h-6 px-1.5 border-tactical-rose/40 text-tactical-rose hover:bg-tactical-rose/20"
          >
            Retry
          </Button>
        </div>
      ) : cameras.length === 0 ? (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-surveillance-900 border border-surveillance-800 rounded text-xs text-surveillance-500 font-mono">
          <span>No cameras available</span>
          <Button
            size="sm"
            variant="ghost"
            onClick={fetchCameras}
            className="text-[11px] h-6 px-1.5 text-surveillance-400 hover:text-surveillance-200"
          >
            <RefreshCw className="w-3 h-3" />
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <div className="relative flex-1 sm:w-64">
            <select
              id="camera-select"
              aria-label="Select camera feed"
              value={selectedCameraId || ''}
              disabled={disabled}
              onChange={(e) => onSelectCamera(e.target.value)}
              className={cn(
                'w-full appearance-none bg-surveillance-900 border border-surveillance-700 text-surveillance-100 text-xs font-mono rounded px-3 py-1.5 pr-8',
                'focus:outline-none focus:border-tactical-emerald focus:ring-1 focus:ring-tactical-emerald/50',
                'disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer'
              )}
            >
              <option value="" disabled>
                -- Select Camera Feed --
              </option>
              {prioritizedCameras && sortByPriority
                ? prioritizedCameras.map((item) => (
                    <option key={item.camera.camera_id} value={item.camera.camera_id}>
                      #{item.rank} [{item.priorityLevel}
                      {item.activeAlertCount > 0 ? ` (${item.activeAlertCount})` : ''}]{' '}
                      {item.camera.name} ({item.camera.camera_id}) — [{item.camera.status}]
                    </option>
                  ))
                : cameras.map((cam) => (
                    <option key={cam.camera_id} value={cam.camera_id}>
                      {cam.name} ({cam.camera_id}) — [{cam.status}]
                    </option>
                  ))}
            </select>
            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-surveillance-400">
              <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 20 20">
                <path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" />
              </svg>
            </div>
          </div>

          {selectedCameraId && (() => {
            const current = cameras.find((c) => c.camera_id === selectedCameraId);
            if (!current) return null;
            const prioItem = prioritizedCameras?.find((p) => p.camera.camera_id === selectedCameraId);
            return (
              <div className="flex items-center gap-1.5">
                {prioItem && <CameraPriorityBadge level={prioItem.priorityLevel} size="sm" />}
                <Badge variant={getStatusVariant(current.status)} size="sm">
                  {current.status}
                </Badge>
              </div>
            );
          })()}

          {onToggleSortByPriority && (
            <Button
              size="sm"
              variant="ghost"
              onClick={onToggleSortByPriority}
              title={sortByPriority ? 'Sorting by priority' : 'Sorting by camera ID'}
              aria-label={`Toggle camera sort order. Currently ${sortByPriority ? 'Priority' : 'Normal'}`}
              className={cn(
                'h-8 px-2 text-xs font-mono',
                sortByPriority ? 'text-tactical-cyan' : 'text-surveillance-400 hover:text-surveillance-200'
              )}
              data-testid="cctv-sort-toggle-btn"
            >
              <ArrowUpDown className="w-3.5 h-3.5" />
            </Button>
          )}

          <Button
            size="sm"
            variant="ghost"
            onClick={fetchCameras}
            title="Refresh cameras list"
            aria-label="Refresh cameras list"
            className="text-surveillance-400 hover:text-surveillance-200 h-8 w-8 p-0"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </Button>
        </div>
      )}
    </div>
  );
};
