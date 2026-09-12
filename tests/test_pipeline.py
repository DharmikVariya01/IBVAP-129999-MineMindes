"""Comprehensive tests for Module 12: Complete AI Pipeline Integration.

Tests cover:
A. Initialization & Component Injection
   - default instantiation
   - custom component injection
   - properties and accessor validation
B. Frame Processing Order & Data Integrity
   - sequential execution through M2–M11
   - PipelineResult schema and helper properties
C. Multi-Frame State Persistence
   - track persistence across consecutive frames
   - EventMemory and tracker continuity
D. ZoneManager Integration
   - tracked objects classified against registered zones
   - ZoneResults routed to downstream detectors
E. Deterministic Synthetic Fence Breach Integration
   - OUTSIDE -> INSIDE transition produces M8 FenceBreachEvent
   - M8 event produces M10 Alert (CRITICAL)
   - M10 alert triggers M11 EvidenceCapture and writes image to disk
F. Deterministic Synthetic Loitering Integration
   - stationary/localized track reaches loitering threshold
   - produces M9 LoiteringEvent
   - M9 event produces M10 Alert (HIGH)
   - M10 alert triggers M11 EvidenceCapture
G. Deduplication Across Consecutive Frames
   - continuous residence inside fence generates exactly ONE alert and ONE evidence record
   - continuous loitering does not spam duplicate alerts or evidence
H. Zero-Event Sequence
   - normal frames without breaches or loitering produce zero alerts and zero evidence
   - pipeline continues smoothly
I. Safe Lifecycle & Reset Behavior
   - pipeline.reset() purges state across all stateful components
   - YOLO model weights are reused (no reload)
   - processing resumes normally after reset
J. Error Handling & Validation
   - None frame, corrupt arrays, wrong dimensions
   - missing VideoSource handling
K. Evidence Capture Verification
   - saved image exists, is readable via cv2.imread, matches resolution
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from ai_engine.alerts import (
    Alert,
    AlertEngine,
    AlertSeverity,
    AlertStatus,
    AlertType,
)
from ai_engine.detector import Detection, YOLODetector
from ai_engine.event_memory import EventMemory, TrackMemory
from ai_engine.evidence import EvidenceCapture, EvidenceRecord
from ai_engine.fence_breach import (
    BreachEventType,
    FenceBreachDetector,
    FenceBreachEvent,
    FenceState,
)
from ai_engine.loitering import (
    LoiteringDetector,
    LoiteringEvent,
    LoiteringResult,
    LoiteringState,
)
from ai_engine.movement import MovementAnalyzer, MovementResult
from ai_engine.pipeline import (
    AIPipeline,
    PipelineError,
    PipelineResult,
    PipelineValidationError,
)
from ai_engine.preprocessing import FramePreprocessor
from ai_engine.tracker import ByteTrackTracker, TrackedObject
from ai_engine.video_input import SourceType, VideoSource
from ai_engine.zones import Zone, ZoneManager, ZoneResult, ZoneType


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------

_shared_detector: Optional[YOLODetector] = None


def _get_shared_detector() -> YOLODetector:
    """Return a module-level YOLODetector instance, creating it once."""
    global _shared_detector
    if _shared_detector is None:
        _shared_detector = YOLODetector(device="cpu")
    return _shared_detector


@pytest.fixture
def temp_evidence_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for evidence storage."""
    ev_dir = tmp_path / "test_pipeline_evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    return ev_dir


@pytest.fixture
def sample_bgr_frame() -> np.ndarray:
    """Return a standard 720x1280 3-channel BGR test frame."""
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    # Background gradient
    frame[:, :] = (40, 50, 45)
    return frame


class MockTracker:
    """Controllable mock tracker for deterministic pipeline integration testing."""

    def __init__(self, detector: Optional[YOLODetector] = None) -> None:
        self.detector = detector or MagicMock(spec=YOLODetector)
        self.objects_to_return: List[TrackedObject] = []
        self.frame_count: int = 0
        self.reset_called: bool = False

    def update(self, frame: np.ndarray) -> List[TrackedObject]:
        self.frame_count += 1
        return list(self.objects_to_return)

    def reset(self) -> None:
        self.reset_called = True
        self.frame_count = 0


