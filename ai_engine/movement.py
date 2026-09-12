"""Movement Analysis module for IBVAP AI Engine.

Module 6: Movement Trail & Direction Detection.

Sits immediately after Module 5 (EventMemory) in the analytics pipeline::

    VideoSource (M1)
        -> FramePreprocessor (M2)
        -> YOLODetector (M3)
        -> ByteTrackTracker (M4)
        -> EventMemory (M5)
        -> MovementAnalyzer (M6)  <- this module

MovementAnalyzer reads positional history from M5 EventMemory and provides,
for each persistent track_id:

* Movement state   (STATIONARY / MOVING)
* Primary direction (LEFT / RIGHT / UP / DOWN / STATIONARY)
* Euclidean displacement from recent observations
* Movement trail   (ordered center-point list, bounded to a configurable length)
* Toward/Away/Parallel classification relative to a configurable reference line

Design constraints
------------------
* Does NOT duplicate tracking, detection, or event-memory logic.
* Does NOT mutate M5's internal history.
* Does NOT implement virtual fences, zones, loitering, alerts, evidence,
  database, FastAPI, WebSocket, or any other later-module concern.
* All geometry is image-space (pixel coordinates).  No GPS/geographic math.
* The reference_line is optional.  When absent, toward/away yields UNKNOWN.
* Configurable thresholds prevent noise from being misclassified as movement.
* Deterministic and unit-testable with no external services.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Sequence, Tuple

from ai_engine.event_memory import EventMemory, PositionalObservation

logger = logging.getLogger("ibvap.ai_engine.movement")

# ---------------------------------------------------------------------------
# Default thresholds
# ---------------------------------------------------------------------------

DEFAULT_MOVEMENT_THRESHOLD: float = 5.0
"""Minimum Euclidean pixel displacement to classify as MOVING (not STATIONARY).

This guards against sub-pixel centroid jitter from the YOLO detector.
Tune upward for noisy cameras; tune downward for slow-moving subjects.
"""

DEFAULT_MIN_HISTORY: int = 2
"""Minimum positional observations required before any direction is reported.

With fewer than this many observations there is no displacement vector.
"""

DEFAULT_TRAIL_LENGTH: int = 30
"""Default maximum number of center points returned by get_trail().

Does not create a new history — it slices the M5 deque.
"""

DEFAULT_DIRECTION_WINDOW: int = 5
"""Number of recent observations to average when computing direction.

Averaging over several recent frames avoids single-frame detection jitter
flipping the direction label.  Must be >= 2.
"""

DEFAULT_REFERENCE_MIN_DISPLACEMENT: float = 3.0
"""Minimum displacement (px) required for a toward/away classification.

