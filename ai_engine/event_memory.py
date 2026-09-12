"""Event Memory module for IBVAP AI Engine.

Module 5: In-Memory Event & Behavioral History.

Sits immediately after Module 4 (ByteTrackTracker) in the analytics pipeline::

    VideoSource (M1)
        -> FramePreprocessor (M2)
        -> YOLODetector (M3)
        -> ByteTrackTracker (M4)
        -> EventMemory (M5)  <- this module

EventMemory maintains persistent, per-track state across consecutive frames.
For every track ID that passes through it, it records:

* identity metadata (class, first/last seen)
* per-frame aggregates (frame count, last confidence, last bbox, last center)
* a bounded positional history deque ready for downstream movement/direction
  calculations in later modules

This module deliberately does **not** implement:

* movement trail rendering
* direction / velocity computation
* loitering detection
* fence / zone logic
* alerts
* evidence snapshots
* database persistence (belongs to M13+)

All of those belong to later modules and are strictly out of scope here.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Deque, Dict, List, Optional, Tuple

from ai_engine.tracker import TrackedObject

logger = logging.getLogger("ibvap.ai_engine.event_memory")

# ---------------------------------------------------------------------------
# Default constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_HISTORY: int = 100
"""Default maximum number of positional observations kept per track."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PositionalObservation:
    """A single positional snapshot for a tracked object.

    Immutable record of where an object was observed at a specific moment.
    Stored in a bounded deque inside :class:`TrackMemory` so that later
    modules can compute movement, speed, and direction without accessing the
    raw tracker output again.

    Attributes:
        frame_time: Wall-clock timestamp of the observation (UTC).
        center_x: Horizontal center of the bounding box in pixels.
        center_y: Vertical center of the bounding box in pixels.
        x1: Left edge of the bounding box (pixels).
        y1: Top edge of the bounding box (pixels).
        x2: Right edge of the bounding box (pixels).
        y2: Bottom edge of the bounding box (pixels).
        confidence: Detection confidence score in [0.0, 1.0].
    """

    frame_time: datetime
    center_x: float
    center_y: float
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float


@dataclass
class TrackMemory:
    """Persistent memory record for a single tracked object.

    Created the first time a ``track_id`` is seen and updated in place on
    every subsequent frame.  The record is **never** automatically deleted
    when a track is absent from a frame — ByteTrack can temporarily lose
    detections, so premature deletion would corrupt the history.

    Attributes:
        track_id: The persistent ByteTrack-assigned identifier.
        class_id: COCO class ID of the tracked object.
        class_name: Human-readable class label (e.g. ``'person'``).
        first_seen: Timestamp of the very first observation (immutable).
        last_seen: Timestamp of the most recent observation (updated per frame).
        last_confidence: Detection confidence from the most recent frame.
        last_bbox: Most recent bounding box as ``(x1, y1, x2, y2)``.
        last_center: Most recent centroid as ``(center_x, center_y)``.
        frame_count: Number of frames in which this track has been observed.
        history: Bounded deque of :class:`PositionalObservation` records,
            oldest at index 0, newest at the right end.
    """

    track_id: int
    class_id: int
    class_name: str
    first_seen: datetime
    last_seen: datetime
    last_confidence: float
    last_bbox: Tuple[int, int, int, int]       # (x1, y1, x2, y2)
    last_center: Tuple[float, float]            # (center_x, center_y)
    frame_count: int
    history: Deque[PositionalObservation] = field(default_factory=deque)


# ---------------------------------------------------------------------------
# EventMemory
# ---------------------------------------------------------------------------


