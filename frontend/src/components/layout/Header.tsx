import React from 'react';
import { ShieldAlert, Radio, Activity } from 'lucide-react';
import { StatusIndicator } from '@/components/common/StatusIndicator';

export interface HeaderProps {
  systemStatus?: 'online' | 'offline' | 'connecting' | 'error';
  version?: string;
}

export const Header: React.FC<HeaderProps> = ({
  systemStatus = 'online',
  version = 'v0.18.0',
}) => {
  return (
    <header className="bg-surveillance-900 border-b border-surveillance-800 px-4 lg:px-6 py-3 select-none">
      <div className="flex items-center justify-between">
        {/* Left: Branding & Platform Identity */}
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded bg-gradient-to-br from-tactical-emerald/20 to-tactical-cyan/20 border border-tactical-emerald/40 flex items-center justify-center text-tactical-emerald">
            <ShieldAlert className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold tracking-wider text-white font-mono">
                IBVAP
              </h1>
              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-surveillance-800 text-surveillance-300 border border-surveillance-700">
                SIH26187
              </span>
            </div>
            <p className="text-xs text-surveillance-400 hidden sm:block">
              Intelligent Border Video Analysis Platform
            </p>
          </div>
        </div>

        {/* Center/Right: Operational Telemetry & System Indicator */}
        <div className="flex items-center gap-4 text-xs font-mono">
          <div className="hidden md:flex items-center gap-4 text-surveillance-400 border-r border-surveillance-800 pr-4">
            <span className="flex items-center gap-1.5 text-surveillance-300">
              <Activity className="h-3.5 w-3.5 text-tactical-cyan" aria-hidden="true" />
              <span>CORE ACTIVE</span>
            </span>
            <span className="flex items-center gap-1.5 text-surveillance-400">
              <Radio className="h-3.5 w-3.5 text-tactical-emerald" aria-hidden="true" />
              <span>STREAM READY</span>
            </span>
          </div>

          <div className="flex items-center gap-3">
            <StatusIndicator status={systemStatus} label="System" />
            <span className="text-surveillance-500 hidden sm:inline">|</span>
            <span className="text-[11px] text-surveillance-400 hidden sm:inline">{version}</span>
          </div>
        </div>
      </div>
    </header>
  );
};
