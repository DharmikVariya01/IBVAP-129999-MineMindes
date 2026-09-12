import React, { useState } from 'react';
import type { CameraStreamStatus, ConnectionState, FrameData } from '@/types/websocket';
import { FrameRenderer } from './FrameRenderer';
import { DetectionOverlay } from './DetectionOverlay';
import { VideoOff, AlertTriangle, Radio } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface LiveVideoProps {
  frame: FrameData | null;
  cameraId: string | null;
  cameraName?: string;
  connectionState: ConnectionState;
  cameraStatus: CameraStreamStatus | null;
  error?: string | null;
  className?: string;
}

export const LiveVideo: React.FC<LiveVideoProps> = ({
  frame,
  cameraId,
  cameraName,
  connectionState,
  cameraStatus,
  error,
  className,
}) => {
  const [dimensions, setDimensions] = useState<{ width: number; height: number }>({
    width: frame?.width || 0,
    height: frame?.height || 0,
  });

  const handleDimensionsChange = (width: number, height: number) => {
    if (width !== dimensions.width || height !== dimensions.height) {
      setDimensions({ width, height });
    }
  };

  const isConnected = connectionState === 'CONNECTED';
  const isConnecting = connectionState === 'CONNECTING' || connectionState === 'RECONNECTING';
  const isCameraOnline = cameraStatus === 'ONLINE' || cameraStatus === null; // default assume ok until reported

  return (
    <div
      className={cn(
        'relative w-full aspect-video bg-surveillance-950 rounded-lg overflow-hidden border border-surveillance-800 shadow-2xl flex items-center justify-center select-none',
        className
      )}
      data-testid="live-video-container"
    >
      {/* 1. Base Layer: Live Frame Renderer */}
      <FrameRenderer
        frame={frame}
        onDimensionsChange={handleDimensionsChange}
        className="w-full h-full object-contain"
      />

      {/* 2. Overlay Layer: AI Detections & Fences */}
      {frame && (
        <DetectionOverlay
          metadata={frame.metadata}
          frameWidth={dimensions.width || frame.width || 640}
          frameHeight={dimensions.height || frame.height || 360}
        />
      )}

      {/* 3. Tactical Corner Crosshairs (Control Room Aesthetic) */}
      <div className="absolute top-2 left-2 w-3 h-3 border-t-2 border-l-2 border-tactical-emerald/40 pointer-events-none z-20" />
      <div className="absolute top-2 right-2 w-3 h-3 border-t-2 border-r-2 border-tactical-emerald/40 pointer-events-none z-20" />
      <div className="absolute bottom-2 left-2 w-3 h-3 border-b-2 border-l-2 border-tactical-emerald/40 pointer-events-none z-20" />
      <div className="absolute bottom-2 right-2 w-3 h-3 border-b-2 border-r-2 border-tactical-emerald/40 pointer-events-none z-20" />

      {/* 4. Top Tactical HUD Bar */}
      <div className="absolute top-3 inset-x-3 flex items-center justify-between pointer-events-none z-20">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-surveillance-900/85 backdrop-blur border border-surveillance-700/80 rounded text-xs font-mono text-surveillance-100 shadow">
            <Radio className="w-3.5 h-3.5 text-tactical-emerald animate-pulse" />
            <span className="font-bold">{cameraName || cameraId || 'NO FEED'}</span>
            {cameraId && (
              <span className="text-[10px] text-surveillance-400 border-l border-surveillance-700 pl-1.5 ml-0.5">
                {cameraId}
              </span>
            )}
          </div>

          {isConnected && isCameraOnline ? (
            <div className="flex items-center gap-1.5 px-2 py-1 bg-tactical-emerald/15 border border-tactical-emerald/30 rounded text-[10px] font-mono font-bold text-tactical-emerald uppercase tracking-wider">
              <span className="w-1.5 h-1.5 rounded-full bg-tactical-emerald animate-ping" />
              LIVE
            </div>
          ) : isConnecting ? (
            <div className="flex items-center gap-1.5 px-2 py-1 bg-tactical-amber/15 border border-tactical-amber/30 rounded text-[10px] font-mono font-bold text-tactical-amber uppercase tracking-wider">
              <span className="w-1.5 h-1.5 rounded-full bg-tactical-amber animate-pulse" />
              SYNCING
            </div>
          ) : (
            <div className="flex items-center gap-1.5 px-2 py-1 bg-tactical-rose/15 border border-tactical-rose/30 rounded text-[10px] font-mono font-bold text-tactical-rose uppercase tracking-wider">
              <span className="w-1.5 h-1.5 rounded-full bg-tactical-rose" />
              FEED DOWN
            </div>
          )}
        </div>

        {/* Frame Resolution & ID Info */}
        {frame && (
          <div className="hidden sm:flex items-center gap-2 px-2 py-1 bg-surveillance-900/85 backdrop-blur border border-surveillance-700/80 rounded text-[10px] font-mono text-surveillance-400">
            {dimensions.width > 0 && dimensions.height > 0 && (
              <span>
                {dimensions.width}×{dimensions.height}
              </span>
            )}
            {typeof frame.frame_id === 'number' && (
              <span className="border-l border-surveillance-700 pl-1.5">FRM #{frame.frame_id}</span>
            )}
          </div>
        )}
      </div>

      {/* 5. Non-Blocking Error Alert Banner */}
      {error && (
        <div className="absolute bottom-4 left-4 flex items-center gap-2.5 px-3 py-1.5 bg-tactical-rose/90 backdrop-blur border border-tactical-rose rounded text-xs font-mono text-white z-30 shadow-lg">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span className="truncate max-w-md">{error}</span>
        </div>
      )}

      {/* 6. Viewport State Overlays */}
      {!cameraId ? (
        <div className="absolute inset-0 bg-surveillance-950/90 flex flex-col items-center justify-center p-4 text-center z-30 font-mono">
          <VideoOff className="w-10 h-10 text-surveillance-600 mb-2" />
          <h3 className="text-sm font-semibold text-surveillance-300 uppercase tracking-wider">
            No Camera Selected
          </h3>
          <p className="text-xs text-surveillance-500 mt-1 max-w-sm">
            Select a border surveillance camera feed above to establish real-time monitoring.
          </p>
        </div>
      ) : connectionState === 'DISCONNECTED' ? (
        <div className="absolute inset-0 bg-surveillance-950/85 flex flex-col items-center justify-center p-4 text-center z-30 font-mono">
          <VideoOff className="w-10 h-10 text-surveillance-600 mb-2" />
          <h3 className="text-sm font-semibold text-surveillance-300 uppercase tracking-wider">
            Stream Disconnected
          </h3>
          <p className="text-xs text-surveillance-500 mt-1">
            Camera channel offline or inactive. Select a camera to reconnect.
          </p>
        </div>
      ) : isConnecting ? (
        <div className="absolute bottom-4 right-4 flex items-center gap-2.5 px-3 py-1.5 bg-surveillance-900/90 backdrop-blur border border-tactical-amber/40 rounded text-xs font-mono text-tactical-amber z-30 shadow-lg">
          <span className="w-2 h-2 rounded-full bg-tactical-amber animate-ping" />
          <span>Connecting to camera stream...</span>
        </div>
      ) : cameraStatus === 'OFFLINE' ? (
        <div className="absolute inset-0 bg-surveillance-950/85 flex flex-col items-center justify-center p-4 text-center z-30 font-mono">
          <AlertTriangle className="w-10 h-10 text-tactical-rose mb-2" />
          <h3 className="text-sm font-semibold text-tactical-rose uppercase tracking-wider">
            Camera Reported Offline
          </h3>
          <p className="text-xs text-surveillance-400 mt-1 max-w-sm">
            The hardware or video capture device is currently offline. Stream channel active.
          </p>
        </div>
      ) : null}
    </div>
  );
};