class EventMemory:
    """In-memory per-track behavioral history for the IBVAP pipeline.

    Maintains a :class:`TrackMemory` record for every ``track_id`` that has
    ever been seen.  Records are never automatically purged — they persist
    until :meth:`remove` or :meth:`clear` is called explicitly.  This is
    intentional: ByteTrack can temporarily lose a detection for a frame or
    two without the physical object having disappeared.

    Each record contains identity metadata and a bounded deque of
    :class:`PositionalObservation` instances ready for downstream analysis.

    Typical usage::

        memory = EventMemory(max_history=100)

        for frame in video_frames:
            tracked_objects = tracker.update(frame)
            frame_time = datetime.utcnow()
            for obj in tracked_objects:
                memory.update(obj, frame_time)

        # Inspect accumulated history for a specific track
        record = memory.get(track_id=7)
        history = memory.get_history(track_id=7)

    Args:
        max_history: Maximum number of positional observations retained per
            track.  Oldest observations are discarded first when the deque
            is full.  Must be a positive integer.

    Raises:
        ValueError: If *max_history* is not a positive integer.
    """

    def __init__(self, max_history: int = DEFAULT_MAX_HISTORY) -> None:
        if not isinstance(max_history, int) or max_history < 1:
            raise ValueError(
                f"max_history must be a positive integer, got: {max_history!r}"
            )

        self._max_history: int = max_history
        self._records: Dict[int, TrackMemory] = {}

        logger.info(
            "EventMemory initialized: max_history=%d", self._max_history
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def max_history(self) -> int:
        """Maximum positional observations kept per track."""
        return self._max_history

    @property
    def track_count(self) -> int:
        """Number of unique track IDs currently held in memory."""
        return len(self._records)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def update(self, tracked_object: TrackedObject, frame_time: datetime) -> TrackMemory:
        """Ingest a single TrackedObject observation.

        If the ``track_id`` is new, a fresh :class:`TrackMemory` record is
        created and ``first_seen`` is set to *frame_time*.

        If the ``track_id`` already exists, only the mutable fields are
        updated (``last_seen``, ``last_confidence``, ``last_bbox``,
        ``last_center``, ``frame_count``), while ``first_seen`` is preserved.

        In both cases, a :class:`PositionalObservation` is appended to the
        bounded history deque.

        Args:
            tracked_object: A TrackedObject produced by ByteTrackTracker.
            frame_time: The timestamp associated with the current frame.
                Use a consistent clock (e.g. ``datetime.utcnow()``) for all
                objects in the same frame so that the history is coherent.

        Returns:
            The updated (or newly created) :class:`TrackMemory` record for
            this track ID.

        Raises:
            TypeError: If *tracked_object* is not a TrackedObject, or if
                *frame_time* is not a datetime.
        """
        if not isinstance(tracked_object, TrackedObject):
            raise TypeError(
                f"tracked_object must be a TrackedObject instance, "
                f"got: {type(tracked_object).__name__}"
            )
        if not isinstance(frame_time, datetime):
            raise TypeError(
                f"frame_time must be a datetime instance, "
                f"got: {type(frame_time).__name__}"
            )

        tid = tracked_object.track_id
        cx = (tracked_object.x1 + tracked_object.x2) / 2.0
        cy = (tracked_object.y1 + tracked_object.y2) / 2.0

        observation = PositionalObservation(
            frame_time=frame_time,
            center_x=cx,
            center_y=cy,
            x1=tracked_object.x1,
            y1=tracked_object.y1,
            x2=tracked_object.x2,
            y2=tracked_object.y2,
            confidence=tracked_object.confidence,
        )

        if tid not in self._records:
            # New track — create record
            history_deque: Deque[PositionalObservation] = deque(
                maxlen=self._max_history
            )
            history_deque.append(observation)

            record = TrackMemory(
                track_id=tid,
                class_id=tracked_object.class_id,
                class_name=tracked_object.class_name,
                first_seen=frame_time,
                last_seen=frame_time,
                last_confidence=tracked_object.confidence,
                last_bbox=(
                    tracked_object.x1,
                    tracked_object.y1,
                    tracked_object.x2,
                    tracked_object.y2,
                ),
                last_center=(cx, cy),
                frame_count=1,
                history=history_deque,
            )
            self._records[tid] = record

            logger.debug(
                "EventMemory: new track %d (%s) first seen at %s",
                tid, tracked_object.class_name, frame_time.isoformat(),
            )
        else:
            # Existing track — update in place
            record = self._records[tid]
            record.last_seen = frame_time
            record.last_confidence = tracked_object.confidence
            record.last_bbox = (
                tracked_object.x1,
                tracked_object.y1,
                tracked_object.x2,
                tracked_object.y2,
            )
            record.last_center = (cx, cy)
            record.frame_count += 1
            record.history.append(observation)   # deque handles maxlen eviction

            logger.debug(
                "EventMemory: updated track %d (%s) frame_count=%d history=%d",
                tid, record.class_name, record.frame_count, len(record.history),
            )

        return record

    def update_batch(
        self,
        tracked_objects: List[TrackedObject],
        frame_time: datetime,
    ) -> List[TrackMemory]:
        """Convenience method to update all objects from a single frame.

        Calls :meth:`update` for each object in *tracked_objects* with the
        same *frame_time*, which ensures temporal consistency within a frame.

        Args:
            tracked_objects: The list of TrackedObject instances returned by
                ByteTrackTracker.update.
            frame_time: Timestamp for all objects in this frame.

        Returns:
            List of :class:`TrackMemory` records in the same order as the
            input list.

        Raises:
            TypeError: Propagated from :meth:`update` on bad input types.
        """
        return [self.update(obj, frame_time) for obj in tracked_objects]

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get(self, track_id: int) -> Optional[TrackMemory]:
        """Return the TrackMemory record for *track_id*, or ``None``.

        Args:
            track_id: The ByteTrack-assigned track identifier.

        Returns:
            The :class:`TrackMemory` record if *track_id* is known,
            otherwise ``None``.
        """
        return self._records.get(track_id)

    def exists(self, track_id: int) -> bool:
        """Return ``True`` if *track_id* is currently held in memory.

        Args:
            track_id: The ByteTrack-assigned track identifier.

        Returns:
            ``True`` if the track has been seen at least once since the last
            :meth:`clear`, ``False`` otherwise.
        """
        return track_id in self._records

    def get_history(self, track_id: int) -> List[PositionalObservation]:
        """Return a safe copy of the positional history for *track_id*.

        The returned list is a snapshot — mutating it does **not** affect the
        internal deque.  Observations are ordered oldest-first.

        Args:
            track_id: The ByteTrack-assigned track identifier.

        Returns:
            Ordered list of :class:`PositionalObservation` instances
            (oldest first), or an empty list if the track is unknown.
        """
        record = self._records.get(track_id)
        if record is None:
            return []
        return list(record.history)  # snapshot; caller cannot corrupt internal state

    def get_all(self) -> Dict[int, TrackMemory]:
        """Return a shallow-copy mapping of all track records.

        The returned dict is a snapshot of ``{track_id: TrackMemory}`` at the
        time of the call.  The :class:`TrackMemory` objects themselves are
        shared references — do not mutate them externally.

        Returns:
            Dictionary mapping each known ``track_id`` to its
            :class:`TrackMemory` record.
        """
        return dict(self._records)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def remove(self, track_id: int) -> bool:
        """Explicitly remove the memory record for *track_id*.

        Useful when external logic (e.g. a timeout policy in a later module)
        determines that a track has definitively disappeared.

        Args:
            track_id: The ByteTrack-assigned track identifier.

        Returns:
            ``True`` if the track was found and removed, ``False`` if it
            was not present.
        """
        if track_id in self._records:
            del self._records[track_id]
            logger.debug("EventMemory: removed track %d", track_id)
            return True
        return False

    def clear(self) -> int:
        """Remove all track records from memory.

        Returns:
            The number of records that were cleared.
        """
        count = len(self._records)
        self._records.clear()
        logger.info("EventMemory: cleared %d track records.", count)
        return count

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        """Return the number of track records currently in memory."""
        return len(self._records)

    def __contains__(self, track_id: int) -> bool:
        """Support ``track_id in memory`` syntax."""
        return track_id in self._records

    def __repr__(self) -> str:
        return (
            f"EventMemory(max_history={self._max_history}, "
            f"tracks={len(self._records)})"
        )
