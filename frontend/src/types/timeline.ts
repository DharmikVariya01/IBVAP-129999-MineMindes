/**
 * TypeScript data contracts and types for IBVAP M22 Event Timeline module.
 */

import type { Event } from './api';

export type TimelineFilterCategory =
  | 'ALL'
  | 'ALERTS'
  | 'BREACH'
  | 'LOITERING'
  | 'ZONE'
  | 'MOVEMENT'
  | 'OTHER';

export type TimelineSortOrder = 'newest' | 'oldest';

export interface TimelineFilterOption {
  id: TimelineFilterCategory;
  label: string;
  badge?: number;
}

export interface TrackSummary {
  trackId: number | string;
  className: string;
  firstSeen: string | null;
  lastSeen: string | null;
  status?: string | null;
  cameraId?: number | null;
  cameraName?: string | null;
  totalEvents: number;
  lastConfidence?: number | null;
}

/**
 * Normalizes any backend or pipeline event into a standardized category
 * for client-side filtering and tactical visual styling.
 */
export function categorizeEvent(event: Event): TimelineFilterCategory {
  const type = (event.event_type || '').toUpperCase();
  const details = event.details || {};

  // 1. Critical Fence Breaches
  if (type.includes('BREACH') || type === 'FENCE_BREACH') {
    return 'BREACH';
  }

  // 2. Loitering
  if (type.includes('LOITER') || type === 'LOITERING') {
    return 'LOITERING';
  }

  // 3. Zone Changes / Entries / Exits
  if (type.includes('ZONE') || type === 'ZONE_ENTRY' || type === 'ZONE_EXIT' || type === 'ZONE_CHANGE') {
    return 'ZONE';
  }

  // 4. Motion / Movement
  if (type.includes('MOTION') || type.includes('MOVE') || type === 'MOVEMENT') {
    return 'MOVEMENT';
  }

  // 5. Alerts / Critical indicators within details or event type
  if (
    type.includes('ALERT') ||
    Boolean(details.severity) ||
    Boolean(details.alert_id) ||
    Boolean(details.is_alert)
  ) {
    return 'ALERTS';
  }

  return 'OTHER';
}

/**
 * Checks whether an event matches a selected filter category.
 */
export function eventMatchesCategory(event: Event, category: TimelineFilterCategory): boolean {
  if (category === 'ALL') return true;

  const eventCat = categorizeEvent(event);

  if (category === 'ALERTS') {
    // Both alerts category and critical triggers (breach, loitering, or explicit alert)
    const details = event.details || {};
    return (
      eventCat === 'BREACH' ||
      eventCat === 'LOITERING' ||
      eventCat === 'ALERTS' ||
      Boolean(details.severity) ||
      Boolean(details.alert_id)
    );
  }

  return eventCat === category;
}
