"""Loitering Detection System for IBVAP AI Engine.

Module 9: Temporal and Spatial Loitering Analytics.

Sits immediately after Module 5 (EventMemory) and Module 7 (ZoneManager)
in the video analytics pipeline::

    VideoSource (M1)
        -> FramePreprocessor (M2)
        -> YOLODetector (M3)
        -> ByteTrackTracker (M4)
        -> EventMemory (M5)
        -> MovementAnalyzer (M6)
        -> ZoneManager (M7)
        -> FenceBreachDetector (M8)
        -> LoiteringDetector (M9)  <- this module

Objective:
    Detect when a tracked person or vehicle remains within a limited spatial
    area for longer than a configurable duration (default: 30.0 seconds).

Core Logic:
    Loitering is based on BOTH:
    1. Time spent in the area (>= loitering_duration_seconds)
    2. Limited spatial displacement (staying within spatial_radius of an anchor)

    An object moving continuously across the camera for 60 seconds is NOT
    classified as loitering. A stationary or localized object remaining
    within the spatial radius for >= 30 seconds triggers a LOITERING event.

Key Design Principles:
    - Default Loitering Threshold: 30.0 seconds.
    - Persistent Track IDs: Uses existing M4 track IDs and M5 behavioral history.
    - Non-duplication: Does NOT duplicate ByteTrack tracker or EventMemory.
    - First Observation Rule: A newly observed track is NOT immediately loitering.
      It must accumulate sufficient elapsed time and spatial evidence.
    - Duplicate Trigger Prevention: A track that stays in the loitering area for
      45+ seconds produces exactly ONE loitering event on initial qualification
      (NOT_LOITERING -> LOITERING). Continuing in the area (LOITERING -> LOITERING)
      emits no duplicate events.
    - Re-qualification: If an object exits its localized anchor area (exceeding
      spatial_radius) and later settles into a new area for >= 30.0s, a new
      loitering event is generated.
    - Strict Track Isolation: Each track is evaluated independently with zero
      state leakage across track IDs.
    - Safe Lifecycle: Supports reset all, reset one track, and stale track cleanup
      without mutating M4/M5/M6/M7/M8 state.
    - Immutability: LoiteringResult and LoiteringEvent instances are frozen and
      immutable.
    - Zone Integration: Seamlessly associates optional M7 zone metadata (zone_id,
      zone_name, zone_type) while remaining fully independent of hardcoded zones.
    - M8 Independence: Fence breach detection and loitering detection operate
      independently without coupling or combined events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from ai_engine.event_memory import EventMemory, PositionalObservation, TrackMemory
from ai_engine.zones import ZoneResult

logger = logging.getLogger("ibvap.ai_engine.loitering")


# ---------------------------------------------------------------------------
# Default Constants
# ---------------------------------------------------------------------------

DEFAULT_LOITERING_DURATION: float = 30.0
"""Default duration threshold in seconds to classify an object as loitering."""

DEFAULT_SPATIAL_RADIUS: float = 50.0
"""Default maximum spatial radius (in pixels) defining a localized area."""

DEFAULT_MIN_OBSERVATIONS: int = 5
"""Minimum number of observations required before declaring a loitering event."""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LoiteringError(Exception):
    """Base exception for all loitering detection errors."""
    pass


class LoiteringValidationError(LoiteringError):
    """Raised when an input or configuration parameter is invalid."""
    pass


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class LoiteringState(str, Enum):
    """Spatial-temporal loitering state of a tracked object."""

    NOT_LOITERING = "NOT_LOITERING"
    LOITERING = "LOITERING"


# ---------------------------------------------------------------------------
# Structured Events and Results
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LoiteringEvent:
    """Immutable event emitted when an object transitions from NOT_LOITERING to LOITERING.

    Emitted exactly once per qualifying loitering episode.

    Attributes:
        track_id: Persistent tracking ID of the loitering object.
        event_type: Identifier of the event type ("LOITERING").
        duration_seconds: Elapsed duration spent within the spatial radius.
        spatial_displacement: Distance in pixels from the spatial anchor.
        spatial_radius: Configured spatial radius threshold in pixels.
        threshold_seconds: Configured duration threshold in seconds.
        anchor_center: Centroid (cx, cy) of the localized spatial anchor.
        current_center: Current centroid (cx, cy) of the object.
        frame_id: Video frame index at which the event triggered.
        timestamp: Timestamp (datetime or seconds) of detection.
        zone_id: Identifier of the zone where loitering occurred, if any.
        zone_name: Name of the zone where loitering occurred, if any.
        zone_type: Type of the zone where loitering occurred, if any.
        loitering_count: Sequence number of loitering episodes for this track.
    """

    track_id: int
    event_type: str = "LOITERING"
    duration_seconds: float = 0.0
    spatial_displacement: float = 0.0
    spatial_radius: float = DEFAULT_SPATIAL_RADIUS
    threshold_seconds: float = DEFAULT_LOITERING_DURATION
    anchor_center: Tuple[float, float] = (0.0, 0.0)
    current_center: Tuple[float, float] = (0.0, 0.0)
    frame_id: Optional[int] = None
    timestamp: Optional[Union[datetime, float]] = None
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    zone_type: Optional[str] = None
    loitering_count: int = 1


@dataclass(frozen=True)
class LoiteringResult:
    """Immutable per-frame evaluation result for a single tracked object.

    Attributes:
        track_id: Persistent tracking ID.
        state: Current loitering state (NOT_LOITERING or LOITERING).
        is_loitering: Boolean flag indicating if object is currently loitering.
        duration_seconds: Accumulated time spent within current spatial anchor.
        spatial_displacement: Distance in pixels from the spatial anchor.
        spatial_radius: Configured spatial radius threshold.
        threshold_seconds: Configured duration threshold in seconds.
        anchor_center: Centroid (cx, cy) of the localized spatial anchor.
        current_center: Current centroid (cx, cy) of the object.
        observations_count: Number of observations recorded within current anchor.
        new_event: Non-None only on the exact frame the track transitions
            NOT_LOITERING -> LOITERING.
        status_reason: Human-readable status explanation.
        zone_id: Associated zone identifier, if any.
        zone_name: Associated zone name, if any.
        zone_type: Associated zone type, if any.
    """

    track_id: int
    state: LoiteringState
    is_loitering: bool
    duration_seconds: float
    spatial_displacement: float
    spatial_radius: float
    threshold_seconds: float
    anchor_center: Tuple[float, float]
    current_center: Tuple[float, float]
    observations_count: int
    new_event: Optional[LoiteringEvent] = None
    status_reason: str = ""
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    zone_type: Optional[str] = None


@dataclass
class TrackLoiteringState:
    """Internal mutable tracking state maintained per track ID."""

    track_id: int
    anchor_center: Tuple[float, float]
    anchor_start_time: Optional[Union[datetime, float]]
    anchor_start_frame: int
    last_seen_time: Optional[Union[datetime, float]]
    last_seen_frame: int
    current_center: Tuple[float, float]
    accumulated_duration: float = 0.0
    max_displacement: float = 0.0
    observations_count: int = 0
    state: LoiteringState = LoiteringState.NOT_LOITERING
    event_emitted: bool = False
    total_loitering_events: int = 0
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    zone_type: Optional[str] = None


# ---------------------------------------------------------------------------
# LoiteringDetector Engine
# ---------------------------------------------------------------------------

class LoiteringDetector:
    """Module 9: Loitering Detection Engine.

    Detects prolonged localized presence of tracked objects by analyzing
    temporal duration and spatial displacement.

    Args:
        loitering_duration_seconds: Minimum seconds an object must remain within
            a localized spatial radius to qualify as loitering. Default: 30.0s.
        spatial_radius: Maximum radius in pixels from the spatial anchor point
            defining the localized area. Default: 50.0 pixels.
        movement_radius: Alias for spatial_radius. If provided, overrides
            spatial_radius.
        min_observations: Minimum consecutive/accumulated observations required
            before declaring a loitering event. Default: 5.
        fps: Optional source video frame rate. Used to compute elapsed time
            when timestamps are frame-based.
        movement_threshold: Optional displacement threshold for secondary
            movement classification.

    Raises:
        LoiteringValidationError: If configuration arguments are invalid.
    """

    def __init__(
        self,
        loitering_duration_seconds: float = DEFAULT_LOITERING_DURATION,
        spatial_radius: float = DEFAULT_SPATIAL_RADIUS,
        movement_radius: Optional[float] = None,
        min_observations: int = DEFAULT_MIN_OBSERVATIONS,
        fps: Optional[float] = None,
        movement_threshold: Optional[float] = None,
    ) -> None:
        effective_radius = movement_radius if movement_radius is not None else spatial_radius

        if not isinstance(loitering_duration_seconds, (int, float)) or loitering_duration_seconds <= 0:
            raise LoiteringValidationError(
                f"loitering_duration_seconds must be a positive number, got: {loitering_duration_seconds!r}"
            )
        if not isinstance(effective_radius, (int, float)) or effective_radius <= 0:
            raise LoiteringValidationError(
                f"spatial_radius must be a positive number, got: {effective_radius!r}"
            )
        if not isinstance(min_observations, int) or min_observations < 1:
            raise LoiteringValidationError(
                f"min_observations must be an integer >= 1, got: {min_observations!r}"
            )
        if fps is not None:
            if not isinstance(fps, (int, float)) or fps <= 0:
                raise LoiteringValidationError(
                    f"fps must be a positive number when specified, got: {fps!r}"
                )
            self._fps: Optional[float] = float(fps)
        else:
            self._fps = None

        if movement_threshold is not None:
            if not isinstance(movement_threshold, (int, float)) or movement_threshold < 0:
                raise LoiteringValidationError(
                    f"movement_threshold must be a non-negative number, got: {movement_threshold!r}"
                )
            self._movement_threshold: Optional[float] = float(movement_threshold)
        else:
            self._movement_threshold = None

        self._loitering_duration: float = float(loitering_duration_seconds)
        self._spatial_radius: float = float(effective_radius)
        self._min_observations: int = min_observations

        self._tracks: Dict[int, TrackLoiteringState] = {}
        self._total_events: int = 0

        logger.info(
            "LoiteringDetector initialized: threshold=%.1fs, radius=%.1fpx, min_obs=%d, fps=%s",
            self._loitering_duration,
            self._spatial_radius,
            self._min_observations,
            str(self._fps),
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def loitering_duration_seconds(self) -> float:
        """Configured loitering duration threshold in seconds."""
        return self._loitering_duration

    @property
    def spatial_radius(self) -> float:
        """Configured spatial radius threshold in pixels."""
        return self._spatial_radius

    @property
    def min_observations(self) -> int:
        """Minimum observations required before declaring loitering."""
        return self._min_observations

    @property
    def fps(self) -> Optional[float]:
        """Configured video frame rate, if any."""
        return self._fps

    @property
    def movement_threshold(self) -> Optional[float]:
        """Optional movement threshold, if any."""
        return self._movement_threshold

    @property
    def tracked_count(self) -> int:
        """Number of unique tracks currently monitored in internal state."""
        return len(self._tracks)

    @property
    def active_loitering_count(self) -> int:
        """Number of tracks currently in LOITERING state."""
        return sum(1 for t in self._tracks.values() if t.state == LoiteringState.LOITERING)

    @property
    def total_loitering_events(self) -> int:
        """Cumulative count of distinct loitering events emitted."""
        return self._total_events

    # ------------------------------------------------------------------
    # Time Computation
    # ------------------------------------------------------------------

    def _calculate_elapsed(
        self,
        start_time: Optional[Union[datetime, float]],
        curr_time: Optional[Union[datetime, float]],
        start_frame: int,
        curr_frame: int,
    ) -> float:
        """Derive elapsed seconds consistently across datetime, float, or FPS modes."""
        # Mode 1: Datetime instances (UTC or wall-clock from M5)
        if isinstance(start_time, datetime) and isinstance(curr_time, datetime):
            return max(0.0, (curr_time - start_time).total_seconds())

        # Mode 2: Numeric timestamps (seconds, e.g. time.perf_counter() or video PTS)
        if isinstance(start_time, (int, float)) and isinstance(curr_time, (int, float)):
            return max(0.0, float(curr_time - start_time))

        # Mode 3: Frame delta with known video FPS
        if self._fps is not None and self._fps > 0:
            frame_delta = curr_frame - start_frame
            return max(0.0, float(frame_delta) / self._fps)

        # Fallback: No timing info available
        return 0.0

    # ------------------------------------------------------------------
    # Core Update APIs
    # ------------------------------------------------------------------

    def update(
        self,
        track_id: int,
        center: Tuple[float, float],
        timestamp: Optional[Union[datetime, float]] = None,
        frame_id: Optional[int] = None,
        zone_id: Optional[str] = None,
        zone_name: Optional[str] = None,
        zone_type: Optional[str] = None,
    ) -> LoiteringResult:
        """Update loitering status for a single track given its centroid.

        Args:
            track_id: Persistent track identifier (positive integer).
            center: Current centroid coordinate as (cx, cy).
            timestamp: Timestamp of the observation (datetime or float seconds).
            frame_id: Monotonic video frame index (integer >= 0).
            zone_id: Optional identifier of the primary zone containing center.
            zone_name: Optional name of the primary zone.
            zone_type: Optional string representation of the primary zone type.

        Returns:
            Immutable :class:`LoiteringResult` containing updated state and any
            newly triggered event.

        Raises:
            LoiteringValidationError: If input types or values are invalid.
        """
        # Validate track_id
        if not isinstance(track_id, int) or isinstance(track_id, bool) or track_id <= 0:
            raise LoiteringValidationError(
                f"track_id must be a positive integer, got: {track_id!r}"
            )

        # Validate center
        if not isinstance(center, (tuple, list)) or len(center) != 2:
            raise LoiteringValidationError(
                f"center must be a 2-element sequence (cx, cy), got: {center!r}"
            )
        cx, cy = center
        if not isinstance(cx, (int, float)) or not isinstance(cy, (int, float)):
            raise LoiteringValidationError(
                f"center coordinates must be numeric, got: ({cx!r}, {cy!r})"
            )
        if math.isnan(cx) or math.isnan(cy) or math.isinf(cx) or math.isinf(cy):
            raise LoiteringValidationError(
                f"center coordinates cannot be NaN or Inf, got: ({cx!r}, {cy!r})"
            )

        curr_frame = frame_id if frame_id is not None else 0
        curr_cx, curr_cy = float(cx), float(cy)

        # 1. First observation of this track: initialize anchor and return NOT_LOITERING
        if track_id not in self._tracks:
            track_state = TrackLoiteringState(
                track_id=track_id,
                anchor_center=(curr_cx, curr_cy),
                anchor_start_time=timestamp,
                anchor_start_frame=curr_frame,
                last_seen_time=timestamp,
                last_seen_frame=curr_frame,
                current_center=(curr_cx, curr_cy),
                accumulated_duration=0.0,
                max_displacement=0.0,
                observations_count=1,
                state=LoiteringState.NOT_LOITERING,
                event_emitted=False,
                total_loitering_events=0,
                zone_id=zone_id,
                zone_name=zone_name,
                zone_type=zone_type,
            )
            self._tracks[track_id] = track_state

            return LoiteringResult(
                track_id=track_id,
                state=LoiteringState.NOT_LOITERING,
                is_loitering=False,
                duration_seconds=0.0,
                spatial_displacement=0.0,
                spatial_radius=self._spatial_radius,
                threshold_seconds=self._loitering_duration,
                anchor_center=(curr_cx, curr_cy),
                current_center=(curr_cx, curr_cy),
                observations_count=1,
                new_event=None,
                status_reason="First observation: spatial anchor established.",
                zone_id=zone_id,
                zone_name=zone_name,
                zone_type=zone_type,
            )

        # 2. Subsequent observation: evaluate distance from anchor
        track_state = self._tracks[track_id]
        anchor_cx, anchor_cy = track_state.anchor_center
        displacement = math.hypot(curr_cx - anchor_cx, curr_cy - anchor_cy)

        # Update last seen metadata
        track_state.last_seen_time = timestamp
        track_state.last_seen_frame = curr_frame
        track_state.current_center = (curr_cx, curr_cy)
        track_state.zone_id = zone_id
        track_state.zone_name = zone_name
        track_state.zone_type = zone_type

        # Case A: Within spatial radius (localized presence)
        if displacement <= self._spatial_radius:
            track_state.observations_count += 1
            if displacement > track_state.max_displacement:
                track_state.max_displacement = displacement

            elapsed = self._calculate_elapsed(
                track_state.anchor_start_time,
                timestamp,
                track_state.anchor_start_frame,
                curr_frame,
            )
            track_state.accumulated_duration = elapsed

            qualifies = (
                elapsed >= self._loitering_duration
                and track_state.observations_count >= self._min_observations
            )

            if qualifies:
                if track_state.state != LoiteringState.LOITERING:
                    # Transition NOT_LOITERING -> LOITERING (trigger once)
                    track_state.state = LoiteringState.LOITERING
                    track_state.event_emitted = True
                    track_state.total_loitering_events += 1
                    self._total_events += 1

                    event = LoiteringEvent(
                        track_id=track_id,
                        event_type="LOITERING",
                        duration_seconds=elapsed,
                        spatial_displacement=displacement,
                        spatial_radius=self._spatial_radius,
                        threshold_seconds=self._loitering_duration,
                        anchor_center=track_state.anchor_center,
                        current_center=(curr_cx, curr_cy),
                        frame_id=frame_id,
                        timestamp=timestamp,
                        zone_id=zone_id,
                        zone_name=zone_name,
                        zone_type=zone_type,
                        loitering_count=track_state.total_loitering_events,
                    )

                    return LoiteringResult(
                        track_id=track_id,
                        state=LoiteringState.LOITERING,
                        is_loitering=True,
                        duration_seconds=elapsed,
                        spatial_displacement=displacement,
                        spatial_radius=self._spatial_radius,
                        threshold_seconds=self._loitering_duration,
                        anchor_center=track_state.anchor_center,
                        current_center=(curr_cx, curr_cy),
                        observations_count=track_state.observations_count,
                        new_event=event,
                        status_reason=(
                            f"Loitering detected: remained within {displacement:.1f}px "
                            f"(<= {self._spatial_radius:.1f}px) for {elapsed:.1f}s "
                            f"(>= {self._loitering_duration:.1f}s)."
                        ),
                        zone_id=zone_id,
                        zone_name=zone_name,
                        zone_type=zone_type,
                    )
                else:
                    # Continuing LOITERING (no duplicate event)
                    return LoiteringResult(
                        track_id=track_id,
                        state=LoiteringState.LOITERING,
                        is_loitering=True,
                        duration_seconds=elapsed,
                        spatial_displacement=displacement,
                        spatial_radius=self._spatial_radius,
                        threshold_seconds=self._loitering_duration,
                        anchor_center=track_state.anchor_center,
                        current_center=(curr_cx, curr_cy),
                        observations_count=track_state.observations_count,
                        new_event=None,
                        status_reason=(
                            f"Continuing loitering ({elapsed:.1f}s, "
                            f"displacement {displacement:.1f}px)."
                        ),
                        zone_id=zone_id,
                        zone_name=zone_name,
                        zone_type=zone_type,
                    )
            else:
                # Still accumulating duration (< 30s or < min_observations)
                return LoiteringResult(
                    track_id=track_id,
                    state=LoiteringState.NOT_LOITERING,
                    is_loitering=False,
                    duration_seconds=elapsed,
                    spatial_displacement=displacement,
                    spatial_radius=self._spatial_radius,
                    threshold_seconds=self._loitering_duration,
                    anchor_center=track_state.anchor_center,
                    current_center=(curr_cx, curr_cy),
                    observations_count=track_state.observations_count,
                    new_event=None,
                    status_reason=(
                        f"Accumulating dwell duration: {elapsed:.1f}s / "
                        f"{self._loitering_duration:.1f}s (obs={track_state.observations_count})."
                    ),
                    zone_id=zone_id,
                    zone_name=zone_name,
                    zone_type=zone_type,
                )

        # Case B: Outside spatial radius (movement beyond localized area)
        was_loitering = (track_state.state == LoiteringState.LOITERING)

        # Reset spatial anchor to current position
        track_state.anchor_center = (curr_cx, curr_cy)
        track_state.anchor_start_time = timestamp
        track_state.anchor_start_frame = curr_frame
        track_state.accumulated_duration = 0.0
        track_state.max_displacement = 0.0
        track_state.observations_count = 1
        track_state.state = LoiteringState.NOT_LOITERING
        track_state.event_emitted = False

        reason = (
            f"Object left localized area ({displacement:.1f}px > {self._spatial_radius:.1f}px); "
            f"loitering ended, anchor reset."
            if was_loitering
            else (
                f"Object moved beyond radius ({displacement:.1f}px > {self._spatial_radius:.1f}px); "
                f"anchor reset."
            )
        )

        return LoiteringResult(
            track_id=track_id,
            state=LoiteringState.NOT_LOITERING,
            is_loitering=False,
            duration_seconds=0.0,
            spatial_displacement=0.0,
            spatial_radius=self._spatial_radius,
            threshold_seconds=self._loitering_duration,
            anchor_center=(curr_cx, curr_cy),
            current_center=(curr_cx, curr_cy),
            observations_count=1,
            new_event=None,
            status_reason=reason,
            zone_id=zone_id,
            zone_name=zone_name,
            zone_type=zone_type,
        )

    def update_track(
        self,
        track_memory: TrackMemory,
        frame_id: Optional[int] = None,
        timestamp: Optional[Union[datetime, float]] = None,
        zone_result: Optional[Union[ZoneResult, Dict[str, Any]]] = None,
    ) -> LoiteringResult:
        """Update loitering status using an M5 TrackMemory instance directly.

        Args:
            track_memory: TrackMemory instance from M5 EventMemory.
            frame_id: Optional frame index.
            timestamp: Optional timestamp override. Defaults to track_memory.last_seen.
            zone_result: Optional M7 ZoneResult or dictionary with zone metadata.

        Returns:
            :class:`LoiteringResult` for this track.

        Raises:
            LoiteringValidationError: If track_memory is not a TrackMemory.
        """
        if not isinstance(track_memory, TrackMemory):
            raise LoiteringValidationError(
                f"track_memory must be a TrackMemory instance, got: {type(track_memory).__name__}"
            )

        eff_time = timestamp if timestamp is not None else track_memory.last_seen
        cx, cy = track_memory.last_center

        zone_id = None
        zone_name = None
        zone_type = None

        if zone_result is not None:
            if isinstance(zone_result, ZoneResult):
                zone_id = zone_result.zone_id
                zone_name = zone_result.zone_name
                zone_type = (
                    zone_result.zone_type.value
                    if zone_result.zone_type
                    else None
                )
            elif isinstance(zone_result, dict):
                zone_id = zone_result.get("zone_id")
                zone_name = zone_result.get("zone_name")
                zone_type = zone_result.get("zone_type")

        return self.update(
            track_id=track_memory.track_id,
            center=(cx, cy),
            timestamp=eff_time,
            frame_id=frame_id,
            zone_id=zone_id,
            zone_name=zone_name,
            zone_type=zone_type,
        )

    def update_from_memory(
        self,
        event_memory: EventMemory,
        active_track_ids: Optional[Sequence[int]] = None,
        frame_id: Optional[int] = None,
        timestamp: Optional[Union[datetime, float]] = None,
        zone_results: Optional[Sequence[ZoneResult]] = None,
    ) -> List[LoiteringResult]:
        """Process all active tracks from M5 EventMemory for the current frame.

        Args:
            event_memory: M5 EventMemory instance.
            active_track_ids: Optional list of active track IDs in current frame.
                If omitted, processes all tracks currently held in event_memory.
            frame_id: Optional frame index.
            timestamp: Optional timestamp for all objects in this frame.
            zone_results: Optional sequence of M7 ZoneResults matching current frame.

        Returns:
            List of :class:`LoiteringResult` records for all processed tracks.

        Raises:
            LoiteringValidationError: If event_memory is not an EventMemory instance.
        """
        if not isinstance(event_memory, EventMemory):
            raise LoiteringValidationError(
                f"event_memory must be an EventMemory instance, got: {type(event_memory).__name__}"
            )

        # Build zone map if zone_results provided
        zone_map: Dict[int, ZoneResult] = {}
        if zone_results:
            for zr in zone_results:
                if isinstance(zr, ZoneResult):
                    zone_map[zr.track_id] = zr

        targets = (
            active_track_ids
            if active_track_ids is not None
            else list(event_memory.get_all_track_ids())
        )

        results: List[LoiteringResult] = []
        for tid in targets:
            record = event_memory.get(tid)
            if record is not None:
                zr = zone_map.get(tid)
                res = self.update_track(
                    track_memory=record,
                    frame_id=frame_id,
                    timestamp=timestamp,
                    zone_result=zr,
                )
                results.append(res)

        return results

    def update_batch(
        self,
        observations: Sequence[Tuple[int, Tuple[float, float]]],
        timestamp: Optional[Union[datetime, float]] = None,
        frame_id: Optional[int] = None,
        zone_map: Optional[Dict[int, Union[ZoneResult, Dict[str, Any]]]] = None,
    ) -> List[LoiteringResult]:
        """Convenience method to process multiple (track_id, center) pairs in a single frame.

        Args:
            observations: List of (track_id, (cx, cy)) tuples.
            timestamp: Timestamp for this batch.
            frame_id: Monotonic frame index.
            zone_map: Optional mapping of track_id -> ZoneResult or dict.

        Returns:
            List of :class:`LoiteringResult` records in matching order.
        """
        results: List[LoiteringResult] = []
        zmap = zone_map or {}

        for tid, center in observations:
            z_info = zmap.get(tid)
            zone_id, zone_name, zone_type = None, None, None
            if isinstance(z_info, ZoneResult):
                zone_id = z_info.zone_id
                zone_name = z_info.zone_name
                zone_type = z_info.zone_type.value if z_info.zone_type else None
            elif isinstance(z_info, dict):
                zone_id = z_info.get("zone_id")
                zone_name = z_info.get("zone_name")
                zone_type = z_info.get("zone_type")

            res = self.update(
                track_id=tid,
                center=center,
                timestamp=timestamp,
                frame_id=frame_id,
                zone_id=zone_id,
                zone_name=zone_name,
                zone_type=zone_type,
            )
            results.append(res)

        return results

    # ------------------------------------------------------------------
    # Query APIs
    # ------------------------------------------------------------------

    def get_state(self, track_id: int) -> LoiteringState:
        """Return the current LoiteringState for track_id, or NOT_LOITERING if unknown."""
        track = self._tracks.get(track_id)
        return track.state if track else LoiteringState.NOT_LOITERING

    def is_loitering(self, track_id: int) -> bool:
        """Return True if track_id is currently classified as LOITERING."""
        return self.get_state(track_id) == LoiteringState.LOITERING

    def get_duration(self, track_id: int) -> float:
        """Return accumulated dwell duration in seconds for track_id."""
        track = self._tracks.get(track_id)
        return track.accumulated_duration if track else 0.0

    def get_track_state(self, track_id: int) -> Optional[TrackLoiteringState]:
        """Return internal TrackLoiteringState record or None."""
        return self._tracks.get(track_id)

    def get_active_loitering_tracks(self) -> List[int]:
        """Return list of track IDs currently in LOITERING state."""
        return [tid for tid, t in self._tracks.items() if t.state == LoiteringState.LOITERING]

    # ------------------------------------------------------------------
    # Lifecycle & Cleanup APIs
    # ------------------------------------------------------------------

    def reset_track(self, track_id: int) -> bool:
        """Reset internal loitering state for a single track ID.

        Args:
            track_id: Track ID to remove.

        Returns:
            True if the track was found and removed, False otherwise.
        """
        if track_id in self._tracks:
            del self._tracks[track_id]
            logger.debug("LoiteringDetector: reset track #%d", track_id)
            return True
        return False

    def reset(self) -> None:
        """Reset all internal loitering tracks and event counters."""
        self._tracks.clear()
        self._total_events = 0
        logger.info("LoiteringDetector: full reset executed.")

    def clear(self) -> None:
        """Alias for reset()."""
        self.reset()

    def cleanup_stale_tracks(
        self,
        active_track_ids: Sequence[int],
        max_stale_seconds: Optional[float] = None,
        max_stale_frames: Optional[int] = None,
        current_time: Optional[Union[datetime, float]] = None,
        current_frame: Optional[int] = None,
    ) -> List[int]:
        """Remove tracks that are no longer active or have exceeded max_stale thresholds.

        Does NOT mutate M4 tracker state or M5 history.

        Args:
            active_track_ids: Sequence of track IDs active in the current frame.
            max_stale_seconds: Optional maximum seconds since last seen before
                a track is purged.
            max_stale_frames: Optional maximum frames since last seen before
                a track is purged.
            current_time: Current timestamp for stale time evaluation.
            current_frame: Current frame index for stale frame evaluation.

        Returns:
            List of track IDs that were removed.
        """
        active_set = set(active_track_ids)
        to_remove: List[int] = []

        for tid, track in list(self._tracks.items()):
            if tid not in active_set:
                if max_stale_frames is not None and current_frame is not None:
                    # Evaluate frame delta since last seen
                    frames_stale = current_frame - track.last_seen_frame
                    if frames_stale >= max_stale_frames:
                        to_remove.append(tid)
                elif max_stale_seconds is not None and current_time is not None:
                    # Evaluate time elapsed since last seen
                    elapsed_stale = self._calculate_elapsed(
                        track.last_seen_time,
                        current_time,
                        track.last_seen_frame,
                        track.last_seen_frame,
                    )
                    if elapsed_stale >= max_stale_seconds:
                        to_remove.append(tid)
                else:
                    # Immediate removal when absent from active tracks
                    to_remove.append(tid)

        for tid in to_remove:
            del self._tracks[tid]

        if to_remove:
            logger.debug("LoiteringDetector: purged %d stale tracks: %s", len(to_remove), to_remove)

        return to_remove