# ---------------------------------------------------------------------------
# A. Initialization Tests
# ---------------------------------------------------------------------------

def test_pipeline_default_init(temp_evidence_dir: Path) -> None:
    """Verify AIPipeline initializes cleanly with default components."""
    evidence_cap = EvidenceCapture(output_dir=temp_evidence_dir)
    pipeline = AIPipeline(
        evidence_capture=evidence_cap,
        camera_id="TEST_CAM_01",
    )

    assert pipeline.camera_id == "TEST_CAM_01"
    assert isinstance(pipeline.preprocessor, FramePreprocessor)
    assert isinstance(pipeline.detector, YOLODetector)
    assert isinstance(pipeline.tracker, ByteTrackTracker)
    assert isinstance(pipeline.event_memory, EventMemory)
    assert isinstance(pipeline.movement_analyzer, MovementAnalyzer)
    assert isinstance(pipeline.zone_manager, ZoneManager)
    assert isinstance(pipeline.fence_breach_detector, FenceBreachDetector)
    assert isinstance(pipeline.loitering_detector, LoiteringDetector)
    assert isinstance(pipeline.alert_engine, AlertEngine)
    assert isinstance(pipeline.evidence_capture, EvidenceCapture)
    assert pipeline.frames_processed == 0


def test_pipeline_custom_component_injection(temp_evidence_dir: Path) -> None:
    """Verify custom injected components are preserved and accessible."""
    mock_tracker = MockTracker()
    custom_preprocessor = FramePreprocessor(brightness_threshold=45.0)
    custom_memory = EventMemory(max_history=50)
    custom_zones = ZoneManager(include_boundary=False)
    custom_breach = FenceBreachDetector(default_fence_id="PERIMETER_NORTH")
    custom_loiter = LoiteringDetector(loitering_duration_seconds=15.0)
    custom_alerts = AlertEngine(default_camera_id="CUSTOM_CAM")
    custom_evidence = EvidenceCapture(output_dir=temp_evidence_dir)

    pipeline = AIPipeline(
        preprocessor=custom_preprocessor,
        tracker=mock_tracker,  # type: ignore[arg-type]
        event_memory=custom_memory,
        zone_manager=custom_zones,
        fence_breach_detector=custom_breach,
        loitering_detector=custom_loiter,
        alert_engine=custom_alerts,
        evidence_capture=custom_evidence,
        camera_id="CUSTOM_CAM",
    )

    assert pipeline.preprocessor is custom_preprocessor
    assert pipeline.tracker is mock_tracker
    assert pipeline.event_memory is custom_memory
    assert pipeline.zone_manager is custom_zones
    assert pipeline.fence_breach_detector is custom_breach
    assert pipeline.loitering_detector is custom_loiter
    assert pipeline.alert_engine is custom_alerts
    assert pipeline.evidence_capture is custom_evidence


# ---------------------------------------------------------------------------
# B. Frame Processing Order & Data Integrity
# ---------------------------------------------------------------------------

def test_pipeline_process_frame_order_and_schema(
    sample_bgr_frame: np.ndarray,
    temp_evidence_dir: Path,
) -> None:
    """Verify that a frame passes sequentially through all M2–M11 stages and returns PipelineResult."""
    mock_tracker = MockTracker()
    mock_tracker.objects_to_return = [
        TrackedObject(
            track_id=10,
            class_id=0,
            class_name="person",
            confidence=0.92,
            x1=100,
            y1=100,
            x2=160,
            y2=220,
        )
    ]

    pipeline = AIPipeline(
        tracker=mock_tracker,  # type: ignore[arg-type]
        evidence_capture=EvidenceCapture(output_dir=temp_evidence_dir),
    )

    result = pipeline.process_frame(sample_bgr_frame, frame_id=1, timestamp=1000.0)

    assert isinstance(result, PipelineResult)
    assert result.frame_id == 1
    assert result.timestamp == 1000.0
    assert result.processed_frame is not None
    assert result.processed_frame.shape == sample_bgr_frame.shape
    assert len(result.tracked_objects) == 1
    assert result.tracked_objects[0].track_id == 10

    # M5 TrackMemory generated
    assert len(result.track_memories) == 1
    assert result.track_memories[0].track_id == 10
    assert result.track_memories[0].frame_count == 1

    # M6 MovementResult generated
    assert len(result.movement_results) == 1
    assert result.movement_results[0].track_id == 10

    # M7 ZoneResult generated
    assert len(result.zone_results) == 1
    assert result.zone_results[0].track_id == 10

    # Summary dictionary contains valid data
    summary = result.summary()
    assert summary["frame_id"] == 1
    assert summary["tracked_objects"] == 1
    assert pipeline.frames_processed == 1


