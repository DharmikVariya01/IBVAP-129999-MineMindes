"""Pipeline Orchestrator Module for IBVAP AI Engine.

Module 12: Complete AI Pipeline Integration.
Orchestrates the sequential, stateful execution of Modules 1 through 11:

VideoSource (M1)
    ↓
FramePreprocessor (M2)
    ↓
YOLODetector (M3)
    ↓
ByteTrackTracker (M4)
    ↓
EventMemory (M5)
    ↓
MovementAnalyzer (M6)
    ↓
ZoneManager (M7)
    ↓
FenceBreachDetector (M8)
    ↓
LoiteringDetector (M9)
    ↓
AlertEngine (M10)
    ↓
EvidenceCapture (M11)

This module serves purely as an orchestrator, maintaining existing component
contracts and preserving state across consecutive video frames without duplicating
internal module logic or introducing M13+ dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, Generator, List, Optional, Sequence, Union

import numpy as np

from ai_engine.alerts import Alert, AlertEngine, AlertSeverity, AlertType
from ai_engine.detector import Detection, YOLODetector
from ai_engine.event_memory import EventMemory, TrackMemory
from ai_engine.evidence import EvidenceCapture, EvidenceRecord
from ai_engine.fence_breach import FenceBreachDetector, FenceBreachEvent
from ai_engine.loitering import LoiteringDetector, LoiteringEvent, LoiteringResult
from ai_engine.movement import MovementAnalyzer, MovementResult
from ai_engine.preprocessing import FramePreprocessor, InvalidFrameError, PreprocessingError
from ai_engine.tracker import ByteTrackTracker, TrackedObject
from ai_engine.video_input import VideoSource, VideoSourceError
from ai_engine.zones import ZoneManager, ZoneResult

logger = logging.getLogger("ibvap.ai_engine.pipeline")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class PipelineError(Exception):
    """Base exception for all pipeline orchestration errors."""
    pass


class PipelineValidationError(PipelineError):
    """Raised when pipeline input parameters or frames fail validation."""
    pass


# ---------------------------------------------------------------------------
# Structured Pipeline Result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PipelineResult:
    """Immutable per-frame output from the IBVAP AI Pipeline.

    Contains all analytics generated along the sequential M1–M11 execution path.
    """

    frame_id: int
    timestamp: float
    processed_frame: Optional[np.ndarray] = None
    tracked_objects: List[TrackedObject] = field(default_factory=list)
    track_memories: List[TrackMemory] = field(default_factory=list)
    movement_results: List[MovementResult] = field(default_factory=list)
    zone_results: List[ZoneResult] = field(default_factory=list)
    fence_breach_events: List[FenceBreachEvent] = field(default_factory=list)
    loitering_events: List[LoiteringEvent] = field(default_factory=list)
    alerts: List[Alert] = field(default_factory=list)
    evidence_records: List[EvidenceRecord] = field(default_factory=list)

    @property
    def has_alerts(self) -> bool:
        """Return True if any alerts were generated in this frame."""
        return len(self.alerts) > 0

    @property
    def has_evidence(self) -> bool:
        """Return True if any evidence frames were captured in this frame."""
        return len(self.evidence_records) > 0

    @property
    def has_fence_breach(self) -> bool:
        """Return True if any fence breach events occurred in this frame."""
        return len(self.fence_breach_events) > 0

    @property
    def has_loitering(self) -> bool:
        """Return True if any loitering events occurred in this frame."""
        return len(self.loitering_events) > 0

    @property
    def object_count(self) -> int:
        """Return the count of tracked objects in this frame."""
        return len(self.tracked_objects)

    def summary(self) -> Dict[str, Any]:
        """Return a lightweight serializable summary of this frame result."""
        return {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "tracked_objects": len(self.tracked_objects),
            "movement_results": len(self.movement_results),
            "zone_results": len(self.zone_results),
            "fence_breach_events": len(self.fence_breach_events),
            "loitering_events": len(self.loitering_events),
            "alerts": len(self.alerts),
            "evidence_records": len(self.evidence_records),
        }


# ---------------------------------------------------------------------------
# AIPipeline Class
# ---------------------------------------------------------------------------

class AIPipeline:
    """Unified End-to-End AI Analytics Pipeline for IBVAP.

    Orchestrates the entire chain:
    VideoSource -> FramePreprocessor -> YOLODetector/ByteTrackTracker ->
    EventMemory -> MovementAnalyzer -> ZoneManager -> FenceBreachDetector ->
    LoiteringDetector -> AlertEngine -> EvidenceCapture.
    """

    def __init__(
        self,
        video_source: Optional[VideoSource] = None,
        preprocessor: Optional[FramePreprocessor] = None,
        detector: Optional[YOLODetector] = None,
        tracker: Optional[ByteTrackTracker] = None,
        event_memory: Optional[EventMemory] = None,
        movement_analyzer: Optional[MovementAnalyzer] = None,
        zone_manager: Optional[ZoneManager] = None,
        fence_breach_detector: Optional[FenceBreachDetector] = None,
        loitering_detector: Optional[LoiteringDetector] = None,
        alert_engine: Optional[AlertEngine] = None,
        evidence_capture: Optional[EvidenceCapture] = None,
        camera_id: str = "CAM_01",
        include_processed_frame_in_result: bool = True,
    ) -> None:
        """Initialize the end-to-end AI Pipeline with modular components.

        Any omitted components are initialized with standard default configurations.
        """
        self._camera_id = str(camera_id)
        self._include_processed_frame_in_result = bool(include_processed_frame_in_result)
        self._frame_count: int = 0
        self._video_source = video_source

        # M2: Preprocessor
        self._preprocessor = preprocessor if preprocessor is not None else FramePreprocessor()

        # M3 & M4: Detector and Tracker
        if tracker is not None:
            self._tracker = tracker
            self._detector = tracker.detector
        else:
            self._detector = detector if detector is not None else YOLODetector()
            self._tracker = ByteTrackTracker(detector=self._detector)

        # M5: Event Memory
        self._event_memory = event_memory if event_memory is not None else EventMemory()

        # M6: Movement Analyzer
        self._movement_analyzer = movement_analyzer if movement_analyzer is not None else MovementAnalyzer()

        # M7: Zone Manager
        self._zone_manager = zone_manager if zone_manager is not None else ZoneManager()

        # M8: Fence Breach Detector
        self._fence_breach_detector = fence_breach_detector if fence_breach_detector is not None else FenceBreachDetector()

        # M9: Loitering Detector
        self._loitering_detector = loitering_detector if loitering_detector is not None else LoiteringDetector()

        # M10: Alert Engine
        self._alert_engine = alert_engine if alert_engine is not None else AlertEngine(default_camera_id=self._camera_id)

        # M11: Evidence Capture
        self._evidence_capture = evidence_capture if evidence_capture is not None else EvidenceCapture()

        logger.info(
            "AIPipeline initialized for camera %s (include_frame=%s)",
            self._camera_id,
            self._include_processed_frame_in_result,
        )

    # -----------------------------------------------------------------------
    # Component Accessors
    # -----------------------------------------------------------------------

    @property
    def camera_id(self) -> str:
        """Return the associated camera identifier."""
        return self._camera_id

    @property
    def video_source(self) -> Optional[VideoSource]:
        """Return the current VideoSource instance, if configured."""
        return self._video_source

    @video_source.setter
    def video_source(self, source: Optional[VideoSource]) -> None:
        """Set or replace the VideoSource instance."""
        self._video_source = source

    @property
    def preprocessor(self) -> FramePreprocessor:
        """Return the M2 FramePreprocessor instance."""
        return self._preprocessor

    @property
    def detector(self) -> YOLODetector:
        """Return the M3 YOLODetector instance."""
        return self._detector

    @property
    def tracker(self) -> ByteTrackTracker:
        """Return the M4 ByteTrackTracker instance."""
        return self._tracker

    @property
    def event_memory(self) -> EventMemory:
        """Return the M5 EventMemory instance."""
        return self._event_memory

    @property
    def movement_analyzer(self) -> MovementAnalyzer:
        """Return the M6 MovementAnalyzer instance."""
        return self._movement_analyzer

    @property
    def zone_manager(self) -> ZoneManager:
        """Return the M7 ZoneManager instance."""
        return self._zone_manager

    @property
    def fence_breach_detector(self) -> FenceBreachDetector:
        """Return the M8 FenceBreachDetector instance."""
        return self._fence_breach_detector

    @property
    def loitering_detector(self) -> LoiteringDetector:
        """Return the M9 LoiteringDetector instance."""
        return self._loitering_detector

    @property
    def alert_engine(self) -> AlertEngine:
        """Return the M10 AlertEngine instance."""
        return self._alert_engine

    @property
    def evidence_capture(self) -> EvidenceCapture:
        """Return the M11 EvidenceCapture instance."""
        return self._evidence_capture

    @property
    def frames_processed(self) -> int:
        """Return the total number of frames processed since initialization or reset."""
        return self._frame_count

    # -----------------------------------------------------------------------
    # Core Processing Order
    # -----------------------------------------------------------------------

    def process_frame(
        self,
        frame: np.ndarray,
        frame_id: Optional[int] = None,
        timestamp: Optional[Union[float, datetime]] = None,
    ) -> PipelineResult:
        """Process a single video frame sequentially through all M2–M11 stages.

        Steps:
        1. Validate raw BGR frame.
        2. M2: FramePreprocessor enhancement.
        3. M3/M4: ByteTrackTracker detection and persistent tracking.
        4. M5: EventMemory state update for each tracked object.
        5. M6: MovementAnalyzer trajectory calculation.
        6. M7: ZoneManager spatial classification.
        7. M8: FenceBreachDetector temporal crossing detection.
        8. M9: LoiteringDetector dwell time evaluation.
        9. M10: AlertEngine routing of new M8/M9 events.
        10. M11: EvidenceCapture for any newly generated M10 alerts.
        11. Aggregate and return structured PipelineResult.

        Args:
            frame: Input BGR NumPy image (H, W, 3) with np.uint8 dtype.
            frame_id: Sequential frame index. Defaults to internal auto-increment.
            timestamp: Frame timestamp (float seconds or datetime). Defaults to current time.

        Returns:
            PipelineResult containing all analytics and generated records.

        Raises:
            PipelineValidationError: If input frame is invalid.
        """
        # 1. Validation
        if frame is None:
            raise PipelineValidationError("Input frame cannot be None.")

        try:
            self._preprocessor.validate_frame(frame)
        except InvalidFrameError as err:
            raise PipelineValidationError(f"Invalid input frame: {err}") from err

        # Determine frame index and timestamps
        self._frame_count += 1
        curr_frame_id = frame_id if frame_id is not None else self._frame_count

        if timestamp is None:
            ts_float = time.time()
            dt = datetime.fromtimestamp(ts_float, tz=timezone.utc).replace(tzinfo=None)
        elif isinstance(timestamp, datetime):
            dt = timestamp
            ts_float = timestamp.timestamp()
        else:
            ts_float = float(timestamp)
            dt = datetime.fromtimestamp(ts_float, tz=timezone.utc).replace(tzinfo=None)

        # 2. M2 Preprocessing
        enhanced_frame = self._preprocessor.process(frame)

        # 3. M3/M4 Tracking (runs YOLO internally on enhanced_frame)
        tracked_objects: List[TrackedObject] = self._tracker.update(enhanced_frame)

        # 4. M5 Event Memory
        track_memories: List[TrackMemory] = []
        for obj in tracked_objects:
            record = self._event_memory.update(obj, frame_time=dt)
            track_memories.append(record)

        # 5. M6 Movement Analysis
        movement_results: List[MovementResult] = []
        for obj in tracked_objects:
            res = self._movement_analyzer.analyze(obj.track_id, self._event_memory)
            movement_results.append(res)

        # 6. M7 Zone Classification
        zone_results: List[ZoneResult] = []
        zone_by_track: Dict[int, ZoneResult] = {}
        for obj in tracked_objects:
            zr = self._zone_manager.classify_object(obj)
            zone_results.append(zr)
            zone_by_track[obj.track_id] = zr

        # 7. M8 Fence Breach Detection
        fence_breach_events: List[FenceBreachEvent] = self._fence_breach_detector.update_batch(
            zone_results=zone_results,
            frame_id=curr_frame_id,
            timestamp=ts_float,
        )

        # 8. M9 Loitering Detection
        loitering_events: List[LoiteringEvent] = []
        for tm in track_memories:
            matched_zr = zone_by_track.get(tm.track_id)
            lr: LoiteringResult = self._loitering_detector.update_track(
                track_memory=tm,
                frame_id=curr_frame_id,
                timestamp=dt,
                zone_result=matched_zr,
            )
            if lr.new_event is not None:
                loitering_events.append(lr.new_event)

        # 9. M10 Alert Engine (Only new genuine events converted to alerts)
        new_alerts: List[Alert] = []
        for breach_event in fence_breach_events:
            alert = self._alert_engine.process_fence_breach(
                event=breach_event,
                camera_id=self._camera_id,
            )
            if alert is not None:
                new_alerts.append(alert)

        for loiter_event in loitering_events:
            alert = self._alert_engine.process_loitering(
                event=loiter_event,
                camera_id=self._camera_id,
            )
            if alert is not None:
                new_alerts.append(alert)

        # 10. M11 Evidence Capture (Only for newly generated alerts)
        evidence_records: List[EvidenceRecord] = []
        for alert in new_alerts:
            # Capture using the enhanced_frame
            rec = self._evidence_capture.capture(alert=alert, frame=enhanced_frame)
            evidence_records.append(rec)

        # 11. Pipeline Result
        result = PipelineResult(
            frame_id=curr_frame_id,
            timestamp=ts_float,
            processed_frame=enhanced_frame if self._include_processed_frame_in_result else None,
            tracked_objects=tracked_objects,
            track_memories=track_memories,
            movement_results=movement_results,
            zone_results=zone_results,
            fence_breach_events=fence_breach_events,
            loitering_events=loitering_events,
            alerts=new_alerts,
            evidence_records=evidence_records,
        )

        return result

    def process_source(
        self,
        source: Optional[VideoSource] = None,
        max_frames: Optional[int] = None,
    ) -> Generator[PipelineResult, None, None]:
        """Stream and process frames from an M1 VideoSource instance.

        Args:
            source: VideoSource instance. Defaults to self.video_source.
            max_frames: Optional maximum number of frames to process.

        Yields:
            PipelineResult for each successfully read and processed frame.

        Raises:
            PipelineError: If no VideoSource is configured or available.
        """
        src = source or self._video_source
        if src is None:
            raise PipelineError("No VideoSource configured for process_source().")

        close_after = False
        if not src.is_opened:
            src.open()
            close_after = True

        try:
            frames_yielded = 0
            while True:
                if max_frames is not None and frames_yielded >= max_frames:
                    break

                ret, frame = src.read()
                if not ret or frame is None:
                    break

                frame_id = src.current_frame_index
                result = self.process_frame(frame, frame_id=frame_id)
                frames_yielded += 1
                yield result
        finally:
            if close_after:
                src.release()

    # -----------------------------------------------------------------------
    # State Management
    # -----------------------------------------------------------------------

    def reset(self) -> None:
        """Reset the internal state of all stateful modules in the pipeline.

        Preserves YOLO model weights and configuration while purging:
        - ByteTrack tracking state (via tracker.reset())
        - EventMemory track history (via event_memory.clear())
        - FenceBreachDetector temporal crossing state (via fence_breach_detector.reset())
        - LoiteringDetector dwell times and anchors (via loitering_detector.reset())
        - AlertEngine active alerts and deduplication memory (via alert_engine.reset())
        - EvidenceCapture in-memory records (via evidence_capture.clear())
        - Pipeline processed frame counter
        """
        self._tracker.reset()
        self._event_memory.clear()
        self._fence_breach_detector.reset()
        self._loitering_detector.reset()
        self._alert_engine.reset()
        self._evidence_capture.clear()
        self._frame_count = 0
        logger.info("AIPipeline state safely reset.")
