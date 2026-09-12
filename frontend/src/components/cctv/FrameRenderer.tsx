import React, { useEffect, useMemo, useRef } from 'react';
import type { FrameData } from '@/types/websocket';
import { cn } from '@/utils/cn';

export interface FrameRendererProps {
  frame: FrameData | null;
  onDimensionsChange?: (width: number, height: number) => void;
  className?: string;
}

export const FrameRenderer: React.FC<FrameRendererProps> = React.memo(
  ({ frame, onDimensionsChange, className }) => {
    const imgRef = useRef<HTMLImageElement | null>(null);

    // Compute data URL safely
    const imageSrc = useMemo(() => {
      if (!frame || !frame.encoded_data) return null;
      const data = frame.encoded_data.trim();
      if (data.startsWith('data:')) {
        return data;
      }
      return `data:image/jpeg;base64,${data}`;
    }, [frame?.encoded_data]);

    // Track frame dimensions
    const handleImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
      const target = e.currentTarget;
      const width = frame?.width ?? target.naturalWidth;
      const height = frame?.height ?? target.naturalHeight;
      if (width > 0 && height > 0) {
        onDimensionsChange?.(width, height);
      }
    };

    useEffect(() => {
      if (frame?.width && frame?.height && frame.width > 0 && frame.height > 0) {
        onDimensionsChange?.(frame.width, frame.height);
      }
    }, [frame?.width, frame?.height, onDimensionsChange]);

    if (!imageSrc) {
      return (
        <div
          className={cn(
            'w-full h-full flex flex-col items-center justify-center bg-surveillance-950 text-surveillance-500 font-mono select-none',
            className
          )}
          data-testid="frame-placeholder"
        >
          <div className="relative flex items-center justify-center w-24 h-24 mb-3 border border-surveillance-800/80 rounded-full bg-surveillance-900/40">
            <span className="w-12 h-12 border border-tactical-emerald/20 rounded-full animate-ping opacity-30" />
            <span className="w-3 h-3 bg-surveillance-700 rounded-full" />
          </div>
          <div className="text-xs font-semibold uppercase tracking-widest text-surveillance-400">
            Awaiting Video Signal
          </div>
          <div className="text-[11px] text-surveillance-600 mt-1">
            Standby for live transmission frames
          </div>
        </div>
      );
    }

    return (
      <img
        ref={imgRef}
        src={imageSrc}
        alt="Live Camera Feed"
        onLoad={handleImageLoad}
        data-testid="live-frame-image"
        className={cn('w-full h-full object-contain block select-none pointer-events-none', className)}
      />
    );
  }
);

FrameRenderer.displayName = 'FrameRenderer';