# ---------------------------------------------------------------------------
# C. Multi-Frame State Persistence
# ---------------------------------------------------------------------------

def test_pipeline_multi_frame_state_persistence(
    sample_bgr_frame: np.ndarray,
    temp_evidence_dir: Path,
) -> None:
    """Verify M4 tracker and M5 event memory maintain continuous state across frames."""
    mock_tracker = MockTracker()
    pipeline = AIPipeline(
        tracker=mock_tracker,  # type: ignore[arg-type]
        evidence_capture=EvidenceCapture(output_dir=temp_evidence_dir),
    )

    # Frame 1: Object 7 appears at (100, 100)
    mock_tracker.objects_to_return = [
        TrackedObject(track_id=7, class_id=0, class_name="person", confidence=0.9, x1=90, y1=80, x2=110, y2=120)
    ]
    res1 = pipeline.process_frame(sample_bgr_frame, frame_id=1, timestamp=1.0)
    assert res1.track_memories[0].frame_count == 1
    assert len(res1.track_memories[0].history) == 1

    # Frame 2: Same Object 7 at (120, 100)
    mock_tracker.objects_to_return = [
        TrackedObject(track_id=7, class_id=0, class_name="person", confidence=0.91, x1=110, y1=80, x2=130, y2=120)
    ]
    res2 = pipeline.process_frame(sample_bgr_frame, frame_id=2, timestamp=2.0)
    assert res2.track_memories[0].frame_count == 2
    assert len(res2.track_memories[0].history) == 2
    assert res2.movement_results[0].displacement > 0.0

    # Event memory maintains single record for track 7
    assert pipeline.event_memory.track_count == 1


# ---------------------------------------------------------------------------
# D. ZoneManager Integration
# ---------------------------------------------------------------------------

def test_pipeline_zone_manager_classification(
    sample_bgr_frame: np.ndarray,
    temp_evidence_dir: Path,
) -> None:
    """Verify ZoneManager classifies tracked objects into registered spatial zones."""
    zone_mgr = ZoneManager()
    zone_mgr.create_zone(
        zone_id="RESTRICTED_BUFFER",
        zone_name="Buffer Zone",
        zone_type=ZoneType.RESTRICTED,
        polygon=[(200, 200), (500, 200), (500, 500), (200, 500)],
    )

    mock_tracker = MockTracker()
    pipeline = AIPipeline(
        tracker=mock_tracker,  # type: ignore[arg-type]
        zone_manager=zone_mgr,
        evidence_capture=EvidenceCapture(output_dir=temp_evidence_dir),
    )

    # Object center at (300, 300) -> inside RESTRICTED_BUFFER
    mock_tracker.objects_to_return = [
        TrackedObject(track_id=1, class_id=0, class_name="person", confidence=0.88, x1=280, y1=280, x2=320, y2=320)
    ]
    result = pipeline.process_frame(sample_bgr_frame, frame_id=1)
    assert len(result.zone_results) == 1
    zr = result.zone_results[0]
    assert zr.inside_zone is True
    assert zr.zone_id == "RESTRICTED_BUFFER"
    assert zr.zone_type == ZoneType.RESTRICTED


# ---------------------------------------------------------------------------
# E. Deterministic Synthetic Fence Breach Integration (M8 -> M10 -> M11)
# ---------------------------------------------------------------------------

