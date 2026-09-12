import React from 'react';
import { Card } from '@/components/common/Card';
import { AlertCircle, Camera, Crosshair, FileCheck, Info } from 'lucide-react';
import type { PlatformStats } from '@/types/api';

export interface ActivitySummaryProps {
  stats: PlatformStats;
}

export const ActivitySummary: React.FC<ActivitySummaryProps> = ({ stats }) => {
  // Normalize camera status
  const normCameras: Record<string, number> = {};
  Object.entries(stats.cameras_by_status || {}).forEach(([k, v]) => {
    normCameras[k.toUpperCase()] = (normCameras[k.toUpperCase()] || 0) + v;
  });
  const onlineCameras = normCameras['ONLINE'] || 0;
  const offlineCameras = normCameras['OFFLINE'] || 0;

  // Normalize alert status & severity
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

  // Normalize track status
  const normTrackStatus: Record<string, number> = {};
  Object.entries(stats.tracks_by_status || {}).forEach(([k, v]) => {
    normTrackStatus[k.toUpperCase()] = (normTrackStatus[k.toUpperCase()] || 0) + v;
  });
  const activeTracks = normTrackStatus['ACTIVE'] || 0;

  const cameraRatioText = stats.cameras > 0
    ? `${onlineCameras} of ${stats.cameras} cameras online (${Math.round((onlineCameras / stats.cameras) * 100)}% operational)`
    : '0 cameras registered';

  return (
    <Card
      data-testid="activity-summary-card"
      title="Border Surveillance Operational Summary"
      subtitle="Synthesized tactical readiness briefing"
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Camera Readiness Brief */}
        <div className="p-3.5 rounded-lg bg-surveillance-950/60 border border-surveillance-800 flex items-start gap-3">
          <div className="p-2 rounded bg-tactical-emerald/10 border border-tactical-emerald/20 text-tactical-emerald shrink-0">
            <Camera className="w-4 h-4" aria-hidden="true" />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-surveillance-200">Perimeter Sensor Readiness</h4>
            <p className="text-xs text-surveillance-300 mt-1 font-mono">
              {cameraRatioText}
            </p>
            {offlineCameras > 0 && (
              <p className="text-[11px] text-tactical-amber mt-0.5">
                {offlineCameras} sensor{offlineCameras > 1 ? 's' : ''} currently offline or unreachable.
              </p>
            )}
          </div>
        </div>

        {/* Threat Posture Brief */}
        <div className="p-3.5 rounded-lg bg-surveillance-950/60 border border-surveillance-800 flex items-start gap-3">
          <div className="p-2 rounded bg-tactical-rose/10 border border-tactical-rose/20 text-tactical-rose shrink-0">
            <AlertCircle className="w-4 h-4" aria-hidden="true" />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-surveillance-200">Threat Posture</h4>
            <p className="text-xs text-surveillance-300 mt-1 font-mono">
              {activeAlerts > 0
                ? `${activeAlerts} active alert${activeAlerts > 1 ? 's' : ''} pending operator response`
                : 'All security alerts triaged & resolved'}
            </p>
            {criticalAlerts > 0 && (
              <p className="text-[11px] text-tactical-rose mt-0.5 font-semibold">
                {criticalAlerts} critical priority threat{criticalAlerts > 1 ? 's' : ''} require immediate containment.
              </p>
            )}
          </div>
        </div>

        {/* Target Tracking Brief */}
        <div className="p-3.5 rounded-lg bg-surveillance-950/60 border border-surveillance-800 flex items-start gap-3">
          <div className="p-2 rounded bg-tactical-cyan/10 border border-tactical-cyan/20 text-tactical-cyan shrink-0">
            <Crosshair className="w-4 h-4" aria-hidden="true" />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-surveillance-200">Target Tracking Activity</h4>
            <p className="text-xs text-surveillance-300 mt-1 font-mono">
              {activeTracks} active target{activeTracks !== 1 ? 's' : ''} in tracking sector out of {stats.tracks} historical tracks
            </p>
            <p className="text-[11px] text-surveillance-400 mt-0.5">
              Persistent ByteTrack association active across monitored feeds.
            </p>
          </div>
        </div>

        {/* Evidence & Pipeline Brief */}
        <div className="p-3.5 rounded-lg bg-surveillance-950/60 border border-surveillance-800 flex items-start gap-3">
          <div className="p-2 rounded bg-tactical-blue/10 border border-tactical-blue/20 text-tactical-blue shrink-0">
            <FileCheck className="w-4 h-4" aria-hidden="true" />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-surveillance-200">Forensic Evidence Chain</h4>
            <p className="text-xs text-surveillance-300 mt-1 font-mono">
              {stats.evidence} evidence frames archived across {stats.events} pipeline events
            </p>
            <p className="text-[11px] text-surveillance-400 mt-0.5">
              Evidence artifacts cryptographically stored for court-admissible audit.
            </p>
          </div>
        </div>
      </div>

      {/* Protocol Compliance Banner */}
      <div className="mt-4 pt-3 border-t border-surveillance-800/80 flex items-center justify-between text-[11px] text-surveillance-500">
        <div className="flex items-center gap-1.5">
          <Info className="w-3.5 h-3.5 text-surveillance-400 shrink-0" aria-hidden="true" />
          <span>All metrics computed directly via database aggregate queries (M16 REST API).</span>
        </div>
        <span className="font-mono text-[10px] uppercase text-surveillance-600">
          SEC: RESTRICTED
        </span>
      </div>
    </Card>
  );
};
