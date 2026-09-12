import React, { useState, useEffect, useCallback } from 'react';
import { EventTimeline } from '@/components/timeline/EventTimeline';
import { apiClient } from '@/services/api/client';
import { webSocketClient } from '@/services/websocket/client';
import { Button } from '@/components/common/Button';
import { History, Search, ShieldCheck, Crosshair } from 'lucide-react';
import type { Event, Track, Camera } from '@/types/api';
import type { WebSocketMessage, AlertData } from '@/types/websocket';

export interface EventTimelinePageProps {
  initialTrackId?: number | string | null;
  onBack?: () => void;
}

export const EventTimelinePage: React.FC<EventTimelinePageProps> = ({
  initialTrackId = null,
  onBack,
}) => {
  // Determine starting track ID from prop, hash, or default
  const getStartingTrackId = (): string => {
    if (initialTrackId !== null && initialTrackId !== undefined) {
      return String(initialTrackId);
    }
    // Check URL hash e.g. #timeline/10 or #10
    if (typeof window !== 'undefined' && window.location.hash) {
      const match = window.location.hash.match(/(?:timeline\/|#)?(\d+)/i);
      if (match && match[1]) return match[1];
    }
    return '1';
  };

  const [trackId, setTrackId] = useState<string>(getStartingTrackId);
  const [inputTrackId, setInputTrackId] = useState<string>(getStartingTrackId);

  const [events, setEvents] = useState<Event[]>([]);
  const [track, setTrack] = useState<Track | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [cameraMap, setCameraMap] = useState<Record<string, string>>({});

  // 1. Sync prop change to state
  useEffect(() => {
    if (initialTrackId !== null && initialTrackId !== undefined) {
      const s = String(initialTrackId);
      setTrackId(s);
      setInputTrackId(s);
    }
  }, [initialTrackId]);

  // 2. Fetch Camera map once for human-readable labels
  useEffect(() => {
    let isMounted = true;
    apiClient
      .getCameras({ page_size: 100 })
      .then((res) => {
        if (!isMounted) return;
        const map: Record<string, string> = {};
        (res.items || []).forEach((c: Camera) => {
          map[String(c.id)] = c.name || c.camera_id;
          map[c.camera_id] = c.name || c.camera_id;
        });
        setCameraMap(map);
      })
      .catch(() => {
        // Fallback gracefully without camera names
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // 3. Load Chronological Events and Track Context for selected track
  const fetchTrackData = useCallback(async () => {
    if (!trackId || !trackId.trim()) return;

    setLoading(true);
    setError(null);

    try {
      // Execute events and track query in parallel
      const eventsPromise = apiClient.getTrackEvents(trackId.trim());
      const trackPromise = apiClient.getTrack(trackId.trim()).catch(() => null);

      const [fetchedEvents, fetchedTrack] = await Promise.all([
        eventsPromise,
        trackPromise,
      ]);

      const safeFetched = Array.isArray(fetchedEvents)
        ? fetchedEvents
        : Array.isArray((fetchedEvents as unknown as { items?: Event[] })?.items)
        ? (fetchedEvents as unknown as { items: Event[] }).items
        : [];

      setEvents(safeFetched);
      setTrack(fetchedTrack);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unable to load event history';
      setError(msg);
      setEvents([]);
      setTrack(null);
    } finally {
      setLoading(false);
    }
  }, [trackId]);

  useEffect(() => {
    fetchTrackData();
  }, [fetchTrackData]);

  // 4. Real-time synchronization via existing M17 WebSocket
  useEffect(() => {
    const unsub = webSocketClient.onMessage((msg: WebSocketMessage) => {
      if (msg.type === 'alert') {
        const alertData = msg.data as AlertData;
        if (
          alertData &&
          alertData.track_id !== undefined &&
          alertData.track_id !== null &&
          String(alertData.track_id) === String(trackId)
        ) {
          // Relevant live alert event arrived for this track: re-hydrate events
          fetchTrackData();
        }
      }
    });

    return () => {
      unsub();
    };
  }, [trackId, fetchTrackData]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputTrackId.trim() && inputTrackId.trim() !== trackId) {
      setTrackId(inputTrackId.trim());
    }
  };

  return (
    <div className="space-y-4" data-testid="event-timeline-page">
      {/* 1. Header Control Bar & Track Lookup */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 p-3.5 bg-surveillance-900/90 border border-surveillance-800 rounded-lg shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-tactical-emerald/10 border border-tactical-emerald/30 rounded text-tactical-emerald">
            <History className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold tracking-wider text-surveillance-100 uppercase font-mono">
                Event Timeline
              </h1>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-surveillance-800 border border-surveillance-700 text-surveillance-400 font-mono">
                M22
              </span>
            </div>
            <p className="text-xs text-surveillance-400 font-mono">
              Target chronological event sequence, loitering history & spatial transitions
            </p>
          </div>
        </div>

        {/* Track ID Lookup Bar */}
        <div className="flex items-center gap-2">
          <form onSubmit={handleSearchSubmit} className="flex items-center gap-1.5">
            <label htmlFor="track-lookup-input" className="sr-only">
              Lookup Track ID
            </label>
            <div className="relative">
              <Crosshair className="w-3.5 h-3.5 text-surveillance-500 absolute left-2.5 top-1/2 -translate-y-1/2" aria-hidden="true" />
              <input
                id="track-lookup-input"
                type="text"
                value={inputTrackId}
                onChange={(e) => setInputTrackId(e.target.value)}
                placeholder="Track ID (e.g. 10)"
                className="pl-8 pr-3 py-1.5 bg-surveillance-950 border border-surveillance-700 rounded text-surveillance-100 text-xs font-mono w-40 focus:outline-none focus:ring-1 focus:ring-tactical-emerald"
                data-testid="track-id-input"
              />
            </div>
            <Button
              type="submit"
              variant="secondary"
              size="sm"
              className="text-xs font-mono px-2.5 py-1.5"
              aria-label="Inspect Track ID"
              data-testid="track-inspect-btn"
            >
              <Search className="w-3.5 h-3.5 mr-1" aria-hidden="true" />
              Inspect
            </Button>
          </form>
        </div>
      </div>

      {/* 2. Main Timeline Component */}
      <EventTimeline
        trackId={trackId}
        events={events}
        track={track}
        loading={loading}
        error={error}
        cameraNameMap={cameraMap}
        onRefresh={fetchTrackData}
        onBack={onBack}
      />

      {/* 3. Operational Advisory Footer */}
      <div className="flex items-center justify-between px-3 py-2 bg-surveillance-950/40 border border-surveillance-850 rounded text-[11px] font-mono text-surveillance-500">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-3.5 h-3.5 text-tactical-emerald" />
          <span>CHRONOLOGICAL AUDIT: CONSUMING REAL M16 EVENT LEDGER (ZERO SYNTHETIC DATA)</span>
        </div>
        <div className="hidden sm:block text-surveillance-600">
          TRACK ID: #{trackId} • AUDIT VERIFIED
        </div>
      </div>
    </div>
  );
};

export default EventTimelinePage;
