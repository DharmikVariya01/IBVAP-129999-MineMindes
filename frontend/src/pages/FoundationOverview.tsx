import React, { useState } from 'react';
import { Card } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import { Badge } from '@/components/common/Badge';
import { Panel } from '@/components/common/Panel';
import { StatusIndicator } from '@/components/common/StatusIndicator';
import { LoadingState } from '@/components/common/LoadingState';
import { ErrorState } from '@/components/common/ErrorState';
import { EmptyState } from '@/components/common/EmptyState';
import { config } from '@/config/env';
import { useWebSocket } from '@/hooks/useWebSocket';
import { Server, Wifi, ShieldCheck, Database } from 'lucide-react';

export const FoundationOverview: React.FC = () => {
  const [testCamId, setTestCamId] = useState('CAM-01');
  const [showLoading, setShowLoading] = useState(false);
  const [showError, setShowError] = useState(false);

  // Demonstrate WebSocket hook infrastructure
  const ws = useWebSocket(testCamId, { autoConnect: false });

  return (
    <div className="space-y-6">
      {/* Top Banner / System Mission */}
      <div className="bg-gradient-to-r from-surveillance-900 via-surveillance-850 to-surveillance-900 border border-surveillance-800 rounded-xl p-6 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Badge variant="success">Milestone 18 Complete</Badge>
              <Badge variant="info">SIH26187 Platform</Badge>
            </div>
            <h2 className="text-xl font-bold text-white tracking-wide">
              Frontend Foundation & Infrastructure
            </h2>
            <p className="text-xs text-surveillance-300 mt-1 max-w-2xl leading-relaxed">
              Target architecture established with React 18, Vite, Tailwind CSS, typed M16 REST client, and M17 WebSocket streaming client. Future surveillance modules (M19–M26) will mount on this foundation.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setShowLoading(!showLoading);
                setShowError(false);
              }}
            >
              Toggle Loading Preview
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setShowError(!showError);
                setShowLoading(false);
              }}
            >
              Toggle Error Preview
            </Button>
          </div>
        </div>
      </div>

      {/* Conditional States Demo */}
      {showLoading && (
        <Card title="Simulated Loading State">
          <LoadingState message="Connecting to telemetry backend and initializing pipeline buffers..." />
        </Card>
      )}

      {showError && (
        <Card title="Simulated Error State">
          <ErrorState
            title="Surveillance Gateway Unreachable"
            message="Connection timeout when contacting REST service at configured endpoint."
            onRetry={() => setShowError(false)}
          />
        </Card>
      )}

      {/* Grid: Environment Config & Real-Time Client Foundation */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Environment & Backend Integration Spec */}
        <Card
          title="Backend Integration Contracts"
          subtitle="Configured endpoints and service protocols"
          action={<StatusIndicator status="online" label="Config Valid" />}
        >
          <div className="space-y-4 text-xs font-mono">
            <div className="bg-surveillance-950 p-3 rounded border border-surveillance-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-surveillance-400 flex items-center gap-2">
                  <Database className="h-3.5 w-3.5 text-tactical-cyan" />
                  REST API Base URL:
                </span>
                <span className="text-emerald-400 font-semibold">{config.apiBaseUrl}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-surveillance-400 flex items-center gap-2">
                  <Wifi className="h-3.5 w-3.5 text-tactical-emerald" />
                  WebSocket Stream URL:
                </span>
                <span className="text-tactical-cyan font-semibold">{config.wsBaseUrl}/ws/{'{camera_id}'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-surveillance-400 flex items-center gap-2">
                  <Server className="h-3.5 w-3.5 text-tactical-amber" />
                  Environment Mode:
                </span>
                <span className="text-surveillance-200 uppercase">{config.isDev ? 'Development' : 'Production'}</span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 pt-1">
              <div className="p-3 rounded bg-surveillance-950/60 border border-surveillance-800/80">
                <div className="text-[11px] text-surveillance-400 uppercase">M16 REST Client</div>
                <div className="text-sm font-bold text-white mt-1">6 Resource Sets</div>
                <div className="text-[10px] text-surveillance-500 mt-0.5">Cameras, Alerts, Tracks, Events, Evidence, Stats</div>
              </div>
              <div className="p-3 rounded bg-surveillance-950/60 border border-surveillance-800/80">
                <div className="text-[11px] text-surveillance-400 uppercase">M17 WebSocket Client</div>
                <div className="text-sm font-bold text-white mt-1">Bounded Backoff</div>
                <div className="text-[10px] text-surveillance-500 mt-0.5">Exponential retries, envelope parsing, clean teardown</div>
              </div>
            </div>
          </div>
        </Card>

        {/* WebSocket Streaming Client Tester */}
        <Panel
          title="M17 WebSocket Client Foundation"
          badge={
            <Badge
              variant={
                ws.state === 'CONNECTED'
                  ? 'success'
                  : ws.state === 'CONNECTING' || ws.state === 'RECONNECTING'
                  ? 'high'
                  : 'neutral'
              }
            >
              {ws.state}
            </Badge>
          }
          actions={
            <div className="flex items-center gap-2">
              {ws.connected ? (
                <Button variant="danger" size="sm" onClick={ws.disconnect}>
                  Disconnect
                </Button>
              ) : (
                <Button
                  variant="primary"
                  size="sm"
                  isLoading={ws.connecting}
                  onClick={() => ws.connect(testCamId)}
                >
                  Connect
                </Button>
              )}
            </div>
          }
        >
          <div className="space-y-3 text-xs">
            <div className="flex items-center gap-3">
              <label htmlFor="cam-target" className="text-surveillance-300 font-mono text-xs whitespace-nowrap">
                Camera Identifier:
              </label>
              <input
                id="cam-target"
                type="text"
                value={testCamId}
                onChange={(e) => setTestCamId(e.target.value)}
                disabled={ws.connected}
                className="bg-surveillance-950 border border-surveillance-700 rounded px-2.5 py-1 text-xs text-white font-mono focus:border-tactical-emerald focus:outline-none disabled:opacity-50 flex-1"
              />
            </div>

            {ws.error && (
              <div className="p-2.5 rounded bg-tactical-rose/10 border border-tactical-rose/30 text-rose-300 text-xs font-mono">
                Error: {ws.error}
              </div>
            )}

            <div className="bg-surveillance-950 border border-surveillance-800 rounded p-3 font-mono text-[11px] space-y-1 max-h-36 overflow-y-auto">
              <div className="text-surveillance-500">// Client Status Telemetry</div>
              <div className="text-surveillance-300">State: <span className="text-tactical-cyan">{ws.state}</span></div>
              <div className="text-surveillance-300">Target URL: <span className="text-surveillance-400">{config.wsBaseUrl}/ws/{testCamId}</span></div>
              {ws.lastMessage ? (
                <div className="text-emerald-400 mt-2">
                  Last Message [{ws.lastMessage.type}]: {JSON.stringify(ws.lastMessage.data)}
                </div>
              ) : (
                <div className="text-surveillance-500 italic mt-1">No incoming messages received yet.</div>
              )}
            </div>
          </div>
        </Panel>
      </div>

      {/* Component Library Showcase */}
      <Card
        title="Reusable Foundation UI Components"
        subtitle="Accessible, styled components ready for dashboard modules"
      >
        <div className="space-y-6">
          {/* Button Variants & Sizes */}
          <div>
            <h4 className="text-xs font-bold font-mono text-surveillance-400 uppercase tracking-wider mb-2">
              1. Button Component Variants & Sizes
            </h4>
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="primary" size="sm">Primary SM</Button>
              <Button variant="primary" size="md">Primary MD</Button>
              <Button variant="primary" size="lg">Primary LG</Button>
              <Button variant="secondary" size="md">Secondary</Button>
              <Button variant="danger" size="md">Danger</Button>
              <Button variant="outline" size="md">Outline</Button>
              <Button variant="ghost" size="md">Ghost</Button>
              <Button variant="primary" size="md" isLoading>Loading</Button>
              <Button variant="secondary" size="md" disabled>Disabled</Button>
            </div>
          </div>

          {/* Badges */}
          <div>
            <h4 className="text-xs font-bold font-mono text-surveillance-400 uppercase tracking-wider mb-2">
              2. Badge Component (Alert & Status Severities)
            </h4>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="critical">CRITICAL (Breach)</Badge>
              <Badge variant="high">HIGH (Loitering)</Badge>
              <Badge variant="medium">MEDIUM</Badge>
              <Badge variant="low">LOW</Badge>
              <Badge variant="success">RESOLVED</Badge>
              <Badge variant="info">ACKNOWLEDGED</Badge>
              <Badge variant="neutral">OFFLINE</Badge>
            </div>
          </div>

          {/* Status Indicators */}
          <div>
            <h4 className="text-xs font-bold font-mono text-surveillance-400 uppercase tracking-wider mb-2">
              3. Status Indicators (Real-Time State Dots)
            </h4>
            <div className="flex flex-wrap items-center gap-6 p-3 bg-surveillance-950 rounded border border-surveillance-800">
              <StatusIndicator status="online" label="Online Stream" />
              <StatusIndicator status="connecting" label="Connecting..." />
              <StatusIndicator status="error" label="Stream Exception" />
              <StatusIndicator status="offline" label="Offline / Idle" />
            </div>
          </div>

          {/* Empty State Component */}
          <div>
            <h4 className="text-xs font-bold font-mono text-surveillance-400 uppercase tracking-wider mb-2">
              4. Empty State Component
            </h4>
            <EmptyState
              title="No Pending Security Breaches"
              message="Platform surveillance pipeline is actively monitoring configured sectors."
            />
          </div>
        </div>
      </Card>

      {/* Module Roadmap Alignment Notice */}
      <div className="p-4 rounded-lg bg-surveillance-900 border border-surveillance-800 flex items-center justify-between text-xs text-surveillance-400">
        <div className="flex items-center gap-3">
          <ShieldCheck className="h-5 w-5 text-tactical-emerald" />
          <span>
            Foundation verified. M18 stops here before M19 Live CCTV Dashboard, M20 Alert Panel, and M21 Tactical Map.
          </span>
        </div>
        <Badge variant="neutral">Boundary Enforced</Badge>
      </div>
    </div>
  );
};
