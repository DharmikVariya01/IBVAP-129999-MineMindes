import React, { useMemo, useState } from 'react';
import { AlertCard } from './AlertCard';
import { AlertFilters, AlertFilterValues } from './AlertFilters';
import { AlertDetail } from './AlertDetail';
import { LoadingState } from '@/components/common/LoadingState';
import { ErrorState } from '@/components/common/ErrorState';
import { EmptyState } from '@/components/common/EmptyState';
import { Bell, ShieldAlert } from 'lucide-react';
import type { Alert, AlertSeverity } from '@/types/api';

export interface AlertPanelProps {
  alerts: Alert[];
  loading?: boolean;
  error?: string | null;
  acknowledgingIds?: Set<string>;
  newAlertIds?: Set<string>;
  onAcknowledge?: (alertId: string) => void;
  onRefresh?: () => void;
  onMarkRead?: (alertId: string) => void;
  cameraNameMap?: Record<string, string>;
  headerAction?: React.ReactNode;
}

const SEVERITY_WEIGHTS: Record<AlertSeverity, number> = {
  CRITICAL: 4,
  HIGH: 3,
  MEDIUM: 2,
  LOW: 1,
};

export const AlertPanel: React.FC<AlertPanelProps> = ({
  alerts,
  loading = false,
  error = null,
  acknowledgingIds = new Set(),
  newAlertIds = new Set(),
  onAcknowledge,
  onRefresh,
  onMarkRead,
  cameraNameMap = {},
  headerAction,
}) => {
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [filterValues, setFilterValues] = useState<AlertFilterValues>({
    status: 'ALL',
    severity: 'ALL',
    alertType: 'ALL',
    search: '',
    sortBy: 'newest',
  });

  const handleResetFilters = () => {
    setFilterValues({
      status: 'ALL',
      severity: 'ALL',
      alertType: 'ALL',
      search: '',
      sortBy: 'newest',
    });
  };

  const handleSelectAlert = (alert: Alert) => {
    setSelectedAlert(alert);
    if (onMarkRead && newAlertIds.has(alert.alert_id)) {
      onMarkRead(alert.alert_id);
    }
  };

  const handleCloseDetail = () => {
    setSelectedAlert(null);
  };

  // 1. Filter Logic
  const filteredAlerts = useMemo(() => {
    return alerts.filter((alert) => {
      // Status filter
      if (filterValues.status !== 'ALL' && alert.status !== filterValues.status) {
        return false;
      }

      // Severity filter
      if (filterValues.severity !== 'ALL' && alert.severity !== filterValues.severity) {
        return false;
      }

      // Alert Type filter
      if (filterValues.alertType !== 'ALL' && alert.alert_type !== filterValues.alertType) {
        return false;
      }

      // Search Query filter
      if (filterValues.search.trim()) {
        const query = filterValues.search.toLowerCase();
        const msg = (alert.message || '').toLowerCase();
        const id = (alert.alert_id || '').toLowerCase();
        const cam = String(alert.camera_id || '').toLowerCase();
        const metaCam = String(alert.alert_metadata?.camera_code || '').toLowerCase();
        const matches =
          msg.includes(query) ||
          id.includes(query) ||
          cam.includes(query) ||
          metaCam.includes(query);
        if (!matches) return false;
      }

      return true;
    });
  }, [alerts, filterValues]);

  // 2. Sort Logic
  const sortedAlerts = useMemo(() => {
    const list = [...filteredAlerts];

    switch (filterValues.sortBy) {
      case 'newest':
        return list.sort((a, b) => {
          const tA = new Date(a.alert_timestamp).getTime() || 0;
          const tB = new Date(b.alert_timestamp).getTime() || 0;
          return tB - tA;
        });

      case 'oldest':
        return list.sort((a, b) => {
          const tA = new Date(a.alert_timestamp).getTime() || 0;
          const tB = new Date(b.alert_timestamp).getTime() || 0;
          return tA - tB;
        });

      case 'severity':
        return list.sort((a, b) => {
          const weightA = SEVERITY_WEIGHTS[a.severity] || 0;
          const weightB = SEVERITY_WEIGHTS[b.severity] || 0;
          if (weightB !== weightA) {
            return weightB - weightA;
          }
          // Tie-break by timestamp descending
          const tA = new Date(a.alert_timestamp).getTime() || 0;
          const tB = new Date(b.alert_timestamp).getTime() || 0;
          return tB - tA;
        });

      default:
        return list;
    }
  }, [filteredAlerts, filterValues.sortBy]);

  const activeAlertsCount = useMemo(() => {
    return alerts.filter((a) => a.status === 'ACTIVE').length;
  }, [alerts]);

  return (
    <div className="space-y-4" data-testid="alert-panel">
      {/* Tactical Panel Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-surveillance-900 border border-surveillance-800 rounded-lg shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-tactical-rose/10 border border-tactical-rose/30 rounded text-tactical-rose">
            <ShieldAlert className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold tracking-wider text-surveillance-100 uppercase font-mono">
                Real-Time Alert Feed
              </h2>
              <span
                className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-tactical-rose/20 text-rose-300 border border-tactical-rose/40"
                data-testid="active-alerts-count"
              >
                ACTIVE: {activeAlertsCount}
              </span>
            </div>
            <p className="text-xs text-surveillance-400 font-mono">
              Live threat events & operator incident triage
            </p>
          </div>
        </div>

        {headerAction && <div className="flex items-center gap-2">{headerAction}</div>}
      </div>

      {/* Filter & Sort Controls */}
      <AlertFilters
        values={filterValues}
        onChange={setFilterValues}
        onReset={handleResetFilters}
        activeCount={sortedAlerts.length}
        totalCount={alerts.length}
      />

      {/* Main Content Area */}
      {loading && alerts.length === 0 ? (
        <LoadingState message="Connecting to surveillance database and loading security alerts..." />
      ) : error && alerts.length === 0 ? (
        <ErrorState
          title="Alert Service Disconnected"
          message={error}
          onRetry={onRefresh}
          retryLabel="Retry Alert Sync"
        />
      ) : sortedAlerts.length === 0 ? (
        <EmptyState
          icon={<Bell className="w-6 h-6 text-surveillance-500" />}
          title={alerts.length === 0 ? 'No Active Alerts' : 'No Matching Alerts'}
          message={
            alerts.length === 0
              ? 'Perimeter perimeter sensors report zero security incidents. All surveillance sectors normal.'
              : 'No alerts match the currently selected filter criteria. Try adjusting or clearing filters.'
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-3" data-testid="alert-list">
          {sortedAlerts.map((alert) => {
            const isAcknowledging = acknowledgingIds.has(alert.alert_id);
            const isNew = newAlertIds.has(alert.alert_id);
            const camName =
              cameraNameMap[alert.camera_id ?? ''] ||
              cameraNameMap[alert.alert_metadata?.camera_code as string];

            return (
              <AlertCard
                key={alert.alert_id}
                alert={alert}
                isNew={isNew}
                isAcknowledging={isAcknowledging}
                onAcknowledge={onAcknowledge}
                onSelect={handleSelectAlert}
                cameraName={camName}
              />
            );
          })}
        </div>
      )}

      {/* Alert Detail Slide-Over / Modal */}
      {selectedAlert && (
        <AlertDetail
          alert={selectedAlert}
          isOpen={true}
          onClose={handleCloseDetail}
          onAcknowledge={onAcknowledge}
          isAcknowledging={acknowledgingIds.has(selectedAlert.alert_id)}
          cameraName={
            cameraNameMap[selectedAlert.camera_id ?? ''] ||
            cameraNameMap[selectedAlert.alert_metadata?.camera_code as string]
          }
        />
      )}
    </div>
  );
};
