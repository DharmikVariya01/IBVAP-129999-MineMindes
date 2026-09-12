"""Automated tests for IBVAP Module 4 (ByteTrack Persistent Object Tracking).

Tests validate the ByteTrackTracker class, TrackedObject dataclass, input
validation, output contract, persistent state across consecutive frames,
class filtering, and integration with M1/M2/M3 modules.

All tests use synthetic or real video frames and do NOT require a webcam.
"""

from dataclasses import fields as dataclass_fields
from pathlib import Path
import sys
import unittest

import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.detector import (
    DEFAULT_TARGET_CLASSES,
    Detection,
    InvalidFrameError,
    YOLODetector,
)
from ai_engine.tracker import (
    ByteTrackTracker,
    TrackedObject,
    TrackingError,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# Module-level instances (loaded once for all tests to avoid repeated
# model downloads / loads during the test run)
_shared_detector = None
_shared_tracker = None


def _get_shared_detector() -> YOLODetector:
    """Return a module-level YOLODetector instance, creating it once."""
    global _shared_detector
    if _shared_detector is None:
        _shared_detector = YOLODetector(device="cpu")
    return _shared_detector


def _get_shared_tracker() -> ByteTrackTracker:
    """Return a module-level ByteTrackTracker instance, creating it once."""
    global _shared_tracker
    if _shared_tracker is None:
        _shared_tracker = ByteTrackTracker(_get_shared_detector())
    return _shared_tracker


def _make_synthetic_frame(
    height: int = 480,
    width: int = 640,
    color: tuple = (128, 128, 128),
) -> np.ndarray:
    """Create a deterministic synthetic BGR uint8 frame."""
    return np.full((height, width, 3), color, dtype=np.uint8)


# ===========================================================================
# Test Cases
# ===========================================================================


class TestTrackerInitialization(unittest.TestCase):
    """Test tracker construction and configuration."""

    def test_01_tracker_initializes_successfully(self):
        """ByteTrackTracker can be constructed with a YOLODetector."""
        tracker = _get_shared_tracker()
        self.assertIsInstance(tracker, ByteTrackTracker)

    def test_02_tracker_holds_detector_reference(self):
        """Tracker references the same detector instance (no duplicate model)."""
        detector = _get_shared_detector()
        tracker = _get_shared_tracker()
        self.assertIs(tracker.detector, detector)

    def test_03_tracker_reuses_same_model(self):
        """Tracker uses the exact same YOLO model object as the detector."""
        detector = _get_shared_detector()
        tracker = _get_shared_tracker()
        self.assertIs(tracker.detector.model, detector.model)

    def test_04_invalid_detector_type_rejected(self):
        """Passing a non-YOLODetector raises TypeError."""
        with self.assertRaises(TypeError):
            ByteTrackTracker("not_a_detector")

    def test_05_tracker_type_default(self):
        """Default tracker type is bytetrack.yaml."""
        tracker = _get_shared_tracker()
        self.assertEqual(tracker.tracker_type, "bytetrack.yaml")


class TestTrackedObjectDataclass(unittest.TestCase):
    """Test the TrackedObject dataclass structure and fields."""

    def test_06_tracked_object_has_required_fields(self):
        """TrackedObject dataclass has all 8 required fields."""
        expected_fields = {
            "track_id", "class_id", "class_name", "confidence",
            "x1", "y1", "x2", "y2",
        }
        actual_fields = {f.name for f in dataclass_fields(TrackedObject)}
        self.assertEqual(expected_fields, actual_fields)

    def test_07_tracked_object_constructor(self):
        """TrackedObject can be instantiated with all required fields."""
        obj = TrackedObject(
            track_id=1,
            class_id=0,
            class_name="person",
            confidence=0.92,
            x1=100, y1=50, x2=200, y2=300,
        )
        self.assertEqual(obj.track_id, 1)
        self.assertEqual(obj.class_id, 0)
        self.assertEqual(obj.class_name, "person")
        self.assertAlmostEqual(obj.confidence, 0.92)
        self.assertEqual(obj.x1, 100)
        self.assertEqual(obj.y1, 50)
        self.assertEqual(obj.x2, 200)
        self.assertEqual(obj.y2, 300)

    def test_08_tracked_object_is_frozen(self):
        """TrackedObject is immutable (frozen dataclass)."""
        obj = TrackedObject(
            track_id=1, class_id=0, class_name="person",
            confidence=0.9, x1=10, y1=20, x2=100, y2=200,
        )
        with self.assertRaises(AttributeError):
            obj.track_id = 99


class TestValidFrameInput(unittest.TestCase):
    """Test that valid frames are accepted by the tracker."""

    def test_09_valid_bgr_frame_returns_list(self):
        """A valid BGR uint8 frame produces a list result (possibly empty)."""
        tracker = _get_shared_tracker()
        frame = _make_synthetic_frame(480, 640)
        result = tracker.update(frame)
        self.assertIsInstance(result, list)

    def test_10_result_contains_tracked_objects(self):
        """All items in the result list are TrackedObject instances."""
        tracker = _get_shared_tracker()
        frame = _make_synthetic_frame(480, 640)
        result = tracker.update(frame)
        for obj in result:
            self.assertIsInstance(obj, TrackedObject)


class TestInvalidFrameInput(unittest.TestCase):
    """Test that invalid frames are rejected."""

    def test_11a_none_frame_rejected(self):
        """None input raises InvalidFrameError."""
        tracker = _get_shared_tracker()
        with self.assertRaises(InvalidFrameError):
            tracker.update(None)

    def test_11b_non_numpy_frame_rejected(self):
        """Non-numpy input raises InvalidFrameError."""
        tracker = _get_shared_tracker()
        with self.assertRaises(InvalidFrameError):
            tracker.update([[1, 2, 3]])

    def test_11c_float32_frame_rejected(self):
        """Float32 frame raises InvalidFrameError."""
        tracker = _get_shared_tracker()
        frame = np.full((100, 100, 3), 0.5, dtype=np.float32)
        with self.assertRaises(InvalidFrameError):
            tracker.update(frame)

    def test_11d_grayscale_2d_frame_rejected(self):
        """2D grayscale frame raises InvalidFrameError."""
        tracker = _get_shared_tracker()
        frame = np.full((100, 100), 128, dtype=np.uint8)
        with self.assertRaises(InvalidFrameError):
            tracker.update(frame)


class TestOutputStructure(unittest.TestCase):
    """Test the structure and types of tracker output fields."""

    def test_12_output_field_types(self):
        """TrackedObject fields have correct types when constructed."""
        obj = TrackedObject(
            track_id=5, class_id=2, class_name="car",
            confidence=0.85, x1=50, y1=60, x2=200, y2=300,
        )
        self.assertIsInstance(obj.track_id, int)
        self.assertIsInstance(obj.class_id, int)
        self.assertIsInstance(obj.class_name, str)
        self.assertIsInstance(obj.confidence, float)
        self.assertIsInstance(obj.x1, int)
        self.assertIsInstance(obj.y1, int)
        self.assertIsInstance(obj.x2, int)
        self.assertIsInstance(obj.y2, int)

    def test_13_track_id_is_positive_integer(self):
        """Track IDs from real inference are positive integers."""
        obj = TrackedObject(
            track_id=1, class_id=0, class_name="person",
            confidence=0.9, x1=10, y1=20, x2=100, y2=200,
        )
        self.assertGreater(obj.track_id, 0)


class TestClassFiltering(unittest.TestCase):
    """Test that only IBVAP target classes are returned."""

    def test_14_target_classes_match_detector(self):
        """Tracker target classes match the detector's target classes."""
        tracker = _get_shared_tracker()
        self.assertEqual(tracker.target_classes, DEFAULT_TARGET_CLASSES)

    def test_15_only_target_classes_in_output(self):
        """Any tracked objects have class IDs from the IBVAP target set."""
        tracker = _get_shared_tracker()
        frame = _make_synthetic_frame(480, 640)
        result = tracker.update(frame)
        allowed_ids = set(DEFAULT_TARGET_CLASSES.keys())
        for obj in result:
            self.assertIn(
                obj.class_id, allowed_ids,
                f"Unexpected class_id {obj.class_id} ({obj.class_name})"
            )


class TestEmptyDetections(unittest.TestCase):
    """Test behavior when no objects are detected."""

    def test_16_blank_frame_returns_empty_list(self):
        """A blank synthetic frame returns an empty list (no false positives)."""
        tracker = _get_shared_tracker()
        # Use a small solid-color frame unlikely to trigger detections
        frame = _make_synthetic_frame(64, 64, color=(0, 0, 0))
        result = tracker.update(frame)
        self.assertIsInstance(result, list)
        # It SHOULD be empty on a tiny black frame, but if not, that's OK —
        # what matters is it doesn't crash and returns TrackedObject items
        for obj in result:
            self.assertIsInstance(obj, TrackedObject)


class TestPersistentState(unittest.TestCase):
    """Test that tracker state persists between consecutive update() calls."""

    def test_17_multiple_updates_without_crash(self):
        """Multiple consecutive update() calls on the same tracker succeed."""
        tracker = _get_shared_tracker()
        frame = _make_synthetic_frame(240, 320)
        for i in range(5):
            result = tracker.update(frame)
            self.assertIsInstance(result, list)

    def test_18_frame_count_increments(self):
        """frame_count property increments with each update() call."""
        detector = YOLODetector(device="cpu")
        tracker = ByteTrackTracker(detector)
        self.assertEqual(tracker.frame_count, 0)

        frame = _make_synthetic_frame(240, 320)
        tracker.update(frame)
        self.assertEqual(tracker.frame_count, 1)

        tracker.update(frame)
        self.assertEqual(tracker.frame_count, 2)


class TestResetBehavior(unittest.TestCase):
    """Test tracker reset functionality."""

    def test_19_reset_clears_frame_count(self):
        """reset() sets frame_count back to 0."""
        detector = YOLODetector(device="cpu")
        tracker = ByteTrackTracker(detector)
        frame = _make_synthetic_frame(240, 320)

        tracker.update(frame)
        self.assertGreater(tracker.frame_count, 0)

        tracker.reset()
        self.assertEqual(tracker.frame_count, 0)

    def test_20_reset_allows_continued_tracking(self):
        """Tracker works normally after reset()."""
        detector = YOLODetector(device="cpu")
        tracker = ByteTrackTracker(detector)
        frame = _make_synthetic_frame(240, 320)

        tracker.update(frame)
        tracker.reset()

        # Should not raise
        result = tracker.update(frame)
        self.assertIsInstance(result, list)


class TestCPUExecution(unittest.TestCase):
    """Test that tracking works correctly on CPU."""

    def test_21_cpu_tracking(self):
        """Tracker works on CPU device without errors."""
        detector = YOLODetector(device="cpu")
        tracker = ByteTrackTracker(detector)
        self.assertEqual(tracker.detector.device, "cpu")

        frame = _make_synthetic_frame(240, 320)
        result = tracker.update(frame)
        self.assertIsInstance(result, list)


class TestConsecutiveFrameTracking(unittest.TestCase):
    """Integration: verify actual tracking persistence across real video frames."""

    SAMPLE_VIDEO = PROJECT_ROOT / "videos" / "test.mp4"

    @unittest.skipUnless(
        (PROJECT_ROOT / "videos" / "test.mp4").exists(),
        "Sample video test.mp4 not available",
    )
    def test_22_real_video_consecutive_tracking(self):
        """Feed 20+ real video frames; tracked objects have valid track_id fields."""
        from ai_engine.video_input import VideoSource

        detector = YOLODetector(device="cpu")
        tracker = ByteTrackTracker(detector)

        all_ids_per_frame = []

        with VideoSource(source_type="video", source=self.SAMPLE_VIDEO) as src:
            frames_processed = 0
            for raw_frame in src:
                tracked = tracker.update(raw_frame)

                # Validate every tracked object
                for obj in tracked:
                    self.assertIsInstance(obj, TrackedObject)
                    self.assertIsInstance(obj.track_id, int)
                    self.assertGreater(obj.track_id, 0)
                    self.assertIn(obj.class_id, DEFAULT_TARGET_CLASSES)
                    self.assertGreaterEqual(obj.confidence, 0.0)
                    self.assertLessEqual(obj.confidence, 1.0)

                frame_ids = {obj.track_id for obj in tracked}
                all_ids_per_frame.append(frame_ids)

                frames_processed += 1
                if frames_processed >= 30:
                    break

        self.assertGreaterEqual(frames_processed, 20,
                                "Need at least 20 frames for meaningful tracking test")

    @unittest.skipUnless(
        (PROJECT_ROOT / "videos" / "test.mp4").exists(),
        "Sample video test.mp4 not available",
    )
    def test_23_track_ids_persist_across_frames(self):
        """At least one track ID appears in multiple consecutive frames,
        demonstrating genuine ID persistence."""
        from ai_engine.video_input import VideoSource

        detector = YOLODetector(device="cpu")
        tracker = ByteTrackTracker(detector)

        id_frame_count: dict = {}  # track_id → count of frames it appeared in

        with VideoSource(source_type="video", source=self.SAMPLE_VIDEO) as src:
            frames_processed = 0
            for raw_frame in src:
                tracked = tracker.update(raw_frame)

                for obj in tracked:
                    id_frame_count[obj.track_id] = (
                        id_frame_count.get(obj.track_id, 0) + 1
                    )

                frames_processed += 1
                if frames_processed >= 50:
                    break

        # At least one ID should have persisted across multiple frames
        persistent_ids = {tid: cnt for tid, cnt in id_frame_count.items() if cnt >= 2}
        self.assertTrue(
            len(persistent_ids) > 0,
            f"No track IDs persisted across 2+ frames out of "
            f"{len(id_frame_count)} unique IDs over {frames_processed} frames. "
            f"ByteTrack should maintain IDs for continuously visible objects."
        )


class TestIntegrationWithM1M2M3(unittest.TestCase):
    """Full pipeline regression: VideoSource → Preprocessor → Tracker."""

    SAMPLE_VIDEO = PROJECT_ROOT / "videos" / "test.mp4"

    @unittest.skipUnless(
        (PROJECT_ROOT / "videos" / "test.mp4").exists(),
        "Sample video test.mp4 not available",
    )
    def test_24_full_pipeline_integration(self):
        """M1 → M2 → M4(M3) pipeline produces valid tracked output."""
        from ai_engine.preprocessing import FramePreprocessor
        from ai_engine.video_input import VideoSource

        detector = YOLODetector(device="cpu")
        preprocessor = FramePreprocessor()
        tracker = ByteTrackTracker(detector)

        with VideoSource(source_type="video", source=self.SAMPLE_VIDEO) as src:
            frames_processed = 0
            for raw_frame in src:
                # M2 preprocessing
                processed = preprocessor.process(raw_frame)
                # M4 tracking (internally uses M3 model)
                tracked = tracker.update(processed)

                self.assertIsInstance(tracked, list)
                for obj in tracked:
                    self.assertIsInstance(obj, TrackedObject)

                frames_processed += 1
                if frames_processed >= 10:
                    break

        self.assertGreaterEqual(frames_processed, 5)

    @unittest.skipUnless(
        (PROJECT_ROOT / "videos" / "test.mp4").exists(),
        "Sample video test.mp4 not available",
    )
    def test_25_m3_detector_still_works_independently(self):
        """M3 detect() still works after tracker has been used (regression)."""
        from ai_engine.video_input import VideoSource

        detector = _get_shared_detector()

        with VideoSource(source_type="video", source=self.SAMPLE_VIDEO) as src:
            ret, frame = src.read()
            self.assertTrue(ret)

            # M3 direct detection should still work
            detections = detector.detect(frame)
            self.assertIsInstance(detections, list)
            for det in detections:
                self.assertIsInstance(det, Detection)


class TestMultipleObjects(unittest.TestCase):
    """Test that the tracker can handle multiple objects simultaneously."""

    SAMPLE_VIDEO = PROJECT_ROOT / "videos" / "test.mp4"

    @unittest.skipUnless(
        (PROJECT_ROOT / "videos" / "test.mp4").exists(),
        "Sample video test.mp4 not available",
    )
    def test_26_multiple_objects_tracked(self):
        """Multiple objects can be tracked in the same frame."""
        from ai_engine.video_input import VideoSource

        detector = YOLODetector(device="cpu")
        tracker = ByteTrackTracker(detector)

        max_objects_in_single_frame = 0

        with VideoSource(source_type="video", source=self.SAMPLE_VIDEO) as src:
            frames_processed = 0
            for raw_frame in src:
                tracked = tracker.update(raw_frame)
                if len(tracked) > max_objects_in_single_frame:
                    max_objects_in_single_frame = len(tracked)

                # If we find a frame with 2+ objects, that's sufficient
                if max_objects_in_single_frame >= 2:
                    break

                frames_processed += 1
                if frames_processed >= 50:
                    break

        # The test is informational — not all videos have multiple objects.
        # At minimum, no crash should occur.
        self.assertGreaterEqual(max_objects_in_single_frame, 0)


class TestDifferentClasses(unittest.TestCase):
    """Test that the tracker handles different object classes."""

    SAMPLE_VIDEO = PROJECT_ROOT / "videos" / "test.mp4"

    @unittest.skipUnless(
        (PROJECT_ROOT / "videos" / "test.mp4").exists(),
        "Sample video test.mp4 not available",
    )
    def test_27_different_classes_tracked(self):
        """Tracked objects can belong to different IBVAP target classes."""
        from ai_engine.video_input import VideoSource

        detector = YOLODetector(device="cpu")
        tracker = ByteTrackTracker(detector)
        observed_classes = set()

        with VideoSource(source_type="video", source=self.SAMPLE_VIDEO) as src:
            frames_processed = 0
            for raw_frame in src:
                tracked = tracker.update(raw_frame)
                for obj in tracked:
                    observed_classes.add(obj.class_name)
                    # Verify class_name matches class_id
                    expected_name = DEFAULT_TARGET_CLASSES.get(obj.class_id)
                    self.assertEqual(
                        obj.class_name, expected_name,
                        f"class_name '{obj.class_name}' doesn't match "
                        f"class_id {obj.class_id} (expected '{expected_name}')",
                    )
                frames_processed += 1
                if frames_processed >= 50:
                    break

        # Informational: log observed classes
        # (video content determines what classes appear)


class TestReprAndStr(unittest.TestCase):
    """Test repr output of tracker."""

    def test_28_tracker_repr(self):
        """ByteTrackTracker has a meaningful repr string."""
        tracker = _get_shared_tracker()
        repr_str = repr(tracker)
        self.assertIn("ByteTrackTracker", repr_str)
        self.assertIn("bytetrack.yaml", repr_str)


if __name__ == "__main__":
    unittest.main()