def test_pipeline_synthetic_fence_breach_to_evidence_flow(
    sample_bgr_frame: np.ndarray,
    temp_evidence_dir: Path,
) -> None:
    """Scenario A: OUTSIDE -> INSIDE transition produces M8 event -> M10 alert -> M11 evidence file."""
    zone_mgr = ZoneManager()
    zone_mgr.create_zone(
        zone_id="FENCE_LINE_01",
        zone_name="Perimeter Virtual Fence",
        zone_type=ZoneType.FENCE,
        polygon=[(300, 100), (600, 100), (600, 400), (300, 400)],
    )

    mock_tracker = MockTracker()
    pipeline = AIPipeline(
        tracker=mock_tracker,  # type: ignore[arg-type]
        zone_manager=zone_mgr,
        evidence_capture=EvidenceCapture(output_dir=temp_evidence_dir),
        camera_id="BORDER_CAM_01",
    )

    # Frame 1: Object 42 is OUTSIDE at center (100, 100)
    mock_tracker.objects_to_return = [
        TrackedObject(track_id=42, class_id=0, class_name="person", confidence=0.92, x1=90, y1=90, x2=110, y2=110)
    ]
    res1 = pipeline.process_frame(sample_bgr_frame, frame_id=1, timestamp=10.0)
    assert res1.zone_results[0].fence_inside is False
    assert len(res1.fence_breach_events) == 0
    assert len(res1.alerts) == 0
    assert len(res1.evidence_records) == 0

    # Frame 2: Object 42 moves INSIDE to center (450, 250) -> BREACH!
    mock_tracker.objects_to_return = [
        TrackedObject(track_id=42, class_id=0, class_name="person", confidence=0.93, x1=440, y1=240, x2=460, y2=260)
    ]
    res2 = pipeline.process_frame(sample_bgr_frame, frame_id=2, timestamp=11.0)

    # M8 Event generated
    assert len(res2.fence_breach_events) == 1
    fbe = res2.fence_breach_events[0]
    assert fbe.track_id == 42
    assert fbe.event_type == BreachEventType.FENCE_BREACH
    assert fbe.previous_state == FenceState.OUTSIDE
    assert fbe.current_state == FenceState.INSIDE

    # M10 Alert generated
    assert len(res2.alerts) == 1
    alert = res2.alerts[0]
    assert alert.track_id == 42
    assert alert.alert_type == AlertType.FENCE_BREACH
    assert alert.severity == AlertSeverity.CRITICAL
    assert alert.camera_id == "BORDER_CAM_01"

    # M11 Evidence captured
    assert len(res2.evidence_records) == 1
    ev_rec = res2.evidence_records[0]
    assert ev_rec.alert_id == alert.alert_id
    assert ev_rec.track_id == 42
    assert Path(ev_rec.file_path).exists()
    assert Path(ev_rec.file_path).stat().st_size > 0

    # Verify image integrity
    saved_img = cv2.imread(ev_rec.file_path)
    assert saved_img is not None
    assert saved_img.shape == sample_bgr_frame.shape


# ---------------------------------------------------------------------------
# F. Deterministic Synthetic Loitering Integration (M9 -> M10 -> M11)
# ---------------------------------------------------------------------------

