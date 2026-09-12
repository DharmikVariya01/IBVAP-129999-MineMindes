import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { Analytics } from '@/pages/Analytics';
import { App } from '@/App';
import { apiClient, ApiError } from '@/services/api/client';
import {
  StatCard,
  AnalyticsError,
  AnalyticsEmpty,
} from '@/components/analytics';
import type { PlatformStats } from '@/types/api';
import { Camera } from 'lucide-react';

const mockValidStats: PlatformStats = {
  cameras: 8,
  tracks: 24,
  events: 56,
  alerts: 12,
  evidence: 9,
  alerts_by_status: {
    ACTIVE: 4,
    ACKNOWLEDGED: 5,
    RESOLVED: 3,
  },
  alerts_by_severity: {
    CRITICAL: 2,
    HIGH: 4,
    MEDIUM: 5,
    LOW: 1,
  },
  cameras_by_status: {
    ONLINE: 6,
    OFFLINE: 2,
    ERROR: 0,
  },
  tracks_by_status: {
    ACTIVE: 10,
    LOST: 2,
    COMPLETED: 12,
  },
};

const mockZeroStats: PlatformStats = {
  cameras: 0,
  tracks: 0,
  events: 0,
  alerts: 0,
  evidence: 0,
  alerts_by_status: {},
  alerts_by_severity: {},
  cameras_by_status: {},
  tracks_by_status: {},
};

