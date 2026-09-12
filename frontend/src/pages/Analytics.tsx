import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '@/services/api/client';
import type { PlatformStats } from '@/types/api';
import {
  AnalyticsHeader,
  StatCard,
  CameraStatusChart,
  AlertSeverityChart,
  TrackStatusChart,
  AlertStatusChart,
  ActivitySummary,
  AnalyticsLoading,
  AnalyticsError,
  AnalyticsEmpty,
} from '@/components/analytics';
import {
  Camera,
  AlertTriangle,
  Crosshair,
  Activity,
  FileCheck,
} from 'lucide-react';

export interface AnalyticsProps {
  onNavigateToAlerts?: () => void;
  onNavigateToMap?: () => void;
  onNavigateToCCTV?: () => void;
  onNavigateToTimeline?: () => void;
}

export const Analytics: React.FC<AnalyticsProps> = ({
  onNavigateToAlerts,
  onNavigateToMap,
  onNavigateToCCTV,
  onNavigateToTimeline,
}) => {
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchStats = useCallback(async (isManualRefresh = false) => {
    if (isManualRefresh) {
      setIsRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const data = await apiClient.getStats();
      setStats(data);
      setLastUpdated(new Date());
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to retrieve statistics from backend';
      setError(errorMsg);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchStats(false);
  }, [fetchStats]);

  // Loading State
  if (loading && !stats) {
    return (
      <div data-testid="analytics-page" className="space-y-6">
        <AnalyticsHeader
          lastUpdated={null}
          onRefresh={() => fetchStats(true)}
          isRefreshing={false}
        />
        <AnalyticsLoading />
      </div>
    );
  }

  // Error State
  if (error && !stats) {
    return (
      <div data-testid="analytics-page" className="space-y-6">
        <AnalyticsHeader
          lastUpdated={lastUpdated}
          onRefresh={() => fetchStats(true)}
          isRefreshing={isRefreshing}
        />
        <AnalyticsError
          message={error}
          onRetry={() => fetchStats(false)}
          isRetrying={loading || isRefreshing}
        />
      </div>
    );
  }

  // Empty / Null State
  if (!stats) {
    return (
      <div data-testid="analytics-page" className="space-y-6">
        <AnalyticsHeader
          lastUpdated={lastUpdated}
          onRefresh={() => fetchStats(true)}
          isRefreshing={isRefreshing}
        />
        <AnalyticsEmpty
          onRefresh={() => fetchStats(true)}
          isRefreshing={isRefreshing}
        />
      </div>
    );
  }

  // Normalized safe values from real response
  const totalCameras = typeof stats.cameras === 'number' ? stats.cameras : 0;
  const totalAlerts = typeof stats.alerts === 'number' ? stats.alerts : 0;
  const totalTracks = typeof stats.tracks === 'number' ? stats.tracks : 0;
  const totalEvents = typeof stats.events === 'number' ? stats.events : 0;
  const totalEvidence = typeof stats.evidence === 'number' ? stats.evidence : 0;

  // Normalized status counts
  const normCameras: Record<string, number> = {};
  Object.entries(stats.cameras_by_status || {}).forEach(([k, v]) => {
    normCameras[k.toUpperCase()] = (normCameras[k.toUpperCase()] || 0) + v;
  });
  const onlineCameras = normCameras['ONLINE'] || 0;
  const offlineCameras = normCameras['OFFLINE'] || 0;

  const normAlertStatus: Record<string, number> = {};
  Object.entries(stats.alerts_by_status || {}).forEach(([k, v]) => {
    normAlertStatus[k.toUpperCase()] = (normAlertStatus[k.toUpperCase()] || 0) + v;
  });
  const activeAlerts = normAlertStatus['ACTIVE'] || 0;

  const normAlertSeverity: Record<string, number> = {};
  Object.entries(stats.alerts_by_severity || {}).forEach(([k, v]) => {
    normAlertSeverity[k.toUpperCase()] = (normAlertSeverity[k.toUpperCase()] || 0) + v;
  });
  const criticalAlerts = normAlertSeverity['CRITICAL'] || 0;

  const normTracks: Record<string, number> = {};
  Object.entries(stats.tracks_by_status || {}).forEach(([k, v]) => {
    normTracks[k.toUpperCase()] = (normTracks[k.toUpperCase()] || 0) + v;
  });
  const activeTracks = normTracks['ACTIVE'] || 0;

  return (
    <div data-testid="analytics-page" className="space-y-6">
      {/* Top Header with Refresh */}
      <AnalyticsHeader
        lastUpdated={lastUpdated}
        onRefresh={() => fetchStats(true)}
        isRefreshing={isRefreshing}
      />

      {/* Overview KPI Cards */}
      <section aria-label="Operational KPI Overview" className="space-y-2">
        <h2 className="text-xs font-mono font-semibold uppercase tracking-wider text-surveillance-400">
          Core Surveillance Metrics
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <StatCard
            testId="stat-cameras"
            title="Total Cameras"
            value={totalCameras}
            subtitle={`${onlineCameras} Online / ${offlineCameras} Offline`}
            icon={Camera}
            badge={onlineCameras > 0 ? `${onlineCameras} Online` : undefined}
            variant="emerald"
            onClick={onNavigateToMap || onNavigateToCCTV}
            actionLabel="Map View"
          />

          <StatCard
            testId="stat-alerts"
            title="Security Alerts"
            value={totalAlerts}
            subtitle={`${activeAlerts} Active / ${criticalAlerts} Critical`}
            icon={AlertTriangle}
            badge={criticalAlerts > 0 ? `${criticalAlerts} Critical` : activeAlerts > 0 ? `${activeAlerts} Active` : undefined}
            variant={criticalAlerts > 0 ? 'rose' : activeAlerts > 0 ? 'amber' : 'neutral'}
            onClick={onNavigateToAlerts}
            actionLabel="Alert Center"
          />

          <StatCard
            testId="stat-tracks"
            title="Tracked Objects"
            value={totalTracks}
            subtitle={`${activeTracks} Active in sector`}
            icon={Crosshair}
            badge={activeTracks > 0 ? `${activeTracks} Active` : undefined}
            variant="cyan"
            onClick={onNavigateToTimeline}
            actionLabel="Timeline"
          />

          <StatCard
            testId="stat-events"
            title="Detection Events"
            value={totalEvents}
            subtitle="Pipeline boundary triggers"
            icon={Activity}
            variant="purple"
            onClick={onNavigateToTimeline}
            actionLabel="Timeline"
          />

          <StatCard
            testId="stat-evidence"
            title="Forensic Evidence"
            value={totalEvidence}
            subtitle="Archived frame records"
            icon={FileCheck}
            variant="blue"
          />
        </div>
      </section>

      {/* Distribution Charts Grid */}
      <section aria-label="Surveillance Distribution Charts" className="space-y-2">
        <h2 className="text-xs font-mono font-semibold uppercase tracking-wider text-surveillance-400">
          Tactical Distribution &amp; Status Breakdowns
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <CameraStatusChart
            data={stats.cameras_by_status}
            totalCameras={totalCameras}
            onNavigateToMap={onNavigateToMap}
          />

          <AlertSeverityChart
            data={stats.alerts_by_severity}
            totalAlerts={totalAlerts}
            onNavigateToAlerts={onNavigateToAlerts}
          />

          <TrackStatusChart
            data={stats.tracks_by_status}
            totalTracks={totalTracks}
            onNavigateToTimeline={onNavigateToTimeline}
          />

          <AlertStatusChart
            data={stats.alerts_by_status}
            totalAlerts={totalAlerts}
            onNavigateToAlerts={onNavigateToAlerts}
          />
        </div>
      </section>

      {/* Operational Summary Briefing */}
      <section aria-label="Operational Briefing">
        <ActivitySummary stats={stats} />
      </section>
    </div>
  );
};