Below this the result is PARALLEL (neither clearly toward nor away).
"""


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class MovementState(str, Enum):
    """Coarse movement state of a tracked object."""

    STATIONARY = "STATIONARY"
    MOVING = "MOVING"


class Direction(str, Enum):
    """Primary direction of movement in image-space.

    Image coordinates: X increases to the RIGHT, Y increases DOWNWARD.
    """

    LEFT = "LEFT"
    RIGHT = "RIGHT"
    UP = "UP"
    DOWN = "DOWN"
    STATIONARY = "STATIONARY"


class BorderRelation(str, Enum):
    """Relationship of movement to a configured reference line / border."""

    TOWARD = "TOWARD"
    AWAY = "AWAY"
    PARALLEL = "PARALLEL"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Reference geometry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReferenceLine:
    """A directed reference line used for toward/away border analysis.

    The line is defined by two image-space points (x1,y1) -> (x2,y2).
    The *outward normal* of this directed line points to the side that is
    considered "away".  Concretely, the normal is computed as:

        n = perpendicular-left of the direction vector (x2-x1, y2-y1)
            i.e. n = (-(y2-y1), (x2-x1))

    A track whose displacement vector has a **positive dot-product** with n
    is classified as TOWARD (crossing toward the inside), and **negative**
    as AWAY.

    Because border semantics ("inside" vs. "outside") are camera-specific,
    callers in M7+ can flip the interpretation by swapping the two points.

    Attributes:
        x1: X-coordinate of the start point (pixels).
        y1: Y-coordinate of the start point (pixels).
        x2: X-coordinate of the end point (pixels).
        y2: Y-coordinate of the end point (pixels).
    """

    x1: float
    y1: float
    x2: float
    y2: float

    # ------------------------------------------------------------------
    # Derived geometry (computed lazily via property)
    # ------------------------------------------------------------------

    def normal(self) -> Tuple[float, float]:
        """Return the unit outward-normal vector of this reference line.

        The normal is the left-perpendicular of the direction vector
        (dx, dy) = (x2-x1, y2-y1), i.e. (-dy, dx), normalised to length 1.

        Returns:
            (nx, ny) unit vector, or (0.0, 0.0) if the line is degenerate.
        """
        dx = self.x2 - self.x1
        dy = self.y2 - self.y1
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return (0.0, 0.0)
        # Left-perpendicular (pointing "toward" side by convention)
        nx = -dy / length
        ny = dx / length
        return (nx, ny)

    def validate(self) -> None:
        """Raise ValueError if the line is degenerate (start == end).

        Raises:
            ValueError: If both endpoints are the same pixel location.
        """
        dx = self.x2 - self.x1
        dy = self.y2 - self.y1
        if math.hypot(dx, dy) < 1e-9:
            raise ValueError(
                f"ReferenceLine start and end points are identical: "
                f"({self.x1}, {self.y1})"
            )


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MovementResult:
    """Structured movement information for a single tracked object.

    All fields are read-only (frozen dataclass).  Later modules consume this
    as a plain data container — they must NOT write back to EventMemory or
    mutate the trail list.

    Attributes:
        track_id: ByteTrack-assigned persistent identifier.
        state: Coarse movement classification (STATIONARY / MOVING).
        direction: Primary image-space direction of recent displacement.
        border_relation: Toward/Away/Parallel relative to a ReferenceLine,
            or UNKNOWN when no reference is configured.
        current_center: Most recent centroid ``(cx, cy)`` in pixels.
        previous_center: Oldest center used in the displacement calculation.
            ``None`` when fewer than 2 observations are available.
        displacement: Euclidean pixel distance between *previous_center* and
            *current_center*.  ``0.0`` when history is insufficient.
        dx: Signed horizontal displacement (positive = rightward).
        dy: Signed vertical displacement (positive = downward in image coords).
        trail: Ordered list of ``(cx, cy)`` tuples, oldest first, bounded to
            the configured trail_length.  May be empty for brand-new tracks.
        history_length: Number of positional observations used (from M5).
    """

    track_id: int
    state: MovementState
    direction: Direction
    border_relation: BorderRelation
    current_center: Tuple[float, float]
    previous_center: Optional[Tuple[float, float]]
    displacement: float
    dx: float
    dy: float
    trail: Tuple[Tuple[float, float], ...]   # immutable; ordered oldest-first
    history_length: int


# ---------------------------------------------------------------------------
# MovementAnalyzer
# ---------------------------------------------------------------------------


class MovementAnalyzer:
    """Analyzes movement of tracked objects using M5 EventMemory history.

    Reads from EventMemory; does **not** write to it.

    Typical usage::

        analyzer = MovementAnalyzer(movement_threshold=5.0, trail_length=30)

        # After M4 + M5 have processed a frame:
        for track_id in memory.get_all():
            result = analyzer.analyze(track_id, memory)
            print(result.direction, result.state)

    Args:
        movement_threshold: Euclidean pixel displacement below which an object
            is classified as STATIONARY.  Default: 5.0 px.
        min_history: Minimum positional observations needed before direction
            and displacement are computed.  Default: 2.
        trail_length: Maximum number of trail points returned by
            :meth:`get_trail`.  Default: 30.
        direction_window: Number of recent observations averaged for the
            direction calculation, to smooth single-frame jitter.  Default: 5.
        reference_line: Optional :class:`ReferenceLine` for toward/away
            classification relative to a border.  When ``None``, border_relation
            is always ``BorderRelation.UNKNOWN``.
        reference_min_displacement: Minimum displacement (px) required to
            classify as TOWARD or AWAY rather than PARALLEL.  Default: 3.0.

    Raises:
        ValueError: If any numeric threshold is out of range, or if the
            supplied reference_line is degenerate.
    """

    def __init__(
        self,
        movement_threshold: float = DEFAULT_MOVEMENT_THRESHOLD,
        min_history: int = DEFAULT_MIN_HISTORY,
        trail_length: int = DEFAULT_TRAIL_LENGTH,
        direction_window: int = DEFAULT_DIRECTION_WINDOW,
        reference_line: Optional[ReferenceLine] = None,
        reference_min_displacement: float = DEFAULT_REFERENCE_MIN_DISPLACEMENT,
    ) -> None:
        if movement_threshold < 0:
            raise ValueError(
                f"movement_threshold must be >= 0, got {movement_threshold!r}"
            )
        if not isinstance(min_history, int) or min_history < 2:
            raise ValueError(
                f"min_history must be an integer >= 2, got {min_history!r}"
            )
        if not isinstance(trail_length, int) or trail_length < 1:
            raise ValueError(
                f"trail_length must be a positive integer, got {trail_length!r}"
            )
        if not isinstance(direction_window, int) or direction_window < 2:
            raise ValueError(
                f"direction_window must be an integer >= 2, "
                f"got {direction_window!r}"
            )
        if reference_min_displacement < 0:
            raise ValueError(
                f"reference_min_displacement must be >= 0, "
                f"got {reference_min_displacement!r}"
            )
        if reference_line is not None:
            reference_line.validate()

        self._movement_threshold = movement_threshold
        self._min_history = min_history
        self._trail_length = trail_length
        self._direction_window = direction_window
        self._reference_line = reference_line
        self._reference_min_displacement = reference_min_displacement

        logger.info(
            "MovementAnalyzer initialized: threshold=%.1f px, min_history=%d, "
            "trail_length=%d, direction_window=%d, reference_line=%s",
            self._movement_threshold,
            self._min_history,
            self._trail_length,
            self._direction_window,
            self._reference_line,
        )

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def movement_threshold(self) -> float:
        """Pixel displacement threshold separating STATIONARY from MOVING."""
        return self._movement_threshold

    @property
    def min_history(self) -> int:
        """Minimum observations before direction can be computed."""
        return self._min_history

    @property
    def trail_length(self) -> int:
        """Maximum number of trail points returned by get_trail()."""
        return self._trail_length

    @property
    def direction_window(self) -> int:
        """Number of recent observations averaged for direction."""
        return self._direction_window

    @property
    def reference_line(self) -> Optional[ReferenceLine]:
        """The configured reference line, or None."""
        return self._reference_line

    @property
    def reference_min_displacement(self) -> float:
        """Minimum displacement (px) to classify as TOWARD or AWAY."""
        return self._reference_min_displacement

    # ------------------------------------------------------------------
    # Primary API
    # ------------------------------------------------------------------

    def analyze(self, track_id: int, memory: EventMemory) -> MovementResult:
        """Compute full movement information for *track_id* from *memory*.

        Reads the positional history stored by M5 EventMemory and returns a
        :class:`MovementResult` describing the object's movement state,
        direction, displacement, trail, and border relation.

        Does **not** modify *memory* in any way.

        Args:
            track_id: The ByteTrack-assigned identifier to analyze.
            memory: M5 :class:`EventMemory` instance containing history.

        Returns:
            :class:`MovementResult` for the requested track.  If the track
            is unknown or has insufficient history, safe zero-displacement
            values are returned rather than raising an exception.

        Raises:
            TypeError: If *memory* is not an EventMemory instance.
        """
        if not isinstance(memory, EventMemory):
            raise TypeError(
                f"memory must be an EventMemory instance, "
                f"got: {type(memory).__name__}"
            )

        history = memory.get_history(track_id)  # safe snapshot, no mutation
        return self._compute_result(track_id, history)

    def get_direction(self, track_id: int, memory: EventMemory) -> Direction:
        """Return only the direction for *track_id*.

        Convenience wrapper around :meth:`analyze`.

        Args:
            track_id: Track identifier.
            memory: M5 EventMemory instance.

        Returns:
            :class:`Direction` enum value.
        """
        return self.analyze(track_id, memory).direction

    def get_trail(
        self,
        track_id: int,
        memory: EventMemory,
    ) -> List[Tuple[float, float]]:
        """Return the recent movement trail for *track_id*.

        The trail is a list of ``(cx, cy)`` tuples ordered oldest-first,
        bounded to :attr:`trail_length` points.  The data is sliced from the
        M5 history deque; no second history is maintained.

        Args:
            track_id: Track identifier.
            memory: M5 EventMemory instance.

        Returns:
            List of ``(cx, cy)`` tuples (may be empty for unknown tracks).
        """
        history = memory.get_history(track_id)
        return self._extract_trail(history)

    def analyze_all(self, memory: EventMemory) -> List[MovementResult]:
        """Analyze every track currently held in *memory*.

        Returns results in ascending track_id order.

        Args:
            memory: M5 EventMemory instance.

        Returns:
            List of :class:`MovementResult` objects, one per known track.
        """
        results = []
        for track_id in sorted(memory.get_all().keys()):
            results.append(self.analyze(track_id, memory))
        return results

    # ------------------------------------------------------------------
    # Internal computation helpers
    # ------------------------------------------------------------------

    def _compute_result(
        self,
        track_id: int,
        history: List[PositionalObservation],
    ) -> MovementResult:
        """Build a MovementResult from a history snapshot."""

        n = len(history)
        trail = self._extract_trail(history)

        # Default values for tracks with insufficient history
        if n == 0:
            # Track unknown to memory
            current_center = (0.0, 0.0)
            return MovementResult(
                track_id=track_id,
                state=MovementState.STATIONARY,
                direction=Direction.STATIONARY,
                border_relation=BorderRelation.UNKNOWN,
                current_center=current_center,
                previous_center=None,
                displacement=0.0,
                dx=0.0,
                dy=0.0,
                trail=tuple(trail),
                history_length=0,
            )

        current_center = (history[-1].center_x, history[-1].center_y)

        if n < self._min_history:
            # Not enough history for displacement/direction
            return MovementResult(
                track_id=track_id,
                state=MovementState.STATIONARY,
                direction=Direction.STATIONARY,
                border_relation=BorderRelation.UNKNOWN,
                current_center=current_center,
                previous_center=None,
                displacement=0.0,
                dx=0.0,
                dy=0.0,
                trail=tuple(trail),
                history_length=n,
            )

        # --- Compute displacement using a windowed average ---
        # Window: use up to `direction_window` most-recent observations,
        # anchored so we compare the average of the earliest half of the
        # window to the average of the latest half.
        window_size = min(self._direction_window, n)
        window = history[-window_size:]  # most-recent slice

        # Split window into early and late halves (at least one each)
        mid = window_size // 2
        early_pts = window[:mid] if mid > 0 else [window[0]]
        late_pts = window[mid:] if mid < window_size else [window[-1]]

        # Compute centroid averages
        early_cx = sum(o.center_x for o in early_pts) / len(early_pts)
        early_cy = sum(o.center_y for o in early_pts) / len(early_pts)
        late_cx = sum(o.center_x for o in late_pts) / len(late_pts)
        late_cy = sum(o.center_y for o in late_pts) / len(late_pts)

        dx = late_cx - early_cx
        dy = late_cy - early_cy
        displacement = math.hypot(dx, dy)

        previous_center = (early_cx, early_cy)

        # --- Movement state ---
        state = (
            MovementState.MOVING
            if displacement >= self._movement_threshold
            else MovementState.STATIONARY
        )

        # --- Direction ---
        direction = self._compute_direction(dx, dy, displacement)

        # --- Border relation ---
        border_relation = self._compute_border_relation(dx, dy, displacement)

        return MovementResult(
            track_id=track_id,
            state=state,
            direction=direction,
            border_relation=border_relation,
            current_center=current_center,
            previous_center=previous_center,
            displacement=displacement,
            dx=dx,
            dy=dy,
            trail=tuple(trail),
            history_length=n,
        )

    def _compute_direction(
        self,
        dx: float,
        dy: float,
        displacement: float,
    ) -> Direction:
        """Determine primary image-space direction from a (dx, dy) vector.

        Uses the axis with the larger absolute component.  Returns STATIONARY
        when displacement is below the movement threshold.

        Args:
            dx: Signed horizontal displacement (positive = RIGHT).
            dy: Signed vertical displacement (positive = DOWN in image coords).
            displacement: Pre-computed Euclidean magnitude (avoids recalculation).

        Returns:
            :class:`Direction` enum value.
        """
        if displacement < self._movement_threshold:
            return Direction.STATIONARY

        if abs(dx) >= abs(dy):
            return Direction.RIGHT if dx >= 0 else Direction.LEFT
        else:
            return Direction.DOWN if dy >= 0 else Direction.UP

    def _compute_border_relation(
        self,
        dx: float,
        dy: float,
        displacement: float,
    ) -> BorderRelation:
        """Classify movement relative to the configured reference line.

        Uses the dot-product of (dx, dy) with the reference line's outward
        normal to decide TOWARD / AWAY / PARALLEL.

        Args:
            dx: Signed horizontal displacement.
            dy: Signed vertical displacement.
            displacement: Euclidean magnitude of (dx, dy).

        Returns:
            :class:`BorderRelation` enum value.
        """
        if self._reference_line is None:
            return BorderRelation.UNKNOWN

        if displacement < self._reference_min_displacement:
            return BorderRelation.PARALLEL

        nx, ny = self._reference_line.normal()
        dot = dx * nx + dy * ny

        # Use 10% of displacement as a "parallel band" threshold
        parallel_band = displacement * 0.10
        if abs(dot) < parallel_band:
            return BorderRelation.PARALLEL

        return BorderRelation.TOWARD if dot > 0 else BorderRelation.AWAY

    def _extract_trail(
        self,
        history: List[PositionalObservation],
    ) -> List[Tuple[float, float]]:
        """Extract a bounded, ordered list of trail center-points from history.

        Slices the M5 history list (oldest-first) to at most *trail_length*
        points.  No new deque or history structure is created.

        Args:
            history: Snapshot of M5 positional history (oldest-first list).

        Returns:
            List of ``(cx, cy)`` tuples, oldest-first, length <= trail_length.
        """
        # Take the most-recent trail_length observations
        relevant = history[-self._trail_length :]
        return [(obs.center_x, obs.center_y) for obs in relevant]

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"MovementAnalyzer("
            f"threshold={self._movement_threshold:.1f}, "
            f"min_history={self._min_history}, "
            f"trail_length={self._trail_length}, "
            f"direction_window={self._direction_window}, "
            f"reference_line={self._reference_line!r})"
        )
