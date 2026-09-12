import React, { useEffect, useRef } from 'react';
import { cn } from '@/utils/cn';

export interface DetectionBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface TrackMetadata {
  track_id?: number | string;
  id?: number | string;
  class_name?: string;
  label?: string;
  confidence?: number;
  score?: number;
  bbox?: DetectionBox | [number, number, number, number] | { x: number; y: number; width: number; height: number };
  trail?: Array<[number, number] | { x: number; y: number }>;
}

export interface ZoneGeometry {
  id?: string | number;
  name?: string;
  type?: 'RESTRICTED' | 'SENSITIVE' | 'NORMAL' | string;
  points: Array<[number, number] | { x: number; y: number }>;
}

export interface DetectionOverlayProps {
  metadata?: Record<string, unknown> | null;
  frameWidth: number;
  frameHeight: number;
  className?: string;
}

export const DetectionOverlay: React.FC<DetectionOverlayProps> = ({
  metadata,
  frameWidth,
  frameHeight,
  className,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || frameWidth <= 0 || frameHeight <= 0) return;

    let ctx: CanvasRenderingContext2D | null = null;
    try {
      ctx = canvas.getContext('2d');
    } catch {
      // Graceful fallback in environments without full Canvas implementation (e.g. JSDOM)
      return;
    }
    if (!ctx) return;

    // Reset canvas
    ctx.clearRect(0, 0, frameWidth, frameHeight);

    if (!metadata) return;

    // 1. Draw Virtual Fences / Zones if present in metadata
    const zones = (metadata.zones || metadata.fence || metadata.boundaries) as unknown;
    if (Array.isArray(zones)) {
      zones.forEach((zone: ZoneGeometry) => {
        if (!zone || !Array.isArray(zone.points) || zone.points.length < 2) return;

        const isRestricted = zone.type?.toUpperCase() === 'RESTRICTED';
        const isSensitive = zone.type?.toUpperCase() === 'SENSITIVE';

        ctx.save();
        ctx.beginPath();
        zone.points.forEach((pt, idx) => {
          const x = Array.isArray(pt) ? pt[0] : pt.x;
          const y = Array.isArray(pt) ? pt[1] : pt.y;
          if (idx === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        });

        if (zone.points.length > 2) {
          ctx.closePath();
          ctx.fillStyle = isRestricted
            ? 'rgba(244, 63, 94, 0.12)'
            : isSensitive
            ? 'rgba(245, 158, 11, 0.10)'
            : 'rgba(6, 182, 212, 0.08)';
          ctx.fill();
        }

        ctx.strokeStyle = isRestricted ? '#f43f5e' : isSensitive ? '#f59e0b' : '#06b6d4';
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 4]);
        ctx.stroke();

        // Zone Name Label
        if (zone.name) {
          const firstPt = zone.points[0];
          const lx = Array.isArray(firstPt) ? firstPt[0] : firstPt.x;
          const ly = Array.isArray(firstPt) ? firstPt[1] : firstPt.y;
          ctx.fillStyle = isRestricted ? '#f43f5e' : isSensitive ? '#f59e0b' : '#06b6d4';
          ctx.font = 'bold 11px monospace';
          ctx.fillText(zone.name.toUpperCase(), lx + 4, ly - 6);
        }
        ctx.restore();
      });
    }

    // 2. Draw Detected / Tracked Entities
    const rawTracks = (metadata.tracks ||
      metadata.tracked_objects ||
      metadata.detections ||
      metadata.objects) as unknown;

    if (Array.isArray(rawTracks)) {
      rawTracks.forEach((item: TrackMetadata) => {
        if (!item) return;

        // Parse Bounding Box
        let x1 = 0;
        let y1 = 0;
        let x2 = 0;
        let y2 = 0;

        if (Array.isArray(item.bbox) && item.bbox.length === 4) {
          [x1, y1, x2, y2] = item.bbox;
        } else if (item.bbox && typeof item.bbox === 'object') {
          if ('x1' in item.bbox) {
            const b = item.bbox as DetectionBox;
            x1 = b.x1;
            y1 = b.y1;
            x2 = b.x2;
            y2 = b.y2;
          } else if ('x' in item.bbox) {
            const b = item.bbox as { x: number; y: number; width: number; height: number };
            x1 = b.x;
            y1 = b.y;
            x2 = b.x + b.width;
            y2 = b.y + b.height;
          }
        } else {
          return;
        }

        const width = Math.max(0, x2 - x1);
        const height = Math.max(0, y2 - y1);
        if (width === 0 || height === 0) return;

        const trackId = item.track_id ?? item.id ?? '';
        const className = (item.class_name || item.label || 'OBJECT').toUpperCase();
        const conf = item.confidence ?? item.score;

        // Determine Color Style
        const isVehicle = className.includes('VEHICLE') || className.includes('CAR') || className.includes('TRUCK');
        const boxColor = isVehicle ? '#f59e0b' : '#10b981'; // Tactical Amber or Tactical Emerald
        const bgColor = isVehicle ? 'rgba(245, 158, 11, 0.85)' : 'rgba(16, 185, 129, 0.85)';

        ctx.save();

        // Draw Movement Trail if available
        if (Array.isArray(item.trail) && item.trail.length > 1) {
          ctx.beginPath();
          item.trail.forEach((pt, i) => {
            const tx = Array.isArray(pt) ? pt[0] : pt.x;
            const ty = Array.isArray(pt) ? pt[1] : pt.y;
            if (i === 0) ctx.moveTo(tx, ty);
            else ctx.lineTo(tx, ty);
          });
          ctx.strokeStyle = boxColor;
          ctx.lineWidth = 1.5;
          ctx.setLineDash([3, 3]);
          ctx.globalAlpha = 0.6;
          ctx.stroke();
          ctx.globalAlpha = 1.0;
        }

        // Draw Bounding Box with Tactical Corner Accents
        ctx.strokeStyle = boxColor;
        ctx.lineWidth = 2;
        ctx.setLineDash([]);
        ctx.strokeRect(x1, y1, width, height);

        // Corner accents (tactical surveillance HUD look)
        const cornerLen = Math.min(12, width / 4, height / 4);
        ctx.lineWidth = 3;
        // Top-Left
        ctx.beginPath();
        ctx.moveTo(x1, y1 + cornerLen);
        ctx.lineTo(x1, y1);
        ctx.lineTo(x1 + cornerLen, y1);
        ctx.stroke();
        // Top-Right
        ctx.beginPath();
        ctx.moveTo(x2 - cornerLen, y1);
        ctx.lineTo(x2, y1);
        ctx.lineTo(x2, y1 + cornerLen);
        ctx.stroke();
        // Bottom-Left
        ctx.beginPath();
        ctx.moveTo(x1, y2 - cornerLen);
        ctx.lineTo(x1, y2);
        ctx.lineTo(x1 + cornerLen, y2);
        ctx.stroke();
        // Bottom-Right
        ctx.beginPath();
        ctx.moveTo(x2 - cornerLen, y2);
        ctx.lineTo(x2, y2);
        ctx.lineTo(x2, y2 - cornerLen);
        ctx.stroke();

        // Label Badge: e.g. "ID 17 | PERSON 0.91"
        const idLabel = trackId ? `ID ${trackId}` : '';
        const confLabel = typeof conf === 'number' ? ` ${conf.toFixed(2)}` : '';
        const fullLabel = [idLabel, className + confLabel].filter(Boolean).join(' • ');

        ctx.font = 'bold 10px monospace';
        const textMetrics = ctx.measureText(fullLabel);
        const badgeWidth = textMetrics.width + 10;
        const badgeHeight = 16;
        const badgeY = Math.max(0, y1 - badgeHeight - 2);

        // Badge Background
        ctx.fillStyle = bgColor;
        ctx.fillRect(x1, badgeY, badgeWidth, badgeHeight);

        // Badge Text
        ctx.fillStyle = '#0a0f18';
        ctx.fillText(fullLabel, x1 + 5, badgeY + 11);

        ctx.restore();
      });
    }
  }, [metadata, frameWidth, frameHeight]);

  return (
    <canvas
      ref={canvasRef}
      width={frameWidth > 0 ? frameWidth : 640}
      height={frameHeight > 0 ? frameHeight : 360}
      data-testid="detection-overlay-canvas"
      className={cn('absolute inset-0 w-full h-full object-contain pointer-events-none z-10', className)}
    />
  );
};
