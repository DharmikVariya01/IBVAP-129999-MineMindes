"""Fence Breach Detection System for IBVAP AI Engine.

Module 8: Temporal Geofence Breach Detection.

Sits immediately after Module 7 (ZoneManager) in the video analytics pipeline::

    VideoSource (M1)
        -> FramePreprocessor (M2)
        -> YOLODetector (M3)
        -> ByteTrackTracker (M4)
        -> EventMemory (M5)
        -> MovementAnalyzer (M6)
        -> ZoneManager (M7)
        -> FenceBreachDetector (M8)  <- this module

Objective:
    Detect when a tracked object crosses a configured virtual fence by adding
    temporal crossing state logic:
        OUTSIDE -> INSIDE
    across the configured virtual fence.

Key Design Principles:
- Reuses M4 track IDs and M7 fence classifications (ZoneResult.fence_inside).
- Does NOT create another tracker, EventMemory, or zone system.
- Temporal state machine: tracks previous and current fence states per track_id.
- First Observation Rule: If a track is first observed as INSIDE, no breach event
  is generated. It only initializes the state. A breach requires an observed
  transition from OUTSIDE to INSIDE.
- Duplicate Protection: Continuous residence inside the fence (e.g., 100 consecutive
  frames) yields exactly ONE breach event for that initial crossing.
- Re-entry: If a track exits (INSIDE -> OUTSIDE) and later re-enters (OUTSIDE -> INSIDE),
  a new breach event is generated.
- Strict Track Isolation: Per-track state is keyed solely by track_id with zero
  state leakage across tracks.
- Safe Lifecycle: Supports resetting all tracks, resetting individual tracks, and
  cleaning up stale tracks without mutating M4/M5/M7 states.
- Immutability: FenceBreachEvent instances are frozen and immutable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from ai_engine.zones import ZoneResult

logger = logging.getLogger("ibvap.ai_engine.fence_breach")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class FenceBreachError(Exception):
    """Base exception for all fence breach detection errors."""
    pass


class FenceBreachValidationError(FenceBreachError):
    """Raised when an input or configuration parameter is invalid."""
    pass


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class FenceState(str, Enum):
    """Spatial membership state of an object relative to the virtual fence."""

    OUTSIDE = "OUTSIDE"
    INSIDE = "INSIDE"
    UNKNOWN = "UNKNOWN"


class BreachEventType(str, Enum):
    """Types of fence-related boundary crossing events."""

    FENCE_BREACH = "FENCE_BREACH"


# ---------------------------------------------------------------------------
# Structured Event
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FenceBreachEvent:
    """Immutable event representing an OUTSIDE -> INSIDE virtual fence breach.

    Attributes:
        track_id: Persistent tracking ID of the breaching object.
        event_type: Type identifier (BreachEventType.FENCE_BREACH).
        previous_state: State prior to breach (FenceState.OUTSIDE).
        current_state: State after breach (FenceState.INSIDE).
        frame_id: Video frame index at which the breach was detected.
        timestamp: Time in seconds or system timestamp of detection.
        center: Centroid (cx, cy) of the object at the time of breach.
        fence_id: Identifier of the breached virtual fence, if specified.
        zone_id: Identifier of the containing zone, if available from M7.
        breach_count: Total breach count for this track (including this event).
        metadata: Additional diagnostic context.
    """

    track_id: int
    event_type: BreachEventType = BreachEventType.FENCE_BREACH
    previous_state: FenceState = FenceState.OUTSIDE
    current_state: FenceState = FenceState.INSIDE
    frame_id: Optional[int] = None
    timestamp: Optional[float] = None
    center: Optional[Tuple[int, int]] = None
    fence_id: Optional[str] = None
    zone_id: Optional[str] = None
    breach_count: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-Track Internal Temporal State
# ---------------------------------------------------------------------------

@dataclass
class TrackFenceState:
    """Internal temporal state maintained per track for breach detection.

    Attributes:
        track_id: Tracking identifier.
        previous_state: Fence state in previous evaluation frame, or None if first frame.
        current_state: Fence state in most recent evaluation frame.
        breach_count: Number of times this track has breached the fence.
        total_inside_frames: Total number of frames the track has been inside.
        last_frame_id: Frame ID of the most recent update.
        last_timestamp: Timestamp of the most recent update.
        last_center: Most recent center coordinate (cx, cy).
    """

    track_id: int
    previous_state: Optional[FenceState] = None
    current_state: FenceState = FenceState.UNKNOWN
    breach_count: int = 0
    total_inside_frames: int = 0
    last_frame_id: Optional[int] = None
    last_timestamp: Optional[float] = None
    last_center: Optional[Tuple[int, int]] = None


# ---------------------------------------------------------------------------
# FenceBreachDetector Engine
# ---------------------------------------------------------------------------

class FenceBreachDetector:
    """Evaluates spatial fence membership over time to detect fence breaches.

    Detects temporal transitions where a tracked object crosses from OUTSIDE
    to INSIDE a configured virtual fence.

    Enforces:
    - First observation rule: If first observed INSIDE, do not generate a breach.
    - Duplicate protection: Continuous presence INSIDE does not emit repeated events.
    - Re-entry: Re-entering from OUTSIDE to INSIDE produces a new event.
    - Strict track isolation: State is stored strictly per track_id.
    """

    def __init__(self, default_fence_id: Optional[str] = "virtual_fence") -> None:
        """Initialize the FenceBreachDetector.

        Args:
            default_fence_id: Default identifier for the virtual fence.
        """
        self._default_fence_id: Optional[str] = default_fence_id
        self._tracks: Dict[int, TrackFenceState] = {}
        self._total_breaches: int = 0
        self._frame_count: int = 0

    @property
    def default_fence_id(self) -> Optional[str]:
        """Default virtual fence identifier."""
        return self._default_fence_id

    @property
    def total_breaches(self) -> int:
        """Total number of breach events detected across all tracks since reset."""
        return self._total_breaches

    def __len__(self) -> int:
        """Return the number of active tracked objects in temporal state."""
        return len(self._tracks)

    def __contains__(self, track_id: int) -> bool:
        """Check if a track_id is present in temporal state."""
        return track_id in self._tracks

    # -----------------------------------------------------------------------
    # Validation Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _validate_track_id(track_id: Any) -> int:
        """Validate and cast track_id.

        Raises:
            FenceBreachValidationError: If track_id is not a valid integer >= 0.
        """
        if track_id is None or isinstance(track_id, bool):
            raise FenceBreachValidationError(f"Invalid track_id: {track_id!r}")
        try:
            tid = int(track_id)
        except (ValueError, TypeError):
            raise FenceBreachValidationError(f"track_id must be an integer, got {track_id!r}")
        if tid < 0:
            raise FenceBreachValidationError(f"track_id must be non-negative, got {tid}")
        return tid

    @staticmethod
    def _normalize_fence_state(fence_inside: Any) -> FenceState:
        """Convert a boolean or string fence membership to FenceState.

        Raises:
            FenceBreachValidationError: If fence_inside cannot be evaluated.
        """
        if fence_inside is None:
            raise FenceBreachValidationError("fence_inside cannot be None")
        if isinstance(fence_inside, bool):
            return FenceState.INSIDE if fence_inside else FenceState.OUTSIDE
        if isinstance(fence_inside, FenceState):
            return fence_inside
        if isinstance(fence_inside, str):
            clean = fence_inside.strip().upper()
            if clean in (FenceState.INSIDE.value, "TRUE", "1"):
                return FenceState.INSIDE
            if clean in (FenceState.OUTSIDE.value, "FALSE", "0"):
                return FenceState.OUTSIDE
            if clean == FenceState.UNKNOWN.value:
                return FenceState.UNKNOWN
            raise FenceBreachValidationError(f"Unknown fence state string: {fence_inside!r}")
        if isinstance(fence_inside, (int, float)):
            return FenceState.INSIDE if bool(fence_inside) else FenceState.OUTSIDE

        raise FenceBreachValidationError(f"Unsupported fence_inside type: {type(fence_inside)}")

    # -----------------------------------------------------------------------
    # Core Update Logic
    # -----------------------------------------------------------------------

    def update_track(
        self,
        track_id: int,
        fence_inside: Union[bool, FenceState, str],
        frame_id: Optional[int] = None,
        timestamp: Optional[float] = None,
        center: Optional[Tuple[int, int]] = None,
        fence_id: Optional[str] = None,
        zone_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[FenceBreachEvent]:
        """Update temporal state for a single track and detect breach transitions.

        Transition Rules:
        - First observation:
            - If first observed OUTSIDE: initialized to OUTSIDE. No breach.
            - If first observed INSIDE: initialized to INSIDE. No breach (first-observation rule).
        - Subsequent updates:
            - OUTSIDE -> INSIDE: **BREACH DETECTED**. Emits FenceBreachEvent.
            - INSIDE -> INSIDE: No breach (duplicate protection).
            - INSIDE -> OUTSIDE: No breach (exit).
            - OUTSIDE -> OUTSIDE: No breach.
            - Transitions from or to UNKNOWN do not produce breaches.

        Args:
            track_id: Tracking ID of the object.
            fence_inside: Boolean or FenceState indicating whether object is inside fence.
            frame_id: Video frame number.
            timestamp: Timestamp in seconds.
            center: Object centroid (cx, cy).
            fence_id: Virtual fence identifier.
            zone_id: Zone identifier from M7 if available.
            metadata: Diagnostic context dictionary.

        Returns:
            FenceBreachEvent if an OUTSIDE -> INSIDE crossing occurred, else None.
        """
        tid = self._validate_track_id(track_id)
        current_state = self._normalize_fence_state(fence_inside)
        target_fence_id = fence_id or self._default_fence_id

        # Normalize center if provided
        norm_center: Optional[Tuple[int, int]] = None
        if center is not None:
            if isinstance(center, (tuple, list)) and len(center) == 2:
                try:
                    norm_center = (int(round(float(center[0]))), int(round(float(center[1]))))
                except (ValueError, TypeError):
                    norm_center = None

        if tid not in self._tracks:
            # First observation of this track
            track_state = TrackFenceState(
                track_id=tid,
                previous_state=None,
                current_state=current_state,
                breach_count=0,
                total_inside_frames=1 if current_state == FenceState.INSIDE else 0,
                last_frame_id=frame_id,
                last_timestamp=timestamp,
                last_center=norm_center,
            )
            self._tracks[tid] = track_state
            logger.debug(
                "Track %d first observed with state %s (no breach)", tid, current_state.value
            )
            return None

        # Existing track: retrieve state and update
        track_state = self._tracks[tid]
        previous_state = track_state.current_state

        # Update per-track fields
        track_state.previous_state = previous_state
        track_state.current_state = current_state
        track_state.last_frame_id = frame_id
        track_state.last_timestamp = timestamp
        if norm_center is not None:
            track_state.last_center = norm_center

        if current_state == FenceState.INSIDE:
            track_state.total_inside_frames += 1

        # Evaluate transition
        if previous_state == FenceState.OUTSIDE and current_state == FenceState.INSIDE:
            # OUTSIDE -> INSIDE transition = BREACH!
            track_state.breach_count += 1
            self._total_breaches += 1

            event_meta = dict(metadata or {})
            event_meta.setdefault("total_inside_frames", track_state.total_inside_frames)

            event = FenceBreachEvent(
                track_id=tid,
                event_type=BreachEventType.FENCE_BREACH,
                previous_state=FenceState.OUTSIDE,
                current_state=FenceState.INSIDE,
                frame_id=frame_id,
                timestamp=timestamp,
                center=norm_center if norm_center is not None else track_state.last_center,
                fence_id=target_fence_id,
                zone_id=zone_id,
                breach_count=track_state.breach_count,
                metadata=event_meta,
            )
            logger.info(
                "FENCE BREACH: Track %d crossed OUTSIDE -> INSIDE (breach #%d at frame %s)",
                tid,
                track_state.breach_count,
                frame_id,
            )
            return event

        return None

    def update_from_zone_result(
        self,
        zone_result: ZoneResult,
        frame_id: Optional[int] = None,
        timestamp: Optional[float] = None,
        fence_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[FenceBreachEvent]:
        """Update temporal state directly from a Module 7 ZoneResult.

        Consumes ZoneResult.track_id, ZoneResult.fence_inside, ZoneResult.center,
        and ZoneResult.zone_id.

        Args:
            zone_result: ZoneResult produced by M7 ZoneManager.
            frame_id: Video frame index.
            timestamp: Timestamp in seconds.
            fence_id: Virtual fence identifier.
            metadata: Diagnostic context.

        Returns:
            FenceBreachEvent if breach occurred, else None.
        """
        if not isinstance(zone_result, ZoneResult):
            raise FenceBreachValidationError(
                f"Expected ZoneResult instance, got {type(zone_result)}"
            )

        return self.update_track(
            track_id=zone_result.track_id,
            fence_inside=zone_result.fence_inside,
            frame_id=frame_id,
            timestamp=timestamp,
            center=zone_result.center,
            fence_id=fence_id,
            zone_id=zone_result.zone_id,
            metadata=metadata,
        )

    def update_batch(
        self,
        zone_results: Sequence[ZoneResult],
        frame_id: Optional[int] = None,
        timestamp: Optional[float] = None,
        fence_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[FenceBreachEvent]:
        """Process a batch of ZoneResult objects from a video frame.

        Args:
            zone_results: Sequence of ZoneResult instances from M7.
            frame_id: Video frame index.
            timestamp: Timestamp in seconds.
            fence_id: Virtual fence identifier.
            metadata: Diagnostic context.

        Returns:
            List of FenceBreachEvent instances detected in this batch.
        """
        if zone_results is None:
            return []

        breach_events: List[FenceBreachEvent] = []
        for zr in zone_results:
            event = self.update_from_zone_result(
                zone_result=zr,
                frame_id=frame_id,
                timestamp=timestamp,
                fence_id=fence_id,
                metadata=metadata,
            )
            if event is not None:
                breach_events.append(event)

        return breach_events

    # -----------------------------------------------------------------------
    # State Inspection
    # -----------------------------------------------------------------------

    def get_track_state(self, track_id: int) -> Optional[TrackFenceState]:
        """Retrieve a copy or view of internal state for a track_id.

        Args:
            track_id: Tracking ID.

        Returns:
            TrackFenceState or None if track_id is unknown.
        """
        if track_id is None:
            return None
        try:
            tid = int(track_id)
        except (ValueError, TypeError):
            return None
        return self._tracks.get(tid)

    def get_fence_state(self, track_id: int) -> FenceState:
        """Get the current fence membership state of a track."""
        state = self.get_track_state(track_id)
        if state is None:
            return FenceState.UNKNOWN
        return state.current_state

    def get_breach_count(self, track_id: int) -> int:
        """Get the total breach count for a specific track."""
        state = self.get_track_state(track_id)
        return state.breach_count if state else 0

    def get_active_track_ids(self) -> List[int]:
        """Return list of track IDs currently managed in temporal state."""
        return list(self._tracks.keys())

    # -----------------------------------------------------------------------
    # Reset and Lifecycle Management
    # -----------------------------------------------------------------------

    def reset(self) -> None:
        """Reset all tracking states and counters.

        Clears all per-track fence states. Does not alter external tracker
        or EventMemory states.
        """
        self._tracks.clear()
        self._total_breaches = 0
        logger.debug("FenceBreachDetector: All tracking states reset.")

    def reset_track(self, track_id: int) -> bool:
        """Reset temporal state for a single track.

        Args:
            track_id: Tracking ID to remove.

        Returns:
            True if the track was found and removed, False otherwise.
        """
        try:
            tid = self._validate_track_id(track_id)
        except FenceBreachValidationError:
            return False

        if tid in self._tracks:
            del self._tracks[tid]
            logger.debug("FenceBreachDetector: Track %d state reset.", tid)
            return True
        return False

    def cleanup_stale_tracks(self, active_track_ids: Sequence[int]) -> List[int]:
        """Remove state for tracks that are no longer active.

        Args:
            active_track_ids: Sequence of currently active track IDs from M4.

        Returns:
            List of purged track IDs.
        """
        if active_track_ids is None:
            return []

        active_set: Set[int] = set()
        for tid in active_track_ids:
            try:
                active_set.add(int(tid))
            except (ValueError, TypeError):
                continue

        stale_ids = [tid for tid in self._tracks if tid not in active_set]
        for tid in stale_ids:
            del self._tracks[tid]

        if stale_ids:
            logger.debug("FenceBreachDetector: Purged %d stale tracks: %s", len(stale_ids), stale_ids)

        return stale_ids
