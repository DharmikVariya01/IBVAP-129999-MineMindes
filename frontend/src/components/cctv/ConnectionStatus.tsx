import React from 'react';
import type { ConnectionState } from '@/types/websocket';
import { StatusIndicator, StatusType } from '@/components/common/StatusIndicator';
import { cn } from '@/utils/cn';

export interface ConnectionStatusProps {
  state: ConnectionState;
  className?: string;
  showLabel?: boolean;
}

export const ConnectionStatus: React.FC<ConnectionStatusProps> = ({
  state,
  className,
  showLabel = true,
}) => {
  const mapStateToStatus = (s: ConnectionState): { status: StatusType; label: string } => {
    switch (s) {
      case 'CONNECTED':
        return { status: 'online', label: 'Stream Connected' };
      case 'CONNECTING':
        return { status: 'connecting', label: 'Connecting' };
      case 'RECONNECTING':
        return { status: 'connecting', label: 'Reconnecting' };
      case 'DISCONNECTED':
      case 'CLOSED':
        return { status: 'offline', label: 'Disconnected' };
      default:
        return { status: 'error', label: 'Stream Error' };
    }
  };

  const { status, label } = mapStateToStatus(state);

  return (
    <div
      className={cn(
        'inline-flex items-center gap-2 px-2.5 py-1 bg-surveillance-900 border border-surveillance-800 rounded text-xs font-mono',
        className
      )}
      data-testid="connection-status-badge"
    >
      <StatusIndicator status={status} pulse={status !== 'offline'} label="" />
      {showLabel && (
        <span className="text-surveillance-200 uppercase tracking-tight text-[11px] font-semibold">
          {label}
        </span>
      )}
    </div>
  );
};
