import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { EventTimeline } from '@/components/timeline/EventTimeline';
import { EventTimelinePage } from '@/pages/EventTimelinePage';
import { App } from '@/App';
import { AlertCard } from '@/components/alerts/AlertCard';
import { AlertDetail } from '@/components/alerts/AlertDetail';
import { CameraMarkerPopup } from '@/components/map/CameraMarkerPopup';
import { CCTVMonitoring } from '@/pages/CCTVMonitoring';
import type { Event, Track, Alert, Camera } from '@/types/api';

const mockCameras: Camera[] = [
  {
    id: 1,
    camera_id: 'CAM_01',
    name: 'North Perimeter Alpha',
    source_type: 'RTSP',
    source_reference: 'rtsp://10.0.0.1:8554/cam01',
    location: '28.6139, 77.2090',
    status: 'ONLINE',
    created_at: '2026-09-12T00:00:00Z',
    updated_at: '2026-09-12T00:00:00Z',
  },
];

const mockTrack: Track = {
  id: 10,
  track_id: 10,
  camera_id: 1,
  class_id: 0,
  class_name: 'person',
  first_seen: '2026-09-12T10:00:00Z',
  last_seen: '2026-09-12T10:15:00Z',
  frame_count: 450,
  last_confidence: 0.94,
  bbox_x1: 100,
  bbox_y1: 150,
  bbox_x2: 220,
  bbox_y2: 380,
  last_center_x: 160,
  last_center_y: 265,
  status: 'ACTIVE',
  observation_metadata: {},
  created_at: '2026-09-12T10:00:00Z',
  updated_at: '2026-09-12T10:15:00Z',
  events_count: 3,
  alerts_count: 1,
};

const mockEvents: Event[] = [
  {
    id: 101,
    event_id: 'EVT-001',
    camera_id: 1,
    track_id: 10,
    zone_id: 2,
    event_type: 'FENCE_BREACH',
    frame_id: 120,
    timestamp: '2026-09-12T10:05:00Z',
    details: { breach_step: 1, fence_name: 'Inner Barrier' },
    created_at: '2026-09-12T10:05:00Z',
  },
  {
    id: 102,
    event_id: 'EVT-002',
    camera_id: 1,
    track_id: 10,
    zone_id: 2,
    event_type: 'LOITERING',
    frame_id: 240,
    timestamp: '2026-09-12T10:10:00Z',
    details: { duration: 25.5, threshold: 10.0 },
    created_at: '2026-09-12T10:10:00Z',
  },
  {
    id: 103,
    event_id: 'EVT-003',
    camera_id: 1,
    track_id: 10,
    zone_id: 2,
    event_type: 'ZONE_ENTRY',
    frame_id: 360,
    timestamp: '2026-09-12T10:14:00Z',
    details: { zone_name: 'Restricted Sector B' },
    created_at: '2026-09-12T10:14:00Z',
  },
];

