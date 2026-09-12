"""Tracker module for IBVAP AI Engine.

Module 4: ByteTrack Persistent Object Tracking.
Wraps the existing Module 3 YOLODetector and uses Ultralytics' built-in
ByteTrack tracker to assign persistent track IDs to detected persons and
vehicles across consecutive video frames.

The tracker state persists between consecutive ``update()`` calls so that
the same physical object retains the same ``track_id`` throughout a video
sequence.  A ``reset()`` method is provided to clear state when switching
to a new video source.

This module does NOT implement movement history, trajectory trails,
direction detection, event memory, or any behavioral analytics — those
belong to later modules.
"""

from dataclasses import dataclass
import logging
from typing import Dict, List, Optional

import numpy as np

from ai_engine.detector import (
    DEFAULT_TARGET_CLASSES,
    InvalidFrameError,
    YOLODetector,
)

logger = logging.getLogger("ibvap.ai_engine.tracker")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TrackingError(Exception):
    """Base exception for tracking errors in IBVAP AI Engine."""
    pass


# ---------------------------------------------------------------------------
# Tracked object data class
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TrackedObject:
    """A single tracked object result.

    Contains the persistent ``track_id`` assigned by ByteTrack plus all
    detection metadata.  All bounding-box coordinates are absolute pixel
    values relative to the input frame dimensions.

    Attributes:
        track_id: Persistent identifier assigned by ByteTrack.  The same
            physical object retains this ID across consecutive frames.
        class_id: COCO class ID (e.g. 0 for person, 2 for car).
        class_name: Human-readable class label (e.g. 'person', 'car').
        confidence: Detection confidence score in [0.0, 1.0].
        x1: Left edge of the bounding box (pixels).
        y1: Top edge of the bounding box (pixels).
        x2: Right edge of the bounding box (pixels).
        y2: Bottom edge of the bounding box (pixels).
    """
    track_id: int
    class_id: int
    class_name: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int


# ---------------------------------------------------------------------------
# ByteTrackTracker
# ---------------------------------------------------------------------------