describe('IBVAP M23 — Tactical Statistics & Analytics Module', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // 1. Statistics page renders
  it('1. renders the Analytics page with tactical header and branding', async () => {
    vi.spyOn(apiClient, 'getStats').mockResolvedValue(mockValidStats);

    render(<Analytics />);

    expect(screen.getByTestId('analytics-page')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /tactical statistics & analytics/i })
    ).toBeInTheDocument();
    expect(screen.getByText(/m23 console/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('stat-cameras')).toBeInTheDocument();
    });
  });

  // 2. GET /api/v1/stats is called
  it('2. calls apiClient.getStats (GET /api/v1/stats) exactly on mount', async () => {
    const getStatsSpy = vi.spyOn(apiClient, 'getStats').mockResolvedValue(mockValidStats);

    render(<Analytics />);

    await waitFor(() => {
      expect(getStatsSpy).toHaveBeenCalledTimes(1);
    });
  });

  // 3. KPI metrics render from real response data
  it('3. renders KPI metrics accurately from actual API response data without fabrication', async () => {
    vi.spyOn(apiClient, 'getStats').mockResolvedValue(mockValidStats);

    render(<Analytics />);

    await waitFor(() => {
      // Cameras KPI
      const camerasCard = screen.getByTestId('stat-cameras');
      expect(within(camerasCard).getByText('8')).toBeInTheDocument();
      expect(within(camerasCard).getByText(/6 online \/ 2 offline/i)).toBeInTheDocument();

      // Alerts KPI
      const alertsCard = screen.getByTestId('stat-alerts');
      expect(within(alertsCard).getByText('12')).toBeInTheDocument();
      expect(within(alertsCard).getByText(/4 active \/ 2 critical/i)).toBeInTheDocument();

      // Tracks KPI
      const tracksCard = screen.getByTestId('stat-tracks');
      expect(within(tracksCard).getByText('24')).toBeInTheDocument();
      expect(within(tracksCard).getByText(/10 active in sector/i)).toBeInTheDocument();

      // Events KPI
      const eventsCard = screen.getByTestId('stat-events');
      expect(within(eventsCard).getByText('56')).toBeInTheDocument();

      // Evidence KPI
      const evidenceCard = screen.getByTestId('stat-evidence');
      expect(within(evidenceCard).getByText('9')).toBeInTheDocument();
    });
  });

  // 4. Supported chart data renders
  it('4. renders supported distributions (Camera status, Alert severity, Track status, Alert lifecycle)', async () => {
    vi.spyOn(apiClient, 'getStats').mockResolvedValue(mockValidStats);

    render(<Analytics />);

    await waitFor(() => {
      expect(screen.getByTestId('camera-status-chart')).toBeInTheDocument();
      expect(screen.getByTestId('alert-severity-chart')).toBeInTheDocument();
      expect(screen.getByTestId('track-status-chart')).toBeInTheDocument();
      expect(screen.getByTestId('alert-status-chart')).toBeInTheDocument();

      // Camera counts: 6 online, 2 offline
      const camChart = screen.getByTestId('camera-status-chart');
      expect(within(camChart).getByText('6')).toBeInTheDocument();
      expect(within(camChart).getByText('2')).toBeInTheDocument();

      // Alert severity: 2 critical, 4 high, 5 medium, 1 low
      const sevChart = screen.getByTestId('alert-severity-chart');
      expect(within(sevChart).getByText('Critical')).toBeInTheDocument();
      expect(within(sevChart).getByText('High')).toBeInTheDocument();
      expect(within(sevChart).getByText('Medium')).toBeInTheDocument();
      expect(within(sevChart).getByText('Low')).toBeInTheDocument();
    });
  });

  // 5. Zero values render correctly
  it('5. handles zero values gracefully without NaN, division by zero, or crashing', async () => {
    vi.spyOn(apiClient, 'getStats').mockResolvedValue(mockZeroStats);

    render(<Analytics />);

    await waitFor(() => {
      const camerasCard = screen.getByTestId('stat-cameras');
      expect(within(camerasCard).getByText('0')).toBeInTheDocument();
      expect(within(camerasCard).getByText(/0 online \/ 0 offline/i)).toBeInTheDocument();

      const alertsCard = screen.getByTestId('stat-alerts');
      expect(within(alertsCard).getByText('0')).toBeInTheDocument();

      // Charts render with empty/zero state indicators
      expect(screen.getByText(/no camera assets currently registered/i)).toBeInTheDocument();
      expect(screen.getByText(/no security alerts recorded/i)).toBeInTheDocument();
      expect(screen.getByText(/no tracking entities currently recorded/i)).toBeInTheDocument();
      expect(screen.getByText(/no alert triage history recorded/i)).toBeInTheDocument();
    });
  });

  // 6. Empty distribution handled
  it('6. handles empty distributions when objects have zero items', async () => {
    const emptyDistStats: PlatformStats = {
      cameras: 2,
      tracks: 5,
      events: 10,
      alerts: 1,
      evidence: 0,
      alerts_by_status: {},
      alerts_by_severity: {},
      cameras_by_status: {},
      tracks_by_status: {},
    };

    vi.spyOn(apiClient, 'getStats').mockResolvedValue(emptyDistStats);

    render(<Analytics />);

    await waitFor(() => {
      expect(screen.getByTestId('stat-cameras')).toBeInTheDocument();
      expect(screen.getByTestId('camera-status-chart')).toBeInTheDocument();
    });
  });

  // 7. Loading state
  it('7. renders loading state while awaiting API response', () => {
    // Return a promise that never resolves immediately
    vi.spyOn(apiClient, 'getStats').mockReturnValue(new Promise(() => {}));

    render(<Analytics />);

    expect(screen.getByTestId('analytics-loading')).toBeInTheDocument();
    expect(screen.getByText(/loading statistics.../i)).toBeInTheDocument();
  });

  // 8. API error state
  it('8. renders tactical error alert when API request fails', async () => {
    vi.spyOn(apiClient, 'getStats').mockRejectedValue(
      new ApiError('Database connection pool exhausted', 503)
    );

    render(<Analytics />);

    await waitFor(() => {
      expect(screen.getByTestId('analytics-error')).toBeInTheDocument();
      expect(screen.getByText(/unable to load statistics./i)).toBeInTheDocument();
      expect(screen.getByText(/database connection pool exhausted/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /retry loading statistics/i })).toBeInTheDocument();
    });
  });

  // 9. Retry behavior
  it('9. allows retrying data fetch after an error occurs', async () => {
    const getStatsSpy = vi.spyOn(apiClient, 'getStats');
    getStatsSpy.mockRejectedValueOnce(new Error('Network offline'));
    getStatsSpy.mockResolvedValueOnce(mockValidStats);

    render(<Analytics />);

    await waitFor(() => {
      expect(screen.getByTestId('analytics-error')).toBeInTheDocument();
    });

    // Click Retry
    const retryBtn = screen.getByRole('button', { name: /retry loading statistics/i });
    fireEvent.click(retryBtn);

    await waitFor(() => {
      expect(getStatsSpy).toHaveBeenCalledTimes(2);
      expect(screen.getByTestId('stat-cameras')).toBeInTheDocument();
      expect(within(screen.getByTestId('stat-cameras')).getByText('8')).toBeInTheDocument();
    });
  });

  // 10. Refresh behavior
  it('10. supports manual refresh and updates the timestamp without losing UI state', async () => {
    const getStatsSpy = vi.spyOn(apiClient, 'getStats').mockResolvedValue(mockValidStats);

    render(<Analytics />);

    await waitFor(() => {
      expect(screen.getByTestId('stat-cameras')).toBeInTheDocument();
      expect(screen.getByText(/updated:/i)).toBeInTheDocument();
    });

    const refreshBtn = screen.getByRole('button', { name: /refresh statistics/i });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(getStatsSpy).toHaveBeenCalledTimes(2);
    });
  });

  // 11. No fake data fallback
  it('11. never injects fake or demo data when the API fails', async () => {
    vi.spyOn(apiClient, 'getStats').mockRejectedValue(new Error('500 Internal Server Error'));

    render(<Analytics />);

    await waitFor(() => {
      expect(screen.getByTestId('analytics-error')).toBeInTheDocument();
      // Should NOT render fake camera or alert numbers
      expect(screen.queryByTestId('stat-cameras')).not.toBeInTheDocument();
      expect(screen.queryByTestId('stat-alerts')).not.toBeInTheDocument();
    });
  });

  // 12. Unknown category handling
  it('12. handles unknown status or severity categories gracefully in charts', async () => {
    const statsWithUnknown: PlatformStats = {
      ...mockValidStats,
      cameras_by_status: {
        ONLINE: 4,
        MAINTENANCE_SCHEDULED: 2,
      },
      alerts_by_severity: {
        CRITICAL: 1,
        ELEVATED_CUSTOM: 3,
      },
    };

    vi.spyOn(apiClient, 'getStats').mockResolvedValue(statsWithUnknown);

    render(<Analytics />);

    await waitFor(() => {
      const camChart = screen.getByTestId('camera-status-chart');
      expect(within(camChart).getByText('MAINTENANCE_SCHEDULED')).toBeInTheDocument();
      expect(within(camChart).getByText('2')).toBeInTheDocument();

      const sevChart = screen.getByTestId('alert-severity-chart');
      expect(within(sevChart).getByText('ELEVATED_CUSTOM')).toBeInTheDocument();
      expect(within(sevChart).getByText('3')).toBeInTheDocument();
    });
  });

  // 13. Operational summary derives real statements
  it('13. renders operational summary derived strictly from real API numbers', async () => {
    vi.spyOn(apiClient, 'getStats').mockResolvedValue(mockValidStats);

    render(<Analytics />);

    await waitFor(() => {
      const summary = screen.getByTestId('activity-summary-card');
      expect(within(summary).getByText(/6 of 8 cameras online \(75% operational\)/i)).toBeInTheDocument();
      expect(within(summary).getByText(/4 active alerts pending operator response/i)).toBeInTheDocument();
      expect(within(summary).getByText(/2 critical priority threats require immediate containment/i)).toBeInTheDocument();
      expect(within(summary).getByText(/10 active targets in tracking sector out of 24 historical tracks/i)).toBeInTheDocument();
      expect(within(summary).getByText(/9 evidence frames archived across 56 pipeline events/i)).toBeInTheDocument();
    });
  });

  // 14. Cross-module navigation to Alerts
  it('14. triggers onNavigateToAlerts callback when clicking Security Alerts KPI or Alert Center action', async () => {
    const onNavAlerts = vi.fn();
    vi.spyOn(apiClient, 'getStats').mockResolvedValue(mockValidStats);

    render(<Analytics onNavigateToAlerts={onNavAlerts} />);

    await waitFor(() => {
      expect(screen.getByTestId('stat-alerts')).toBeInTheDocument();
    });

    // Click Alerts KPI card
    const alertsCard = screen.getByTestId('stat-alerts');
    fireEvent.click(alertsCard);
    expect(onNavAlerts).toHaveBeenCalledTimes(1);

    // Click Alert Center action in Severity chart
    const alertCenterBtn = screen.getByRole('button', { name: /view alerts in alert center/i });
    fireEvent.click(alertCenterBtn);
    expect(onNavAlerts).toHaveBeenCalledTimes(2);
  });

  // 15. Cross-module navigation to Map / CCTV
  it('15. triggers onNavigateToMap callback when clicking Cameras KPI or Map action', async () => {
    const onNavMap = vi.fn();
    vi.spyOn(apiClient, 'getStats').mockResolvedValue(mockValidStats);

    render(<Analytics onNavigateToMap={onNavMap} />);

    await waitFor(() => {
      expect(screen.getByTestId('stat-cameras')).toBeInTheDocument();
    });

    const camerasCard = screen.getByTestId('stat-cameras');
    fireEvent.click(camerasCard);
    expect(onNavMap).toHaveBeenCalledTimes(1);

    const mapBtn = screen.getByRole('button', { name: /view cameras on tactical map/i });
    fireEvent.click(mapBtn);
    expect(onNavMap).toHaveBeenCalledTimes(2);
  });

  // 16. Cross-module navigation to Timeline
  it('16. triggers onNavigateToTimeline callback when clicking Tracks or Events KPI', async () => {
    const onNavTimeline = vi.fn();
    vi.spyOn(apiClient, 'getStats').mockResolvedValue(mockValidStats);

    render(<Analytics onNavigateToTimeline={onNavTimeline} />);

    await waitFor(() => {
      expect(screen.getByTestId('stat-tracks')).toBeInTheDocument();
    });

    const tracksCard = screen.getByTestId('stat-tracks');
    fireEvent.click(tracksCard);
    expect(onNavTimeline).toHaveBeenCalledTimes(1);

    const eventsCard = screen.getByTestId('stat-events');
    fireEvent.click(eventsCard);
    expect(onNavTimeline).toHaveBeenCalledTimes(2);
  });

  // 17. Application Shell navigation to Analytics
  it('17. integrates into App shell navigation and renders Analytics page when Analytics tab is selected', async () => {
    vi.spyOn(apiClient, 'getStats').mockResolvedValue(mockValidStats);
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0, page: 1, page_size: 50, total_pages: 1 }),
    } as unknown as Response);

    render(<App />);

    // Click Analytics tab in sub-header nav
    const analyticsNavBtn = screen.getByRole('button', { name: /analytics/i });
    expect(analyticsNavBtn).not.toBeDisabled();
    fireEvent.click(analyticsNavBtn);

    await waitFor(() => {
      expect(screen.getByTestId('analytics-page')).toBeInTheDocument();
      expect(
        screen.getByRole('heading', { name: /tactical statistics & analytics/i })
      ).toBeInTheDocument();
    });
  });

  // 18. StatCard unit tests
  it('18. StatCard renders accessible labels, variant styling, and triggers onClick', () => {
    const handleClick = vi.fn();
    render(
      <StatCard
        title="Custom Metric"
        value={42}
        subtitle="Operational indicator"
        icon={Camera}
        badge="Live"
        variant="emerald"
        onClick={handleClick}
        actionLabel="Inspect"
        testId="custom-stat-card"
      />
    );

    const card = screen.getByTestId('custom-stat-card');
    expect(card).toHaveAttribute('aria-label', 'Inspect');
    expect(screen.getByText('Custom Metric')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('Live')).toBeInTheDocument();

    fireEvent.click(card);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  // 19. Empty and Error components standalone unit tests
  it('19. AnalyticsEmpty and AnalyticsError render expected text and buttons', () => {
    const onRetry = vi.fn();
    const { rerender } = render(<AnalyticsError message="Error testing" onRetry={onRetry} />);

    expect(screen.getByText(/error testing/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /retry loading statistics/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);

    const onRefresh = vi.fn();
    rerender(<AnalyticsEmpty onRefresh={onRefresh} />);
    expect(screen.getByText(/no statistics available./i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /refresh statistics/i }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});