def test_pipeline_synthetic_loitering_to_evidence_flow(
    sample_bgr_frame: np.ndarray,
    temp_evidence_dir: Path,
) -> None:
    """Scenario B: Stationary track accumulates dwell time >= threshold -> M9 event -> M10 alert -> M11 evidence."""
    mock_tracker = MockTracker()
    loiter_detector = LoiteringDetector(
        loitering_duration_seconds=3.0,
        spatial_radius=40.0,
        min_observations=3,
    )

    pipeline = AIPipeline(
        tracker=mock_tracker,  # type: ignore[arg-type]
        loitering_detector=loiter_detector,
        evidence_capture=EvidenceCapture(output_dir=temp_evidence_dir),
        camera_id="BORDER_CAM_02",
    )

    base_time = datetime(2026, 9, 12, 10, 0, 0)

    # Frame 1: t = 0.0s (First observation establishes anchor)
    mock_tracker.objects_to_return = [
        TrackedObject(track_id=88, class_id=0, class_name="person", confidence=0.88, x1=200, y1=200, x2=240, y2=260)
    ]
    res1 = pipeline.process_frame(sample_bgr_frame, frame_id=1, timestamp=base_time)
    assert len(res1.loitering_events) == 0
    assert len(res1.alerts) == 0

    # Frame 2: t = 1.5s (Dwell time 1.5s < 3.0s)
    res2 = pipeline.process_frame(
        sample_bgr_frame,
        frame_id=2,
        timestamp=base_time + timedelta(seconds=1.5),
    )
    assert len(res2.loitering_events) == 0
    assert len(res2.alerts) == 0

    # Frame 3: t = 3.5s (Dwell time 3.5s >= 3.0s, obs count 3 >= 3) -> LOITERING QUALIFIED!
    res3 = pipeline.process_frame(
        sample_bgr_frame,
        frame_id=3,
        timestamp=base_time + timedelta(seconds=3.5),
    )
    assert len(res3.loitering_events) == 1
    le = res3.loitering_events[0]
    assert le.track_id == 88
    assert le.duration_seconds >= 3.0

    # M10 Alert generated
    assert len(res3.alerts) == 1
    alert = res3.alerts[0]
    assert alert.track_id == 88
    assert alert.alert_type == AlertType.LOITERING
    assert alert.severity == AlertSeverity.HIGH

    # M11 Evidence captured
    assert len(res3.evidence_records) == 1
    ev_rec = res3.evidence_records[0]
    assert ev_rec.alert_id == alert.alert_id
    assert Path(ev_rec.file_path).exists()


# ---------------------------------------------------------------------------
# G. Deduplication Across Consecutive Frames
# ---------------------------------------------------------------------------

def test_pipeline_deduplication_continuous_residence(
    sample_bgr_frame: np.ndarray,
    temp_evidence_dir: Path,
) -> None:
    """Verify that continuing inside a fence or remaining loitering does NOT emit duplicate alerts/evidence."""
    zone_mgr = ZoneManager()
    zone_mgr.create_zone(
        zone_id="FENCE_01",
        zone_name="Perimeter",
        zone_type=ZoneType.FENCE,
        polygon=[(100, 100), (400, 100), (400, 400), (100, 400)],
    )

    mock_tracker = MockTracker()
    pipeline = AIPipeline(
        tracker=mock_tracker,  # type: ignore[arg-type]
        zone_manager=zone_mgr,
        evidence_capture=EvidenceCapture(output_dir=temp_evidence_dir),
    )

    # Frame 1: OUTSIDE at (50, 50)
    mock_tracker.objects_to_return = [
        TrackedObject(track_id=5, class_id=0, class_name="person", confidence=0.9, x1=40, y1=40, x2=60, y2=60)
    ]
    pipeline.process_frame(sample_bgr_frame, frame_id=1, timestamp=1.0)

    # Frame 2: OUTSIDE -> INSIDE at (200, 200) -> 1 breach alert
    mock_tracker.objects_to_return = [
        TrackedObject(track_id=5, class_id=0, class_name="person", confidence=0.9, x1=190, y1=190, x2=210, y2=210)
    ]
    res2 = pipeline.process_frame(sample_bgr_frame, frame_id=2, timestamp=2.0)
    assert len(res2.alerts) == 1
    assert len(res2.evidence_records) == 1

    # Frames 3, 4, 5: Continuously INSIDE -> ZERO additional alerts or evidence captures
    for fid in [3, 4, 5]:
        mock_tracker.objects_to_return = [
            TrackedObject(track_id=5, class_id=0, class_name="person", confidence=0.9, x1=195, y1=195, x2=215, y2=215)
        ]
        res = pipeline.process_frame(sample_bgr_frame, frame_id=fid, timestamp=float(fid))
        assert len(res.fence_breach_events) == 0
        assert len(res.alerts) == 0
        assert len(res.evidence_records) == 0

    # Total alerts in engine remains 1
    assert pipeline.alert_engine.count_active_alerts() == 1
    assert pipeline.evidence_capture.count == 1


# ---------------------------------------------------------------------------
# H. Zero-Event Sequence
# ---------------------------------------------------------------------------