class ByteTrackTracker:
    """ByteTrack persistent multi-object tracker for the IBVAP pipeline.

    Wraps a pre-existing :class:`YOLODetector` and calls ``model.track()``
    with ``persist=True`` so that ByteTrack state is maintained across
    consecutive frames.  The same YOLO model instance is reused — no
    duplicate model loading occurs.

    Typical usage::

        detector = YOLODetector(device="cpu")
        tracker  = ByteTrackTracker(detector)

        for frame in video_frames:
            tracked = tracker.update(frame)
            for obj in tracked:
                print(f"ID {obj.track_id}: {obj.class_name} "
                      f"{obj.confidence:.2f}")

    Important:
        The same ``ByteTrackTracker`` instance must process every frame of a
        single video sequence.  Creating a new tracker per frame would reset
        all IDs.
    """

    def __init__(
        self,
        detector: YOLODetector,
        tracker_type: str = "bytetrack.yaml",
    ) -> None:
        """Initialize the ByteTrack tracker.

        Args:
            detector: An already-constructed :class:`YOLODetector` whose
                underlying YOLO model will be used for ``model.track()``.
            tracker_type: Ultralytics tracker config file name.
                Defaults to ``"bytetrack.yaml"`` (bundled with Ultralytics).

        Raises:
            TypeError: If *detector* is not a :class:`YOLODetector`.
        """
        if not isinstance(detector, YOLODetector):
            raise TypeError(
                f"detector must be a YOLODetector instance, "
                f"got: {type(detector).__name__}"
            )

        self._detector = detector
        self._tracker_type = tracker_type
        self._frame_count: int = 0

        # Target class IDs for filtering (mirrors M3)
        self._target_classes: Dict[int, str] = dict(detector.target_classes)
        self._target_ids = set(self._target_classes.keys())

        logger.info(
            "ByteTrackTracker initialized: tracker=%s, detector=%r",
            self._tracker_type,
            self._detector,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def detector(self) -> YOLODetector:
        """Return the underlying YOLODetector instance."""
        return self._detector

    @property
    def tracker_type(self) -> str:
        """Return the tracker configuration filename."""
        return self._tracker_type

    @property
    def frame_count(self) -> int:
        """Return the number of frames processed since last reset."""
        return self._frame_count

    @property
    def target_classes(self) -> Dict[int, str]:
        """Return the target class mapping."""
        return dict(self._target_classes)

    # ------------------------------------------------------------------
    # Core tracking
    # ------------------------------------------------------------------

    def update(self, frame: np.ndarray) -> List[TrackedObject]:
        """Process a single BGR frame and return tracked objects.

        Calls the underlying YOLO model's ``track()`` method with
        ``persist=True`` so that ByteTrack maintains state between
        consecutive invocations.

        Args:
            frame: BGR uint8 NumPy frame (H×W×3) — same contract as
                :meth:`YOLODetector.detect`.

        Returns:
            List of :class:`TrackedObject` instances for the target
            classes whose confidence exceeds the detector's threshold.
            Objects that could not be assigned a track ID (e.g. during
            the very first appearance) are still returned with the
            ID assigned by ByteTrack.

        Raises:
            InvalidFrameError: If *frame* does not meet BGR uint8 specs.
            TrackingError: If the tracking call fails.
        """
        # Validate using the existing M3 validator
        self._detector.validate_frame(frame)

        frame_h, frame_w = frame.shape[:2]

        try:
            results = self._detector.model.track(
                source=frame,
                conf=self._detector.conf_threshold,
                imgsz=self._detector.imgsz,
                device=self._detector.device,
                classes=list(self._target_ids),
                tracker=self._tracker_type,
                persist=True,
                verbose=False,
            )
        except Exception as err:
            raise TrackingError(f"ByteTrack tracking failed: {err}") from err

        self._frame_count += 1
        tracked_objects: List[TrackedObject] = []

        if not results or len(results) == 0:
            return tracked_objects

        result = results[0]

        if result.boxes is None or len(result.boxes) == 0:
            return tracked_objects

        boxes = result.boxes

        # boxes.id is None when no tracks are established yet
        has_ids = boxes.id is not None

        for i in range(len(boxes)):
            cls_id = int(boxes.cls[i].item())

            # Double-check class filtering
            if cls_id not in self._target_ids:
                continue

            # Skip detections without a track ID assignment
            if not has_ids:
                continue

            track_id_val = boxes.id[i]
            if track_id_val is None:
                continue

            track_id = int(track_id_val.item())
            conf = float(boxes.conf[i].item())

            # Pixel coordinates (xyxy format), clamped to frame bounds
            xyxy = boxes.xyxy[i]
            x1 = max(0, int(xyxy[0].item()))
            y1 = max(0, int(xyxy[1].item()))
            x2 = min(frame_w, int(xyxy[2].item()))
            y2 = min(frame_h, int(xyxy[3].item()))

            tracked_objects.append(TrackedObject(
                track_id=track_id,
                class_id=cls_id,
                class_name=self._target_classes.get(cls_id, f"class_{cls_id}"),
                confidence=conf,
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
            ))

        return tracked_objects

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset the tracker state for a new video sequence.

        After calling ``reset()`` a subsequent ``update()`` will start
        with fresh IDs.  The YOLO model itself is NOT reloaded.
        """
        # Ultralytics stores tracker state on the model predictor.
        # Setting predictor to None forces Ultralytics to create a
        # completely fresh predictor (and tracker) on the next track()
        # call.  Simply clearing predictor.trackers = [] causes an
        # IndexError inside Ultralytics when it tries to access
        # trackers[0] on the next invocation.
        model = self._detector.model
        if hasattr(model, "predictor") and model.predictor is not None:
            model.predictor = None
            logger.info("ByteTrack tracker state reset (predictor cleared).")
        else:
            logger.debug(
                "Model predictor not yet initialized — nothing to reset."
            )
        self._frame_count = 0

    # ------------------------------------------------------------------
    # Dunder methods
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"ByteTrackTracker(tracker='{self._tracker_type}', "
            f"detector={self._detector!r}, "
            f"frames_processed={self._frame_count})"
        )
