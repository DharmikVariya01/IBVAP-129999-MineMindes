import React, { useState } from 'react';
import { TimelineEventIcon } from './TimelineEventIcon';
import { categorizeEvent } from '@/types/timeline';
import {
  Camera,
  Layers,
  Film,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Clock,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import type { Event } from '@/types/api';

export interface TimelineEventProps {
  event: Event;
  cameraName?: string;
  isFirst?: boolean;
  isLast?: boolean;
  className?: string;
}

export function formatEventTime(isoString: string): { time: string; date: string } {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return { time: isoString, date: '' };
    return {
      time: d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }),
      date: d.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' }),
    };
  } catch {
    return { time: isoString, date: '' };
  }
}

/**
 * Builds a concise, strictly truthful human description without inventing data.
 */
export function generateEventDescription(event: Event): string {
  const details = event.details || {};
  const type = (event.event_type || '').toUpperCase();

  // If a descriptive message was provided by the backend, prioritize it
  if (typeof details.message === 'string' && details.message.trim()) {
    return details.message;
  }
  if (typeof details.description === 'string' && details.description.trim()) {
    return details.description;
  }
  if (typeof details.reason === 'string' && details.reason.trim()) {
    return details.reason;
  }

  // Structured factual synthesis
  if (type === 'FENCE_BREACH') {
    const step = details.breach_step !== undefined ? ` (Stage ${details.breach_step})` : '';
    const fence = details.fence_name ? ` at ${details.fence_name}` : '';
    return `Perimeter fence line breach detected${fence}${step}`;
  }

  if (type === 'LOITERING') {
    const dur = details.duration !== undefined ? ` for ${details.duration}s` : '';
    const thresh = details.threshold ? ` (threshold ${details.threshold}s)` : '';
    return `Stationary loitering pattern identified${dur}${thresh}`;
  }

  if (type === 'ZONE_ENTRY') {
    const zoneName = (details.zone_name as string) || (event.zone_id ? `Zone #${event.zone_id}` : 'perimeter');
    return `Target entered ${zoneName}`;
  }

  if (type === 'ZONE_EXIT') {
    const zoneName = (details.zone_name as string) || (event.zone_id ? `Zone #${event.zone_id}` : 'perimeter');
    return `Target exited ${zoneName}`;
  }

  if (type === 'ZONE_CHANGE') {
    const fromZone = details.from_zone || 'Unknown';
    const toZone = details.to_zone || (event.zone_id ? `Zone #${event.zone_id}` : 'Restricted');
    return `Zone transition: ${fromZone} → ${toZone}`;
  }

  if (type === 'MOTION' || type === 'MOVEMENT') {
    const speed = details.speed !== undefined ? ` speed: ${details.speed}px/f` : '';
    const dir = details.direction ? ` heading ${details.direction}` : '';
    return `Perimeter movement recorded${dir}${speed}`;
  }

  if (type === 'TRACK_CREATED') {
    return 'Target track session established by ByteTrack';
  }

  return `${(event.event_type || 'PIPELINE_EVENT').replace(/_/g, ' ')} detected`;
}