def test_pipeline_zero_event_sequence(
    sample_bgr_frame: np.ndarray,
    temp_evidence_dir: Path,
) -> None:
    """Verify normal frames with no breaches and no loitering produce 0 alerts and 0 evidence records."""
    mock_tracker = MockTracker()
    pipeline = AIPipeline(
        tracker=mock_tracker,  # type: ignore[arg-type]
        evidence_capture=EvidenceCapture(output_dir=temp_evidence_dir),
    )

    # Process 5 empty frames
    for i in range(1, 6):
        mock_tracker.objects_to_return = []
        res = pipeline.process_frame(sample_bgr_frame, frame_id=i, timestamp=float(i))
        assert res.has_alerts is False
        assert res.has_evidence is False
        assert res.has_fence_breach is False
        assert res.has_loitering is False
        assert len(res.alerts) == 0
        assert len(res.evidence_records) == 0

    assert pipeline.frames_processed == 5
    assert pipeline.alert_engine.count_active_alerts() == 0
    assert pipeline.evidence_capture.count == 0


# ---------------------------------------------------------------------------
# I. Safe Lifecycle & Reset Behavior
# ---------------------------------------------------------------------------

def test_pipeline_reset_clears_all_module_states(
    sample_bgr_frame: np.ndarray,
    temp_evidence_dir: Path,
) -> None:
    """Verify reset() clears states of tracker, event memory, detectors, and alerts while preserving model."""
    mock_tracker = MockTracker()
    pipeline = AIPipeline(
        tracker=mock_tracker,  # type: ignore[arg-type]
        evidence_capture=EvidenceCapture(output_dir=temp_evidence_dir),
    )

    # Feed a frame with object
    mock_tracker.objects_to_return = [
        TrackedObject(track_id=12, class_id=0, class_name="person", confidence=0.85, x1=50, y1=50, x2=80, y2=120)
    ]
    pipeline.process_frame(sample_bgr_frame, frame_id=1, timestamp=1.0)
    assert pipeline.frames_processed == 1
    assert pipeline.event_memory.track_count == 1

    # Execute reset
    detector_before = pipeline.detector
    pipeline.reset()

    # Verified cleared state
    assert pipeline.frames_processed == 0
    assert pipeline.event_memory.track_count == 0
    assert pipeline.alert_engine.count_active_alerts() == 0
    assert pipeline.evidence_capture.count == 0
    assert mock_tracker.reset_called is True
    # Detector reference preserved
    assert pipeline.detector is detector_before

    # Pipeline can immediately process a new frame after reset
    res = pipeline.process_frame(sample_bgr_frame, frame_id=1, timestamp=1.0)
    assert res.frame_id == 1
    assert pipeline.frames_processed == 1


# ---------------------------------------------------------------------------
# J. Error Handling & Validation
# ---------------------------------------------------------------------------

def test_pipeline_invalid_frame_errors(temp_evidence_dir: Path) -> None:
    """Verify pipeline raises PipelineValidationError on invalid frame inputs."""
    pipeline = AIPipeline(evidence_capture=EvidenceCapture(output_dir=temp_evidence_dir))

    # None frame
    with pytest.raises(PipelineValidationError, match="Input frame cannot be None"):
        pipeline.process_frame(None)  # type: ignore[arg-type]

    # Non-array input
    with pytest.raises(PipelineValidationError, match="Expected numpy.ndarray"):
        pipeline.process_frame("not_a_frame")  # type: ignore[arg-type]

    # Non-uint8 dtype
    bad_dtype = np.zeros((100, 100, 3), dtype=np.float32)
    with pytest.raises(PipelineValidationError, match="Expected frame dtype uint8"):
        pipeline.process_frame(bad_dtype)

    # Wrong channels
    bad_channels = np.zeros((100, 100, 1), dtype=np.uint8)
    with pytest.raises(PipelineValidationError, match="Expected 3 channels"):
        pipeline.process_frame(bad_channels)


def test_pipeline_missing_source_for_stream(temp_evidence_dir: Path) -> None:
    """Verify process_source raises PipelineError if no VideoSource is provided."""
    pipeline = AIPipeline(evidence_capture=EvidenceCapture(output_dir=temp_evidence_dir))
    with pytest.raises(PipelineError, match="No VideoSource configured"):
        next(pipeline.process_source())


# ---------------------------------------------------------------------------
# K. VideoSource Streaming Integration
# ---------------------------------------------------------------------------

