import React from 'react';
import type { StatsData } from '@/types/websocket';
import { Activity, Gauge, Users, Eye } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface LiveStatsProps {
  stats: StatsData | null;
  frameCount?: number;
  className?: string;
}

export const LiveStats: React.FC<LiveStatsProps> = ({
  stats,
  frameCount = 0,
  className,
}) => {
  const fps = stats?.fps ?? 0.0;
  const activeTracks = stats?.active_tracks ?? 0;
  const totalDetections = stats?.total_detections ?? 0;
  const connectedClients = stats?.connected_clients ?? 0;

  return (
    <div
      className={cn(
        'grid grid-cols-2 sm:grid-cols-4 gap-3 bg-surveillance-900/90 border border-surveillance-800 rounded-lg p-3 font-mono text-xs',
        className
      )}
      data-testid="live-stats-bar"
    >
      {/* 1. FPS */}
      <div className="flex items-center gap-2.5 p-2 bg-surveillance-950/60 rounded border border-surveillance-800/60">
        <div className="p-1.5 bg-tactical-emerald/10 border border-tactical-emerald/20 rounded text-tactical-emerald">
          <Gauge className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[10px] text-surveillance-400 uppercase tracking-wider">Stream FPS</div>
          <div className="text-sm font-bold text-surveillance-100">{fps > 0 ? fps.toFixed(1) : '—'}</div>
        </div>
      </div>

      {/* 2. Active Tracks */}
      <div className="flex items-center gap-2.5 p-2 bg-surveillance-950/60 rounded border border-surveillance-800/60">
        <div className="p-1.5 bg-tactical-cyan/10 border border-tactical-cyan/20 rounded text-tactical-cyan">
          <Activity className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[10px] text-surveillance-400 uppercase tracking-wider">Active Tracks</div>
          <div className="text-sm font-bold text-surveillance-100">{activeTracks}</div>
        </div>
      </div>

      {/* 3. Total Detections */}
      <div className="flex items-center gap-2.5 p-2 bg-surveillance-950/60 rounded border border-surveillance-800/60">
        <div className="p-1.5 bg-tactical-amber/10 border border-tactical-amber/20 rounded text-tactical-amber">
          <Eye className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[10px] text-surveillance-400 uppercase tracking-wider">Detections</div>
          <div className="text-sm font-bold text-surveillance-100">{totalDetections}</div>
        </div>
      </div>

      {/* 4. Stream Clients / Frame Count */}
      <div className="flex items-center gap-2.5 p-2 bg-surveillance-950/60 rounded border border-surveillance-800/60">
        <div className="p-1.5 bg-surveillance-800 border border-surveillance-700 rounded text-surveillance-300">
          <Users className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[10px] text-surveillance-400 uppercase tracking-wider">Subscribers</div>
          <div className="text-sm font-bold text-surveillance-100">
            {connectedClients} <span className="text-[10px] font-normal text-surveillance-500">(# {frameCount})</span>
          </div>
        </div>
      </div>
    </div>
  );
};