export const TimelineEvent: React.FC<TimelineEventProps> = ({
  event,
  cameraName,
  isFirst = false,
  isLast = false,
  className,
}) => {
  const [showRawDetails, setShowRawDetails] = useState<boolean>(false);
  const category = categorizeEvent(event);
  const { time, date } = formatEventTime(event.timestamp);
  const description = generateEventDescription(event);

  const formattedType = (event.event_type || 'UNKNOWN').replace(/_/g, ' ').toUpperCase();
  const details = event.details || {};
  const hasRawDetails = details && Object.keys(details).length > 0;

  const severity = (details.severity as string) || null;
  const alertId = (details.alert_id as string) || null;
  const cameraDisplay = cameraName || (event.camera_id ? `CAM-${event.camera_id}` : null);
  const zoneDisplay = (details.zone_name as string) || (event.zone_id ? `Zone #${event.zone_id}` : null);

  return (
    <div
      role="listitem"
      aria-label={`Event ${formattedType} at ${time}`}
      className={cn('relative flex items-start gap-3 sm:gap-4 group', className)}
      data-testid={`timeline-event-${event.id}`}
    >
      {/* 1. Left Vertical Connector Line & Tactical Node Icon */}
      <div className="relative flex flex-col items-center flex-shrink-0 self-stretch">
        <TimelineEventIcon
          category={category}
          eventType={event.event_type}
          isFirst={isFirst}
        />
        {!isLast && (
          <div
            className="w-0.5 flex-1 bg-surveillance-800 group-hover:bg-surveillance-700 transition-colors my-1"
            aria-hidden="true"
          />
        )}
      </div>

      {/* 2. Main Event Content Card */}
      <div
        className={cn(
          'flex-1 mb-4 p-3.5 sm:p-4 rounded-lg border font-mono text-xs transition-all duration-150',
          isFirst
            ? 'bg-surveillance-900/95 border-surveillance-700 shadow-md ring-1 ring-tactical-emerald/30'
            : 'bg-surveillance-900/70 border-surveillance-800 hover:border-surveillance-750'
        )}
      >
        {/* Top Header Row: Event Type, Badges, Timestamp */}
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2 pb-2 border-b border-surveillance-800/80">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={cn(
                'text-xs font-bold tracking-wider uppercase',
                category === 'BREACH'
                  ? 'text-tactical-rose'
                  : category === 'LOITERING'
                  ? 'text-tactical-amber'
                  : category === 'ZONE'
                  ? 'text-tactical-cyan'
                  : category === 'MOVEMENT'
                  ? 'text-tactical-emerald'
                  : 'text-surveillance-100'
              )}
            >
              {formattedType}
            </span>

            {event.event_id && (
              <span className="text-[10px] px-1.5 py-0.2 rounded bg-surveillance-800 border border-surveillance-700 text-surveillance-400">
                {event.event_id}
              </span>
            )}

            {severity && (
              <span
                className={cn(
                  'text-[9px] px-1.5 py-0.2 rounded font-bold uppercase tracking-wider',
                  severity.toUpperCase() === 'CRITICAL'
                    ? 'bg-tactical-rose/20 text-tactical-rose border border-tactical-rose/40'
                    : 'bg-tactical-amber/20 text-tactical-amber border border-tactical-amber/40'
                )}
                data-testid="event-severity-badge"
              >
                {severity}
              </span>
            )}

            {isFirst && (
              <span className="text-[9px] px-1.5 py-0.2 rounded font-bold bg-tactical-emerald/20 text-tactical-emerald border border-tactical-emerald/30 uppercase tracking-widest">
                LATEST
              </span>
            )}
          </div>

          {/* Timestamp Info */}
          <div className="flex items-center gap-1.5 text-surveillance-400 text-[11px]">
            <Clock className="w-3.5 h-3.5 text-surveillance-500" aria-hidden="true" />
            <span className="text-surveillance-200 font-semibold">{time}</span>
            {date && <span className="text-surveillance-500 text-[10px]">({date})</span>}
          </div>
        </div>

        {/* Human-Readable Description */}
        <p className="text-xs font-sans text-surveillance-200 mb-3 leading-relaxed">
          {description}
        </p>

        {/* Spatial & Video Telemetry Badges */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-surveillance-850 text-[11px] text-surveillance-400">
          <div className="flex flex-wrap items-center gap-2.5">
            {cameraDisplay && (
              <div className="flex items-center gap-1 text-surveillance-300">
                <Camera className="w-3 h-3 text-surveillance-500" aria-hidden="true" />
                <span>{cameraDisplay}</span>
              </div>
            )}

            {zoneDisplay && (
              <div className="flex items-center gap-1 text-surveillance-300">
                <Layers className="w-3 h-3 text-tactical-cyan" aria-hidden="true" />
                <span>{zoneDisplay}</span>
              </div>
            )}

            {event.frame_id !== null && event.frame_id !== undefined && (
              <div className="flex items-center gap-1 text-surveillance-400">
                <Film className="w-3 h-3 text-surveillance-500" aria-hidden="true" />
                <span>Frame #{event.frame_id}</span>
              </div>
            )}

            {alertId && (
              <div className="flex items-center gap-1 text-tactical-rose">
                <AlertTriangle className="w-3 h-3" aria-hidden="true" />
                <span>Alert #{alertId}</span>
              </div>
            )}
          </div>

          {/* Raw Metadata Details Drawer Toggle */}
          {hasRawDetails && (
            <button
              type="button"
              onClick={() => setShowRawDetails(!showRawDetails)}
              aria-expanded={showRawDetails}
              aria-label={`Toggle raw event metadata for event ${event.id}`}
              className="flex items-center gap-1 text-[10px] text-surveillance-400 hover:text-surveillance-200 transition-colors py-0.5 px-1.5 rounded hover:bg-surveillance-800"
              data-testid={`toggle-raw-details-${event.id}`}
            >
              <span>{showRawDetails ? 'Hide Raw Details' : 'Raw Details'}</span>
              {showRawDetails ? (
                <ChevronUp className="w-3 h-3" aria-hidden="true" />
              ) : (
                <ChevronDown className="w-3 h-3" aria-hidden="true" />
              )}
            </button>
          )}
        </div>

        {/* Collapsible Raw Metadata JSON Viewer */}
        {showRawDetails && hasRawDetails && (
          <div
            className="mt-3 p-2.5 bg-surveillance-950 border border-surveillance-800 rounded font-mono text-[11px] text-surveillance-300 overflow-x-auto select-text"
            data-testid={`raw-details-box-${event.id}`}
          >
            <div className="text-[9px] text-surveillance-500 uppercase pb-1 mb-1 border-b border-surveillance-850 flex items-center justify-between">
              <span>RAW EVENT PAYLOAD</span>
              <span>DB ID: #{event.id}</span>
            </div>
            <pre className="text-surveillance-300 whitespace-pre-wrap break-all">
              {JSON.stringify(details, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};
