import React from 'react';
import { Header } from './Header';
import { LayoutDashboard, Bell, Video, Map, BarChart3, Settings } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface ShellProps {
  children?: React.ReactNode;
  activeNav?: string;
  onNavChange?: (nav: string) => void;
}

export const Shell: React.FC<ShellProps> = ({
  children,
  activeNav = 'foundation',
  onNavChange,
}) => {
  // Lightweight navigation placeholders for future modules M19–M24
  const navItems = [
    { id: 'cctv', label: 'Live CCTV', icon: Video, badge: 'M19' },
    { id: 'alerts', label: 'Alert Center', icon: Bell, badge: 'M20' },
    { id: 'map', label: 'Tactical Map', icon: Map, badge: 'M21' },
    { id: 'stats', label: 'Analytics', icon: BarChart3, badge: 'M23', disabled: true },
    { id: 'foundation', label: 'Overview', icon: LayoutDashboard, badge: 'M18' },
    { id: 'config', label: 'Settings', icon: Settings, badge: 'M18' },
  ];

  return (
    <div className="min-h-screen bg-surveillance-950 text-surveillance-100 flex flex-col font-sans">
      {/* Top Application Header */}
      <Header />

      {/* Sub-Header Navigation Bar */}
      <nav aria-label="Main Navigation" className="bg-surveillance-900/80 border-b border-surveillance-800/80 px-4 lg:px-6">
        <div className="flex items-center space-x-1 overflow-x-auto py-1.5 scrollbar-none">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeNav === item.id;
            return (
              <button
                key={item.id}
                type="button"
                disabled={item.disabled}
                onClick={() => !item.disabled && onNavChange?.(item.id)}
                className={cn(
                  'flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap',
                  isActive
                    ? 'bg-surveillance-800 text-tactical-emerald border border-tactical-emerald/30 shadow-sm'
                    : item.disabled
                    ? 'text-surveillance-600 cursor-not-allowed opacity-60'
                    : 'text-surveillance-400 hover:text-surveillance-200 hover:bg-surveillance-850'
                )}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                <span>{item.label}</span>
                {item.badge && (
                  <span
                    className={cn(
                      'text-[9px] px-1 py-0.2 rounded font-mono uppercase tracking-tighter',
                      item.disabled
                        ? 'bg-surveillance-800/60 text-surveillance-600'
                        : 'bg-tactical-emerald/10 text-tactical-emerald border border-tactical-emerald/20'
                    )}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </nav>

      {/* Main Responsive Content Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8">
        {children}
      </main>

      {/* Security Surveillance Footer */}
      <footer className="bg-surveillance-900 border-t border-surveillance-800 px-4 lg:px-6 py-2.5 text-[11px] font-mono text-surveillance-500 flex flex-col sm:flex-row items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-tactical-emerald" />
          <span>IBVAP SURVEILLANCE FOUNDATION — OPERATIONAL</span>
        </div>
        <div className="flex items-center gap-4 text-surveillance-500">
          <span>SEC LEVEL: RESTRICTED</span>
          <span>SIH26187</span>
        </div>
      </footer>
    </div>
  );
};
