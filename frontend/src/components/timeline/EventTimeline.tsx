import React, { useState, useMemo } from 'react';
import { TimelineFilters } from './TimelineFilters';
import { TimelineEvent } from './TimelineEvent';
import { TimelineLoading } from './TimelineLoading';
import { TimelineEmpty } from './TimelineEmpty';
import { Button } from '@/components/common/Button';
import {
  eventMatchesCategory,
  categorizeEvent,
  type TimelineFilterCategory,
  type TimelineSortOrder,
} from '@/types/timeline';
import {
  Crosshair,
  User,
  Car,
  Camera,
  Calendar,
  AlertTriangle,
  RefreshCw,
  ArrowLeft,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import type { Event, Track } from '@/types/api';

export interface EventTimelineProps {
  trackId: number | string;
  events: Event[];
  track?: Track | null;
  loading?: boolean;
  error?: string | null;
  cameraNameMap?: Record<string, string>;
  onRefresh?: () => void;
  onBack?: () => void;
  className?: string;
}

export const EventTimeline: React.FC<EventTimelineProps> = ({
  trackId,
  events,
  track,
  loading = false,
  error = null,
  cameraNameMap = {},
  onRefresh,
  onBack,
  className,
}) => {
  const [activeCategory, setActiveCategory] = useState<TimelineFilterCategory>('ALL');
  const [sortOrder, setSortOrder] = useState<TimelineSortOrder>('newest');

  // Ensure events is always safely treated as an array
  const safeEvents = useMemo(() => (Array.isArray(events) ? events : []), [events]);

  // 1. Calculate category counts for all loaded real events
  const categoryCounts = useMemo(() => {
    const counts: Record<TimelineFilterCategory, number> = {
      ALL: safeEvents.length,
      ALERTS: 0,
      BREACH: 0,
      LOITERING: 0,
      ZONE: 0,
      MOVEMENT: 0,
      OTHER: 0,
    };

    safeEvents.forEach((ev) => {
      const cat = categorizeEvent(ev);
      const details = ev.details || {};

      if (
        cat === 'BREACH' ||
        cat === 'LOITERING' ||
        cat === 'ALERTS' ||
        Boolean(details.severity) ||
        Boolean(details.alert_id)
      ) {
        counts.ALERTS += 1;
      }

      if (cat in counts && cat !== 'ALL' && cat !== 'ALERTS') {
        counts[cat] += 1;
      }
    });

    return counts;
  }, [events]);

  // 2. Filter & Sort events
  const filteredEvents = useMemo(() => {
    const matched = safeEvents.filter((ev) => eventMatchesCategory(ev, activeCategory));

    return [...matched].sort((a, b) => {
      const timeA = new Date(a.timestamp).getTime();
      const timeB = new Date(b.timestamp).getTime();

      if (sortOrder === 'newest') {
        if (timeA !== timeB) return timeB - timeA;
        return b.id - a.id;
      } else {
        if (timeA !== timeB) return timeA - timeB;
        return a.id - b.id;
      }
    });
  }, [safeEvents, activeCategory, sortOrder]);

  // 3. Track Classification Icon
  const rawClassName = (track?.class_name || 'person').toLowerCase();
  const isVehicle =
    rawClassName.includes('vehicle') ||
    rawClassName.includes('car') ||
    rawClassName.includes('truck') ||
    rawClassName.includes('bus');

  const cameraDisplay = useMemo(() => {
    if (!track?.camera_id) return null;
    const cidStr = String(track.camera_id);
    return cameraNameMap[cidStr] || `CAM-${track.camera_id}`;
  }, [track?.camera_id, cameraNameMap]);

  return (
    <div
      className={cn('space-y-4 font-sans', className)}
      data-testid="event-timeline-container"
    >
      {/* 1. Track Context Summary Header Card */}
      <div
        className="p-4 bg-surveillance-900/95 border border-surveillance-800 rounded-lg shadow-sm font-mono text-xs"
        data-testid="track-context-header"
      >
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 mb-3 border-b border-surveillance-800">
          <div className="flex items-center gap-3">
            {onBack && (
              <Button
                variant="secondary"
                size="sm"
                onClick={onBack}
                aria-label="Return to previous screen"
                className="px-2.5 py-1.5 text-xs text-surveillance-300 hover:text-white"
                data-testid="timeline-back-btn"
              >
                <ArrowLeft className="w-3.5 h-3.5 mr-1" aria-hidden="true" />
                Back
              </Button>
            )}

            <div className="p-2 bg-tactical-cyan/15 border border-tactical-cyan/30 rounded text-tactical-cyan">
              <Crosshair className="w-5 h-5" aria-hidden="true" />
            </div>

            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-base font-bold text-surveillance-100 tracking-wider">
                  TRACK #{trackId}
                </h2>
                <span
                  className={cn(
                    'flex items-center gap-1 text-[10px] px-2 py-0.5 rounded border uppercase font-bold',
                    isVehicle
                      ? 'bg-tactical-amber/15 text-tactical-amber border-tactical-amber/30'
                      : 'bg-tactical-emerald/15 text-tactical-emerald border-tactical-emerald/30'
                  )}
                  data-testid="track-class-badge"
                >
                  {isVehicle ? (
                    <Car className="w-3 h-3" aria-hidden="true" />
                  ) : (
                    <User className="w-3 h-3" aria-hidden="true" />
                  )}
                  <span>{(track?.class_name || 'TARGET').toUpperCase()}</span>
                </span>

                {track?.status && (
                  <span
                    className={cn(
                      'text-[10px] px-1.5 py-0.5 rounded border uppercase font-semibold',
                      track.status === 'ACTIVE'
                        ? 'bg-tactical-emerald/10 text-tactical-emerald border-tactical-emerald/30 animate-pulse'
                        : 'bg-surveillance-800 text-surveillance-400 border-surveillance-700'
                    )}
                    data-testid="track-status-badge"
                  >
                    {track.status}
                  </span>
                )}
              </div>

              <p className="text-[11px] text-surveillance-400 mt-0.5">
                Target chronological activity sequence & audit ledger
              </p>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            {onRefresh && (
              <Button
                variant="secondary"
                size="sm"
                onClick={onRefresh}
                isLoading={loading}
                aria-label="Refresh track events"
                className="text-xs px-3 py-1.5"
                data-testid="timeline-refresh-btn"
              >
                <RefreshCw className={cn('w-3.5 h-3.5 mr-1', loading && 'animate-spin')} aria-hidden="true" />
                Refresh
              </Button>
            )}
          </div>
        </div>

        {/* Telemetry Metrics Row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-[11px] text-surveillance-300">
          <div className="p-2 bg-surveillance-950/60 rounded border border-surveillance-850">
            <span className="text-[10px] text-surveillance-500 uppercase block mb-0.5">Total Events</span>
            <span className="text-sm font-bold text-surveillance-100" data-testid="timeline-events-count">
              {safeEvents.length}
            </span>
          </div>

          <div className="p-2 bg-surveillance-950/60 rounded border border-surveillance-850">
            <span className="text-[10px] text-surveillance-500 uppercase block mb-0.5">Associated Camera</span>
            <div className="flex items-center gap-1 text-surveillance-200 truncate">
              <Camera className="w-3 h-3 text-surveillance-500 flex-shrink-0" aria-hidden="true" />
              <span className="truncate">{cameraDisplay || 'Perimeter Camera'}</span>
            </div>
          </div>

          <div className="p-2 bg-surveillance-950/60 rounded border border-surveillance-850">
            <span className="text-[10px] text-surveillance-500 uppercase block mb-0.5">First Seen</span>
            <div className="flex items-center gap-1 text-surveillance-200">
              <Calendar className="w-3 h-3 text-surveillance-500 flex-shrink-0" aria-hidden="true" />
              <span className="truncate">
                {track?.first_seen
                  ? new Date(track.first_seen).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
                  : safeEvents.length > 0
                  ? new Date(safeEvents[0].timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
                  : '—'}
              </span>
            </div>
          </div>

          <div className="p-2 bg-surveillance-950/60 rounded border border-surveillance-850">
            <span className="text-[10px] text-surveillance-500 uppercase block mb-0.5">Last Seen</span>
            <div className="flex items-center gap-1 text-surveillance-200">
              <Calendar className="w-3 h-3 text-surveillance-500 flex-shrink-0" aria-hidden="true" />
              <span className="truncate">
                {track?.last_seen
                  ? new Date(track.last_seen).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
                  : safeEvents.length > 0
                  ? new Date(safeEvents[safeEvents.length - 1].timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
                  : '—'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 2. Error State */}
      {error && (
        <div
          role="alert"
          className="p-4 bg-tactical-rose/15 border border-tactical-rose/40 rounded-lg text-xs font-mono text-rose-200 flex items-start gap-3"
          data-testid="timeline-error-state"
        >
          <AlertTriangle className="w-5 h-5 text-tactical-rose flex-shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1">
            <h4 className="font-bold uppercase tracking-wider text-tactical-rose">
              Unable to load event history
            </h4>
            <p className="mt-1 text-surveillance-300">
              {error}
            </p>
            {onRefresh && (
              <Button
                variant="secondary"
                size="sm"
                onClick={onRefresh}
                className="mt-3 text-xs"
                data-testid="timeline-retry-btn"
              >
                Retry Request
              </Button>
            )}
          </div>
        </div>
      )}

      {/* 3. Loading State */}
      {loading && !error && <TimelineLoading />}

      {/* 4. Loaded Content */}
      {!loading && !error && (
        <>
          {safeEvents.length === 0 ? (
            <TimelineEmpty onRefresh={onRefresh} />
          ) : (
            <>
              {/* Category Filter & Sorting Controls */}
              <TimelineFilters
                activeCategory={activeCategory}
                onSelectCategory={setActiveCategory}
                sortOrder={sortOrder}
                onToggleSortOrder={() =>
                  setSortOrder(sortOrder === 'newest' ? 'oldest' : 'newest')
                }
                categoryCounts={categoryCounts}
              />

              {/* Filtered Empty State */}
              {filteredEvents.length === 0 ? (
                <TimelineEmpty
                  isFiltered
                  onClearFilters={() => setActiveCategory('ALL')}
                />
              ) : (
                /* Vertical Timeline Node Sequence */
                <div
                  role="list"
                  aria-label={`Chronological events for track ${trackId}`}
                  className="space-y-0 pt-2"
                  data-testid="timeline-events-list"
                >
                  {filteredEvents.map((ev, index) => (
                    <TimelineEvent
                      key={ev.id || `${ev.event_type}_${ev.timestamp}_${index}`}
                      event={ev}
                      cameraName={ev.camera_id ? cameraNameMap[String(ev.camera_id)] : undefined}
                      isFirst={index === 0}
                      isLast={index === filteredEvents.length - 1}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
};