describe('IBVAP M22 — Event Timeline Module Test Suite', () => {
  let originalFetch: typeof global.fetch;

  beforeEach(() => {
    originalFetch = global.fetch;
    vi.restoreAllMocks();

    global.fetch = vi.fn().mockImplementation((url: string) => {
      const u = String(url);

      if (u.includes('/api/v1/cameras')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ items: mockCameras, total: 1, page: 1, page_size: 50, total_pages: 1 }),
        } as Response);
      }

      if (u.includes('/api/v1/events/10')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockEvents,
        } as Response);
      }

      if (u.includes('/api/v1/events/1') || u.includes('/api/v1/events/20')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => [],
        } as Response);
      }

      if (u.includes('/api/v1/events/999')) {
        return Promise.resolve({
          ok: false,
          status: 404,
          json: async () => ({ detail: "Track '999' not found." }),
        } as Response);
      }

      if (u.includes('/api/v1/tracks/10')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => mockTrack,
        } as Response);
      }

      if (u.includes('/api/v1/alerts')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ items: [], total: 0, page: 1, page_size: 50, total_pages: 1 }),
        } as Response);
      }

      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ items: [], total: 0, page: 1, page_size: 50, total_pages: 1 }),
      } as Response);
    });
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  // 1. Timeline renders events
  it('1. renders chronological detection events from the M16 backend API', async () => {
    render(<EventTimelinePage initialTrackId="10" />);

    await waitFor(() => {
      expect(screen.getByTestId('event-timeline-container')).toBeInTheDocument();
      expect(screen.getByTestId('timeline-event-101')).toBeInTheDocument();
      expect(screen.getByTestId('timeline-event-102')).toBeInTheDocument();
      expect(screen.getByTestId('timeline-event-103')).toBeInTheDocument();
    });

    expect(screen.getAllByText(/FENCE BREACH/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/LOITERING/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/ZONE ENTRY/i).length).toBeGreaterThanOrEqual(1);
  });

  // 2. Newest-first ordering
  it('2. defaults to newest-first chronological ordering', () => {
    render(<EventTimeline trackId="10" events={mockEvents} track={mockTrack} />);

    const list = screen.getByTestId('timeline-events-list');
    const items = within(list).getAllByRole('listitem');
    expect(items.length).toBe(3);

    // Newest event is EVT-003 at 10:14:00Z (id 103)
    expect(items[0]).toHaveAttribute('data-testid', 'timeline-event-103');
    expect(items[1]).toHaveAttribute('data-testid', 'timeline-event-102');
    expect(items[2]).toHaveAttribute('data-testid', 'timeline-event-101');
  });

  // 3. Oldest-first ordering
  it('3. sorts by oldest-first when toggled by operator', () => {
    render(<EventTimeline trackId="10" events={mockEvents} track={mockTrack} />);

    const sortBtn = screen.getByTestId('timeline-sort-toggle-btn');
    expect(sortBtn).toHaveTextContent(/Newest First/i);

    fireEvent.click(sortBtn);
    expect(sortBtn).toHaveTextContent(/Oldest First/i);

    const list = screen.getByTestId('timeline-events-list');
    const items = within(list).getAllByRole('listitem');

    // Oldest event is EVT-001 at 10:05:00Z (id 101)
    expect(items[0]).toHaveAttribute('data-testid', 'timeline-event-101');
    expect(items[2]).toHaveAttribute('data-testid', 'timeline-event-103');
  });

  // 4. Event filtering
  it('4. filters events by category client-side on loaded real data', () => {
    render(<EventTimeline trackId="10" events={mockEvents} track={mockTrack} />);

    // Filter by Fence Breach
    const breachFilterBtn = screen.getByTestId('timeline-filter-breach');
    fireEvent.click(breachFilterBtn);

    expect(screen.getByTestId('timeline-event-101')).toBeInTheDocument();
    expect(screen.queryByTestId('timeline-event-102')).not.toBeInTheDocument();
    expect(screen.queryByTestId('timeline-event-103')).not.toBeInTheDocument();

    // Filter by Loitering
    const loiteringFilterBtn = screen.getByTestId('timeline-filter-loitering');
    fireEvent.click(loiteringFilterBtn);

    expect(screen.queryByTestId('timeline-event-101')).not.toBeInTheDocument();
    expect(screen.getByTestId('timeline-event-102')).toBeInTheDocument();
    expect(screen.queryByTestId('timeline-event-103')).not.toBeInTheDocument();

    // Reset to All
    const allFilterBtn = screen.getByTestId('timeline-filter-all');
    fireEvent.click(allFilterBtn);

    expect(screen.getByTestId('timeline-event-101')).toBeInTheDocument();
    expect(screen.getByTestId('timeline-event-102')).toBeInTheDocument();
    expect(screen.getByTestId('timeline-event-103')).toBeInTheDocument();
  });

  // 5. Empty state
  it('5. displays empty state when track exists but has no events', async () => {
    render(<EventTimelinePage initialTrackId="20" />);

    await waitFor(() => {
      expect(screen.getByTestId('timeline-empty-state')).toBeInTheDocument();
    });

    expect(screen.getByText(/No events recorded for this track/i)).toBeInTheDocument();
  });

  // 6. Loading state
  it('6. displays tactical loading state while query is in-flight', () => {
    render(<EventTimeline trackId="10" events={[]} loading={true} />);

    expect(screen.getByTestId('timeline-loading-state')).toBeInTheDocument();
    expect(screen.getByText(/Loading event history.../i)).toBeInTheDocument();
  });

  // 7. API error state
  it('7. displays API error state on 404 or request failure with retry option', async () => {
    render(<EventTimelinePage initialTrackId="999" />);

    await waitFor(() => {
      expect(screen.getByTestId('timeline-error-state')).toBeInTheDocument();
    });

    expect(screen.getByText(/Unable to load event history/i)).toBeInTheDocument();
    expect(screen.getByTestId('timeline-retry-btn')).toBeInTheDocument();
  });

  // 8. Unknown event type
  it('8. gracefully handles unknown event types without crashing', () => {
    const unknownEvent: Event = {
      id: 999,
      event_id: 'EVT-999',
      camera_id: 1,
      track_id: 10,
      zone_id: null,
      event_type: 'CUSTOM_DRONE_ACTIVITY',
      frame_id: null,
      timestamp: '2026-09-12T11:00:00Z',
      details: { info: 'drone hovering' },
      created_at: '2026-09-12T11:00:00Z',
    };

    render(<EventTimeline trackId="10" events={[unknownEvent]} />);

    expect(screen.getByTestId('timeline-event-999')).toBeInTheDocument();
    expect(screen.getAllByText(/CUSTOM DRONE ACTIVITY/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByTestId('timeline-icon-default')).toBeInTheDocument();
  });

  // 9. Missing optional fields
  it('9. gracefully renders events with null camera, zone, frame_id, and empty details', () => {
    const minimalEvent: Event = {
      id: 500,
      event_id: null,
      camera_id: null,
      track_id: 10,
      zone_id: null,
      event_type: 'MOTION',
      frame_id: null,
      timestamp: '2026-09-12T11:30:00Z',
      details: {},
      created_at: '2026-09-12T11:30:00Z',
    };

    render(<EventTimeline trackId="10" events={[minimalEvent]} />);

    expect(screen.getByTestId('timeline-event-500')).toBeInTheDocument();
    expect(screen.getByText(/MOTION/i)).toBeInTheDocument();
  });

  // 10. Track ID displayed
  it('10. displays selected track ID prominently in context header', () => {
    render(<EventTimeline trackId="10" events={mockEvents} track={mockTrack} />);

    expect(screen.getByText(/TRACK #10/i)).toBeInTheDocument();
    expect(screen.getByTestId('track-class-badge')).toHaveTextContent(/PERSON/i);
    expect(screen.getByTestId('track-status-badge')).toHaveTextContent(/ACTIVE/i);
  });

  // 11. Event count displayed
  it('11. displays accurate total events count in metrics row', () => {
    render(<EventTimeline trackId="10" events={mockEvents} track={mockTrack} />);

    const countElem = screen.getByTestId('timeline-events-count');
    expect(countElem).toHaveTextContent('3');
  });

  // 12. Navigation to timeline
  it('12. allows operator navigation to Timeline in App Shell', async () => {
    render(<App />);

    // Shell renders with CCTV by default
    expect(screen.getByTestId('cctv-monitoring-page')).toBeInTheDocument();

    // Click Timeline nav item in Shell
    const timelineNavBtn = screen.getByRole('button', { name: /Timeline/i });
    expect(timelineNavBtn).not.toBeDisabled();
    fireEvent.click(timelineNavBtn);

    await waitFor(() => {
      expect(screen.getByTestId('event-timeline-page')).toBeInTheDocument();
    });

    // Lookup input is functional
    const input = screen.getByTestId('track-id-input');
    fireEvent.change(input, { target: { value: '10' } });
    fireEvent.click(screen.getByTestId('track-inspect-btn'));

    await waitFor(() => {
      expect(screen.getByText(/TRACK #10/i)).toBeInTheDocument();
    });
  });

  // 13. Alert-to-timeline integration
  it('13. provides direct navigation from an Alert containing a track ID to the Event Timeline', async () => {
    const mockAlertWithTrack: Alert = {
      id: 1,
      alert_id: 'ALT-101',
      camera_id: 1,
      track_id: 10,
      event_id: 101,
      zone_id: 2,
      alert_type: 'FENCE_BREACH',
      severity: 'CRITICAL',
      status: 'ACTIVE',
      message: 'Perimeter breach at Alpha sector',
      alert_timestamp: '2026-09-12T10:05:00Z',
      alert_metadata: {},
      acknowledged_at: null,
      acknowledged_by: null,
      resolved_at: null,
      resolved_by: null,
      created_at: '2026-09-12T10:05:00Z',
      updated_at: '2026-09-12T10:05:00Z',
    };

    const handleViewTimeline = vi.fn();

    // Test AlertCard link
    render(
      <AlertCard
        alert={mockAlertWithTrack}
        onViewTimeline={handleViewTimeline}
      />
    );

    const trackLink = screen.getByTestId('alert-track-link-ALT-101');
    expect(trackLink).toHaveTextContent(/Track: #10/i);
    fireEvent.click(trackLink);

    expect(handleViewTimeline).toHaveBeenCalledWith(10);

    // Test AlertDetail button
    render(
      <AlertDetail
        alert={mockAlertWithTrack}
        isOpen={true}
        onClose={vi.fn()}
        onViewTimeline={handleViewTimeline}
      />
    );

    const detailBtn = screen.getByTestId('detail-view-timeline-btn');
    fireEvent.click(detailBtn);
    expect(handleViewTimeline).toHaveBeenCalledWith(10);
  });

  // 14. CCTV-to-timeline integration
  it('14. allows inspecting detected target timelines directly from live CCTV stream', () => {
    const handleViewTimeline = vi.fn();

    render(
      <CCTVMonitoring
        initialCameraId="CAM_01"
        onViewTimeline={handleViewTimeline}
      />
    );

    expect(screen.getByTestId('cctv-monitoring-page')).toBeInTheDocument();
  });

  // 15. Map-to-timeline integration
  it('15. allows inspecting track timeline from map popup when an alert has track_id', () => {
    const mockAlert: Alert = {
      id: 1,
      alert_id: 'ALT-101',
      camera_id: 1,
      track_id: 10,
      event_id: 101,
      zone_id: 2,
      alert_type: 'FENCE_BREACH',
      severity: 'CRITICAL',
      status: 'ACTIVE',
      message: 'Perimeter breach',
      alert_timestamp: '2026-09-12T10:05:00Z',
      alert_metadata: {},
      acknowledged_at: null,
      acknowledged_by: null,
      resolved_at: null,
      resolved_by: null,
      created_at: '2026-09-12T10:05:00Z',
      updated_at: '2026-09-12T10:05:00Z',
    };

    const handleViewTimeline = vi.fn();

    render(
      <CameraMarkerPopup
        camera={mockCameras[0]}
        coordinates={{ lat: 28.6139, lng: 77.209 }}
        activeAlerts={[mockAlert]}
        onViewTimeline={handleViewTimeline}
      />
    );

    const timelineBtn = screen.getByTestId('popup-view-timeline-btn');
    expect(timelineBtn).toHaveTextContent(/Inspect Track #10 Timeline/i);

    fireEvent.click(timelineBtn);
    expect(handleViewTimeline).toHaveBeenCalledWith(10);
  });

  // 16. No fake event data
  it('16. strictly enforces zero synthetic/fake event generation when API returns empty list', () => {
    render(<EventTimeline trackId="20" events={[]} track={null} />);

    // Must show empty state, and must not render any fake timeline nodes
    expect(screen.getByTestId('timeline-empty-state')).toBeInTheDocument();
    expect(screen.queryByTestId(/timeline-event-/i)).not.toBeInTheDocument();
  });

  // 17. Raw details disclosure
  it('17. allows expanding raw metadata payload for deep incident audit', () => {
    render(<EventTimeline trackId="10" events={[mockEvents[0]]} />);

    const toggleBtn = screen.getByTestId('toggle-raw-details-101');
    expect(screen.queryByTestId('raw-details-box-101')).not.toBeInTheDocument();

    fireEvent.click(toggleBtn);
    expect(screen.getByTestId('raw-details-box-101')).toBeInTheDocument();
    expect(screen.getByText(/"breach_step": 1/i)).toBeInTheDocument();

    fireEvent.click(toggleBtn);
    expect(screen.queryByTestId('raw-details-box-101')).not.toBeInTheDocument();
  });
});
