"""Virtual Fence & Zone System for IBVAP AI Engine.

Module 7: Spatial Geofencing and Zone Classification.

Sits immediately after Module 4 (ByteTrackTracker) or Module 6 (MovementAnalyzer)
in the video analytics pipeline::

    VideoSource (M1)
        -> FramePreprocessor (M2)
        -> YOLODetector (M3)
        -> ByteTrackTracker (M4)
        -> EventMemory (M5)
        -> MovementAnalyzer (M6)
        -> ZoneManager (M7)  <- this module

ZoneManager allows defining configurable spatial zones (polygons) in image coordinates:
- Virtual Fences (FENCE)
- Normal Surveillance Zones (NORMAL)
- Sensitive Surveillance Zones (SENSITIVE)
- Restricted Perimeter Zones (RESTRICTED)

It evaluates tracked objects (from M4) by determining whether their bounding-box
center point lies inside or outside registered zones using OpenCV pointPolygonTest.

Design constraints:
- Software-only geometric classification in image pixel space.
- Configurable polygon vertices (NO hardcoded border coordinates).
- Boundary behavior: points directly on polygon edges or vertices are classified
  as INSIDE (dist >= 0) to ensure security-first geofencing.
- Deterministic zone priority resolution for overlapping zones:
  RESTRICTED (priority 3) > SENSITIVE (priority 2) > NORMAL (priority 1) > FENCE (priority 0).
  Ties among equal-priority zones are broken deterministically by registration order.
- Virtual fence status (fence_inside) is evaluated and reported independently.
- Independent of alerts, loitering, databases, web APIs, and frontends (M8+).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np

from ai_engine.tracker import TrackedObject

logger = logging.getLogger("ibvap.ai_engine.zones")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ZoneError(Exception):
    """Base exception for all zone-related errors."""
    pass


class ZoneValidationError(ZoneError):
    """Raised when a zone definition or polygon geometry is invalid."""
    pass


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ZoneType(str, Enum):
    """Classification types for surveillance zones."""

    NORMAL = "NORMAL"
    SENSITIVE = "SENSITIVE"
    RESTRICTED = "RESTRICTED"
    FENCE = "FENCE"


# Priority ranking for overlapping zones:
# RESTRICTED > SENSITIVE > NORMAL > FENCE
_ZONE_PRIORITY: Dict[ZoneType, int] = {
    ZoneType.RESTRICTED: 3,
    ZoneType.SENSITIVE: 2,
    ZoneType.NORMAL: 1,
    ZoneType.FENCE: 0,
}

# Default BGR colors for visualization
DEFAULT_ZONE_COLORS: Dict[ZoneType, Tuple[int, int, int]] = {
    ZoneType.NORMAL: (0, 200, 0),        # Green
    ZoneType.SENSITIVE: (0, 165, 255),    # Orange
    ZoneType.RESTRICTED: (0, 0, 230),     # Red
    ZoneType.FENCE: (255, 255, 0),        # Cyan / Yellow-ish
}


# ---------------------------------------------------------------------------
# Zone Data Structure
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Zone:
    """A spatial polygon zone defined in image pixel coordinates.

    Attributes:
        zone_id: Unique string identifier for the zone.
        zone_name: Human-readable name for the zone.
        zone_type: ZoneType category (NORMAL, SENSITIVE, RESTRICTED, FENCE).
        polygon: Sequence of (x, y) vertex coordinates forming the polygon.
            Must contain at least 3 non-collinear/valid points.
        color: Optional BGR color tuple for display overlay.
    """

    zone_id: str
    zone_name: str
    zone_type: ZoneType
    polygon: Tuple[Tuple[int, int], ...]
    color: Optional[Tuple[int, int, int]] = None
    _contour: np.ndarray = field(init=False, repr=False, compare=False)

    def __init__(
        self,
        zone_id: str,
        zone_name: str,
        zone_type: Union[ZoneType, str],
        polygon: Sequence[Union[Tuple[int, int], Sequence[int]]],
        color: Optional[Tuple[int, int, int]] = None,
    ) -> None:
        # Validate zone_id
        if not isinstance(zone_id, str) or not zone_id.strip():
            raise ZoneValidationError(f"zone_id must be a non-empty string, got {zone_id!r}")
        object.__setattr__(self, "zone_id", zone_id.strip())

        # Validate zone_name
        if not isinstance(zone_name, str) or not zone_name.strip():
            raise ZoneValidationError(f"zone_name must be a non-empty string, got {zone_name!r}")
        object.__setattr__(self, "zone_name", zone_name.strip())

        # Validate zone_type
        if isinstance(zone_type, str):
            try:
                validated_type = ZoneType(zone_type.upper().strip())
            except ValueError:
                valid_names = [zt.value for zt in ZoneType]
                raise ZoneValidationError(
                    f"Invalid zone_type {zone_type!r}. Must be one of {valid_names}"
                )
        elif isinstance(zone_type, ZoneType):
            validated_type = zone_type
        else:
            raise ZoneValidationError(f"zone_type must be a ZoneType or str, got {type(zone_type)}")
        object.__setattr__(self, "zone_type", validated_type)

        # Validate polygon points
        if polygon is None or not isinstance(polygon, (list, tuple)):
            raise ZoneValidationError(f"polygon must be a sequence of points, got {type(polygon)}")

        if len(polygon) < 3:
            raise ZoneValidationError(
                f"polygon must contain at least 3 vertices, got {len(polygon)}"
            )

        cleaned_points: List[Tuple[int, int]] = []
        for i, pt in enumerate(polygon):
            if not isinstance(pt, (tuple, list)) or len(pt) != 2:
                raise ZoneValidationError(
                    f"Vertex {i} must be a 2-element sequence (x, y), got {pt!r}"
                )
            x, y = pt[0], pt[1]
            if not isinstance(x, (int, float, np.integer, np.floating)) or not isinstance(
                y, (int, float, np.integer, np.floating)
            ):
                raise ZoneValidationError(
                    f"Vertex {i} coordinates must be numeric, got ({x!r}, {y!r})"
                )
            if np.isnan(x) or np.isnan(y) or np.isinf(x) or np.isinf(y):
                raise ZoneValidationError(
                    f"Vertex {i} coordinates must be finite numbers, got ({x!r}, {y!r})"
                )
            cleaned_points.append((int(round(float(x))), int(round(float(y)))))

        tuple_points = tuple(cleaned_points)
        object.__setattr__(self, "polygon", tuple_points)

        # Precompute OpenCV contour (float32 for precision in pointPolygonTest)
        contour = np.array(tuple_points, dtype=np.float32).reshape((-1, 1, 2))
        object.__setattr__(self, "_contour", contour)

        # Color
        if color is not None:
            if not isinstance(color, (tuple, list)) or len(color) != 3:
                raise ZoneValidationError(f"color must be a 3-element BGR tuple, got {color!r}")
            object.__setattr__(self, "color", (int(color[0]), int(color[1]), int(color[2])))
        else:
            object.__setattr__(self, "color", DEFAULT_ZONE_COLORS.get(validated_type, (255, 255, 255)))

    @property
    def priority(self) -> int:
        """Priority integer for zone conflict resolution (higher = more restrictive)."""
        return _ZONE_PRIORITY.get(self.zone_type, 0)

    def contains_point(
        self,
        point: Union[Tuple[float, float], Sequence[float]],
        include_boundary: bool = True,
    ) -> bool:
        """Check whether a point lies inside this zone's polygon.

        Args:
            point: (x, y) coordinates to test.
            include_boundary: If True (default), points lying directly on polygon
                edges or vertices are considered INSIDE (dist >= 0). If False,
                only strictly interior points are considered INSIDE (dist > 0).

        Returns:
            True if the point is inside (or on boundary if include_boundary=True).
        """
        if point is None or len(point) != 2:
            return False

        px, py = float(point[0]), float(point[1])
        if np.isnan(px) or np.isnan(py) or np.isinf(px) or np.isinf(py):
            return False

        # cv2.pointPolygonTest returns:
        # > 0 for inside, == 0 on edge/vertex, < 0 for outside
        score = cv2.pointPolygonTest(self._contour, (px, py), measureDist=False)
        if include_boundary:
            return score >= 0.0
        return score > 0.0


# ---------------------------------------------------------------------------
# ZoneResult Structure
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ZoneResult:
    """Immutable result of spatial zone classification for a tracked object.

    Attributes:
        track_id: Persistent tracking ID of the object.
        center: Calculated center point (cx, cy) of the bounding box.
        zone_id: Identifier of the highest-priority zone containing the object,
            or None if outside all zones.
        zone_name: Name of the highest-priority zone, or None.
        zone_type: ZoneType of the highest-priority zone, or None.
        inside_zone: True if the object's center is inside any NORMAL, SENSITIVE,
            or RESTRICTED zone, or FENCE zone.
        fence_inside: True if the object's center is inside any FENCE polygon.
    """

    track_id: int
    center: Tuple[int, int]
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    zone_type: Optional[ZoneType] = None
    inside_zone: bool = False
    fence_inside: bool = False


# ---------------------------------------------------------------------------
# ZoneManager
# ---------------------------------------------------------------------------

class ZoneManager:
    """Manages spatial zones and performs point-in-polygon classifications.

    Provides registration, querying, and spatial classification of tracked objects
    and coordinate points against user-defined zones.

    Supports:
    - Normal, Sensitive, and Restricted zones with deterministic priority resolution.
    - Virtual fence zones with independent fence membership tracking.
    - TrackedObject bounding-box center point calculation.
    """

    def __init__(self, include_boundary: bool = True) -> None:
        """Initialize an empty ZoneManager.

        Args:
            include_boundary: Whether points exactly on polygon boundaries
                count as inside. Default is True (security-first geofencing).
        """
        self._zones: Dict[str, Zone] = {}
        self._include_boundary: bool = include_boundary

    @property
    def include_boundary(self) -> bool:
        """Whether points on boundary are considered inside."""
        return self._include_boundary

    def add_zone(self, zone: Zone) -> None:
        """Register a new zone.

        Args:
            zone: Valid Zone instance.

        Raises:
            ZoneValidationError: If zone is not a Zone instance or zone_id already exists.
        """
        if not isinstance(zone, Zone):
            raise ZoneValidationError(f"Expected Zone instance, got {type(zone)}")

        if zone.zone_id in self._zones:
            raise ZoneValidationError(
                f"Zone with ID {zone.zone_id!r} already registered. "
                "Remove it first or use a distinct ID."
            )

        self._zones[zone.zone_id] = zone
        logger.debug("Added zone '%s' (type=%s, points=%d)", zone.zone_id, zone.zone_type, len(zone.polygon))

    def create_zone(
        self,
        zone_id: str,
        zone_name: str,
        zone_type: Union[ZoneType, str],
        polygon: Sequence[Union[Tuple[int, int], Sequence[int]]],
        color: Optional[Tuple[int, int, int]] = None,
    ) -> Zone:
        """Convenience method to construct and add a zone in one call.

        Returns:
            The created and registered Zone instance.
        """
        zone = Zone(
            zone_id=zone_id,
            zone_name=zone_name,
            zone_type=zone_type,
            polygon=polygon,
            color=color,
        )
        self.add_zone(zone)
        return zone

    def remove_zone(self, zone_id: str) -> bool:
        """Remove a zone by its ID.

        Args:
            zone_id: Identifier of the zone to remove.

        Returns:
            True if removed, False if zone_id was not found.
        """
        if zone_id in self._zones:
            del self._zones[zone_id]
            logger.debug("Removed zone '%s'", zone_id)
            return True
        return False

    def get_zone(self, zone_id: str) -> Optional[Zone]:
        """Retrieve a zone by ID, or None if not found."""
        return self._zones.get(zone_id)

    def get_zones(self, zone_type: Optional[ZoneType] = None) -> List[Zone]:
        """Retrieve registered zones, optionally filtered by zone_type.

        Returns:
            List of matching Zone instances.
        """
        if zone_type is None:
            return list(self._zones.values())
        return [z for z in self._zones.values() if z.zone_type == zone_type]

    def clear_zones(self) -> None:
        """Remove all registered zones."""
        self._zones.clear()
        logger.debug("Cleared all zones")

    def __len__(self) -> int:
        """Return number of registered zones."""
        return len(self._zones)

    def __contains__(self, zone_id: str) -> bool:
        """Check if a zone_id is registered."""
        return zone_id in self._zones

    def classify_point(
        self, point: Union[Tuple[float, float], Sequence[float]]
    ) -> Tuple[Optional[Zone], bool]:
        """Classify a 2D coordinate point against all registered zones.

        For surveillance zones (RESTRICTED, SENSITIVE, NORMAL), determines the
        highest-priority containing zone. For virtual fences (FENCE), determines
        if the point is inside any fence zone.

        Priority order:
            RESTRICTED (3) > SENSITIVE (2) > NORMAL (1) > FENCE (0)
        Ties are broken deterministically by registration order.

        Args:
            point: (x, y) coordinate pair.

        Returns:
            A tuple of (highest_priority_zone, fence_inside).
            highest_priority_zone is None if the point is not in any zone.
            fence_inside is True if inside any FENCE polygon.
        """
        if not self._zones:
            return None, False

        fence_inside = False
        matching_surveillance_zones: List[Zone] = []
        matching_fence_zones: List[Zone] = []

        for zone in self._zones.values():
            if zone.contains_point(point, include_boundary=self._include_boundary):
                if zone.zone_type == ZoneType.FENCE:
                    fence_inside = True
                    matching_fence_zones.append(zone)
                else:
                    matching_surveillance_zones.append(zone)

        # Select highest-priority surveillance zone
        if matching_surveillance_zones:
            # Sort by priority descending; Python's stable max preserves registration order for ties
            best_zone = max(matching_surveillance_zones, key=lambda z: z.priority)
            return best_zone, fence_inside

        # If only inside a FENCE zone, the best zone is that FENCE zone
        if matching_fence_zones:
            return matching_fence_zones[0], fence_inside

        return None, fence_inside

    def is_inside_fence(self, point: Union[Tuple[float, float], Sequence[float]]) -> bool:
        """Check whether a point is inside any registered FENCE zone."""
        for zone in self._zones.values():
            if zone.zone_type == ZoneType.FENCE:
                if zone.contains_point(point, include_boundary=self._include_boundary):
                    return True
        return False

    def is_object_inside_fence(self, tracked_object: TrackedObject) -> bool:
        """Check whether a TrackedObject's center point is inside any FENCE zone."""
        center = self.calculate_center(tracked_object)
        return self.is_inside_fence(center)

    @staticmethod
    def calculate_center(tracked_object: Any) -> Tuple[int, int]:
        """Compute the bounding-box center point for a tracked object.

        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2

        Args:
            tracked_object: Object with x1, y1, x2, y2 attributes.

        Returns:
            (cx, cy) integer pixel coordinates.
        """
        try:
            x1 = float(tracked_object.x1)
            y1 = float(tracked_object.y1)
            x2 = float(tracked_object.x2)
            y2 = float(tracked_object.y2)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ZoneValidationError(
                f"Tracked object must have numeric x1, y1, x2, y2 attributes: {exc}"
            )

        cx = int(round((x1 + x2) / 2.0))
        cy = int(round((y1 + y2) / 2.0))
        return cx, cy

    def classify_object(self, tracked_object: TrackedObject) -> ZoneResult:
        """Classify a single TrackedObject against registered zones.

        Calculates the center point from the object's bounding box:
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
        and determines zone and virtual fence membership.

        Args:
            tracked_object: TrackedObject from Module 4.

        Returns:
            Immutable ZoneResult.
        """
        center = self.calculate_center(tracked_object)
        track_id = getattr(tracked_object, "track_id", -1)

        best_zone, fence_inside = self.classify_point(center)

        if best_zone is None:
            return ZoneResult(
                track_id=track_id,
                center=center,
                zone_id=None,
                zone_name=None,
                zone_type=None,
                inside_zone=False,
                fence_inside=fence_inside,
            )

        is_surveillance = best_zone.zone_type in (
            ZoneType.NORMAL,
            ZoneType.SENSITIVE,
            ZoneType.RESTRICTED,
        )

        return ZoneResult(
            track_id=track_id,
            center=center,
            zone_id=best_zone.zone_id,
            zone_name=best_zone.zone_name,
            zone_type=best_zone.zone_type,
            inside_zone=is_surveillance or (best_zone.zone_type == ZoneType.FENCE),
            fence_inside=fence_inside,
        )

    def classify_objects(
        self, tracked_objects: Sequence[TrackedObject]
    ) -> List[ZoneResult]:
        """Classify a batch of TrackedObjects against registered zones.

        Args:
            tracked_objects: Sequence of TrackedObject instances.

        Returns:
            List of ZoneResult instances corresponding to each input object.
        """
        if tracked_objects is None:
            return []
        return [self.classify_object(obj) for obj in tracked_objects]
