import React from 'react';
import { CameraPriorityBadge } from './CameraPriorityBadge';
import { ChevronRight, Shield } from 'lucide-react';
import type { CameraPriorityLevel } from '@/types/prioritization';

const LEGEND_LEVELS: CameraPriorityLevel[] = [
  'CRITICAL',
  'HIGH',
  'MEDIUM',
  'LOW',
  'CLEAR',
  'OFFLINE',
];

export const PriorityLegend: React.FC = () => {
  return (
    <div
      className="flex flex-wrap items-center gap-1.5 p-2 bg-surveillance-950/60 border border-surveillance-800/80 rounded-md text-[11px] font-mono text-surveillance-400"
      aria-label="Tactical Priority Legend"
      data-testid="priority-legend"
    >
      <div className="flex items-center gap-1 text-surveillance-300 font-bold uppercase mr-1">
        <Shield className="w-3.5 h-3.5 text-tactical-cyan" aria-hidden="true" />
        <span>Hierarchy:</span>
      </div>

      <div className="flex flex-wrap items-center gap-1">
        {LEGEND_LEVELS.map((level, idx) => (
          <React.Fragment key={level}>
            <CameraPriorityBadge level={level} size="sm" />
            {idx < LEGEND_LEVELS.length - 1 && (
              <ChevronRight
                className="w-3 h-3 text-surveillance-600 flex-shrink-0"
                aria-hidden="true"
              />
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};