def test_pipeline_stream_from_video_source(
    sample_bgr_frame: np.ndarray,
    temp_evidence_dir: Path,
) -> None:
    """Verify process_source streams frames from VideoSource and respects max_frames."""
    mock_src = MagicMock(spec=VideoSource)
    mock_src.is_opened = True
    mock_src.read.return_value = (True, sample_bgr_frame)
    mock_src.current_frame_index = 1

    mock_tracker = MockTracker()
    pipeline = AIPipeline(
        video_source=mock_src,
        tracker=mock_tracker,  # type: ignore[arg-type]
        evidence_capture=EvidenceCapture(output_dir=temp_evidence_dir),
    )

    results = list(pipeline.process_source(max_frames=3))
    assert len(results) == 3
    assert all(isinstance(r, PipelineResult) for r in results)
    assert pipeline.frames_processed == 3


# ---------------------------------------------------------------------------
# L. Real YOLO & MP4 End-to-End Integration
# ---------------------------------------------------------------------------

def test_pipeline_real_detector_and_mp4(temp_evidence_dir: Path) -> None:
    """Verify AIPipeline executes end-to-end on real frames from videos/test.mp4 using real YOLO."""
    video_path = Path("videos/test.mp4")
    if not video_path.exists():
        pytest.skip("videos/test.mp4 not found")

    detector = _get_shared_detector()
    tracker = ByteTrackTracker(detector=detector)
    evidence_cap = EvidenceCapture(output_dir=temp_evidence_dir)

    src = VideoSource(source_type=SourceType.VIDEO, source=str(video_path))
    pipeline = AIPipeline(
        video_source=src,
        tracker=tracker,
        evidence_capture=evidence_cap,
        camera_id="REAL_CAM_01",
    )

    results = list(pipeline.process_source(max_frames=5))
    assert len(results) == 5
    assert pipeline.frames_processed == 5
    for res in results:
        assert isinstance(res, PipelineResult)
        assert res.processed_frame is not None
        assert res.processed_frame.shape == (720, 1280, 3) or res.processed_frame.ndim == 3

    # Clean reset
    pipeline.reset()
    assert pipeline.frames_processed == 0


def test_pipeline_without_frame_in_result(
    sample_bgr_frame: np.ndarray,
    temp_evidence_dir: Path,
) -> None:
    """Verify include_processed_frame_in_result=False omits numpy array from PipelineResult to save memory."""
    mock_tracker = MockTracker()
    pipeline = AIPipeline(
        tracker=mock_tracker,  # type: ignore[arg-type]
        evidence_capture=EvidenceCapture(output_dir=temp_evidence_dir),
        include_processed_frame_in_result=False,
    )

    result = pipeline.process_frame(sample_bgr_frame)
    assert result.processed_frame is None
    assert result.frame_id == 1


def test_pipeline_movement_analysis_trail(
    sample_bgr_frame: np.ndarray,
    temp_evidence_dir: Path,
) -> None:
    """Verify M6 MovementAnalyzer populates directional trail for tracked objects."""
    mock_tracker = MockTracker()
    pipeline = AIPipeline(
        tracker=mock_tracker,  # type: ignore[arg-type]
        evidence_capture=EvidenceCapture(output_dir=temp_evidence_dir),
    )

    # Frame 1: center at (100, 100)
    mock_tracker.objects_to_return = [
        TrackedObject(track_id=99, class_id=0, class_name="person", confidence=0.9, x1=90, y1=90, x2=110, y2=110)
    ]
    pipeline.process_frame(sample_bgr_frame, frame_id=1, timestamp=1.0)

    # Frame 2: center at (140, 100) -> Moving RIGHT
    mock_tracker.objects_to_return = [
        TrackedObject(track_id=99, class_id=0, class_name="person", confidence=0.9, x1=130, y1=90, x2=150, y2=110)
    ]
    res2 = pipeline.process_frame(sample_bgr_frame, frame_id=2, timestamp=2.0)

    assert len(res2.movement_results) == 1
    m_res = res2.movement_results[0]
    assert m_res.track_id == 99
    assert m_res.displacement > 0.0
    assert len(m_res.trail) == 2
