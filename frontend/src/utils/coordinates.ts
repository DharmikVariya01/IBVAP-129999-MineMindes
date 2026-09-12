/**
 * Coordinate parsing and validation utility for IBVAP geospatial camera locations.
 *
 * Safely extracts latitude and longitude from location strings or JSON payloads.
 * Strictly avoids inventing fake coordinates when data is invalid or missing.
 */

export interface Coordinates {
  lat: number;
  lng: number;
}

/**
 * Validates whether latitude and longitude numbers are within standard global ranges.
 */
export function isValidCoordinates(lat: number, lng: number): boolean {
  if (typeof lat !== 'number' || typeof lng !== 'number') {
    return false;
  }
  if (Number.isNaN(lat) || Number.isNaN(lng)) {
    return false;
  }
  return lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180;
}

/**
 * Parses a location string into validated {lat, lng} coordinates.
 *
 * Supported formats:
 * - "28.6139, 77.2090" or "28.6139,77.2090" (comma-separated)
 * - "28.6139 77.2090" (space-separated)
 * - "lat: 28.6139, lng: 77.2090" or "lat: 28.6139, lon: 77.2090"
 * - '{"lat": 28.6139, "lng": 77.2090}' or '{"latitude": 28.6139, "longitude": 77.2090}'
 *
 * Returns null if location is null, undefined, empty, unparseable, or out of bounds.
 */
export function parseCoordinates(location: string | null | undefined): Coordinates | null {
  if (!location || typeof location !== 'string') {
    return null;
  }

  const trimmed = location.trim();
  if (!trimmed) {
    return null;
  }

  // 1. Attempt JSON parsing for structured payload
  if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
    try {
      const parsed = JSON.parse(trimmed);
      if (parsed && typeof parsed === 'object') {
        const rawLat = parsed.lat ?? parsed.latitude;
        const rawLng = parsed.lng ?? parsed.lon ?? parsed.longitude;
        const numLat = Number(rawLat);
        const numLng = Number(rawLng);

        if (isValidCoordinates(numLat, numLng)) {
          return { lat: numLat, lng: numLng };
        }
      }
    } catch {
      // Fall through to regex parsing
    }
  }

  // 2. Format: "lat: 28.6139, lng: 77.2090" (case-insensitive)
  const labeledRegex = /lat(?:itude)?\s*[:=]\s*([+-]?\d+(?:\.\d+)?)\s*[,;\s]\s*l(?:ng|on|ongitude)?\s*[:=]\s*([+-]?\d+(?:\.\d+)?)/i;
  const labeledMatch = trimmed.match(labeledRegex);
  if (labeledMatch) {
    const lat = parseFloat(labeledMatch[1]);
    const lng = parseFloat(labeledMatch[2]);
    if (isValidCoordinates(lat, lng)) {
      return { lat, lng };
    }
  }

  // 3. Format: "28.6139, 77.2090" or "28.6139 , 77.2090"
  const commaRegex = /^([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)$/;
  const commaMatch = trimmed.match(commaRegex);
  if (commaMatch) {
    const lat = parseFloat(commaMatch[1]);
    const lng = parseFloat(commaMatch[2]);
    if (isValidCoordinates(lat, lng)) {
      return { lat, lng };
    }
  }

  // 4. Format: "28.6139 77.2090" (two space-separated floating point numbers)
  const spaceRegex = /^([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)$/;
  const spaceMatch = trimmed.match(spaceRegex);
  if (spaceMatch) {
    const lat = parseFloat(spaceMatch[1]);
    const lng = parseFloat(spaceMatch[2]);
    if (isValidCoordinates(lat, lng)) {
      return { lat, lng };
    }
  }

  // Text locations like "Perimeter North", "Sector North Gate", or invalid formats
  return null;
}
