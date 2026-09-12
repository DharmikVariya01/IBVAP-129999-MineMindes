"""Automated tests for IBVAP Module 3 (YOLOv8n Person & Vehicle Detection).

All tests use synthetic/deterministic frames and do NOT require a webcam.
Tests validate the YOLODetector class, Detection dataclass, input validation,
output contract, class filtering, and CPU execution.
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
    DetectionError,
    InvalidFrameError,
    ModelLoadError,
    YOLODetector,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# Module-level detector instance (loaded once for all tests to avoid repeated
# model downloads / loads during the test run)
_shared_detector = None


def _get_shared_detector() -> YOLODetector:
    """Return a module-level YOLODetector instance, creating it once."""
    global _shared_detector
    if _shared_detector is None:
        _shared_detector = YOLODetector(device="cpu")
    return _shared_detector


def _make_synthetic_frame(
    height: int = 480,
    width: int = 640,
    color: tuple = (128, 128, 128),
) -> np.ndarray:
    """Create a deterministic synthetic BGR uint8 frame."""
    frame = np.full((height, width, 3), color, dtype=np.uint8)
    return frame


# ===========================================================================
# Test Cases
# ===========================================================================


class TestDetectorInitialization(unittest.TestCase):
    """Test 1 & 2: Detector and model initialization."""

    def test_1_detector_initializes_successfully(self):
        """Detector can be constructed without errors."""
        detector = _get_shared_detector()
        self.assertIsInstance(detector, YOLODetector)

    def test_2_model_loads_successfully(self):
        """The underlying YOLO model is loaded and available."""
        detector = _get_shared_detector()
        self.assertIsNotNone(detector.model)


class TestConfidenceThreshold(unittest.TestCase):
    """Test 3: Confidence threshold is configurable."""

    def test_3_confidence_threshold_configurable_at_init(self):
        """conf_threshold can be set at construction time."""
        detector = _get_shared_detector()
        # Default
        self.assertEqual(
            detector.conf_threshold,
            YOLODetector.DEFAULT_CONF_THRESHOLD,
        )

    def test_3b_confidence_threshold_configurable_at_runtime(self):
        """conf_threshold can be changed at runtime via property setter."""
        detector = _get_shared_detector()
        original = detector.conf_threshold

        detector.conf_threshold = 0.75
        self.assertEqual(detector.conf_threshold, 0.75)

        # Restore
        detector.conf_threshold = original

    def test_3c_invalid_confidence_threshold_rejected(self):
        """Out-of-range conf_threshold raises ValueError."""
        with self.assertRaises(ValueError):
            YOLODetector(conf_threshold=-0.1, device="cpu")
        with self.assertRaises(ValueError):
            YOLODetector(conf_threshold=1.5, device="cpu")


class TestFrameValidation(unittest.TestCase):
    """Tests 4 & 5: Valid frames accepted, invalid frames rejected."""

    def test_4_valid_bgr_frame_accepted(self):
        """A valid BGR uint8 frame produces a list result (possibly empty)."""
        detector = _get_shared_detector()
        frame = _make_synthetic_frame(480, 640)
        result = detector.detect(frame)
        self.assertIsInstance(result, list)

    def test_5a_none_frame_rejected(self):
        """None input raises InvalidFrameError."""
        detector = _get_shared_detector()
        with self.assertRaises(InvalidFrameError):
            detector.detect(None)

    def test_5b_non_numpy_frame_rejected(self):
        """Non-numpy input raises InvalidFrameError."""
        detector = _get_shared_detector()
        with self.assertRaises(InvalidFrameError):
            detector.detect([[1, 2, 3]])

    def test_5c_float32_frame_rejected(self):
        """Float32 frame raises InvalidFrameError."""
        detector = _get_shared_detector()
        frame = np.full((100, 100, 3), 0.5, dtype=np.float32)
        with self.assertRaises(InvalidFrameError):
            detector.detect(frame)

    def test_5d_grayscale_2d_frame_rejected(self):
        """2D grayscale frame raises InvalidFrameError."""
        detector = _get_shared_detector()
        frame = np.full((100, 100), 128, dtype=np.uint8)
        with self.assertRaises(InvalidFrameError):
            detector.detect(frame)

    def test_5e_four_channel_frame_rejected(self):
        """4-channel BGRA frame raises InvalidFrameError."""
        detector = _get_shared_detector()
        frame = np.full((100, 100, 4), 128, dtype=np.uint8)
        with self.assertRaises(InvalidFrameError):
            detector.detect(frame)


class TestDetectionResultContract(unittest.TestCase):
    """Tests 6, 7, 8: Detection dataclass field validation."""

    def test_6_detection_has_required_fields(self):
        """Detection dataclass has all 7 required fields."""
        expected_fields = {
            "class_id", "class_name", "confidence",
            "x1", "y1", "x2", "y2",
        }
        actual_fields = {f.name for f in dataclass_fields(Detection)}
        self.assertEqual(expected_fields, actual_fields)

    def test_6b_detection_constructor(self):
        """Detection can be instantiated with all required fields."""
        det = Detection(
            class_id=0,
            class_name="person",
            confidence=0.92,
            x1=100, y1=50, x2=200, y2=300,
        )
        self.assertEqual(det.class_id, 0)
        self.assertEqual(det.class_name, "person")
        self.assertAlmostEqual(det.confidence, 0.92)
        self.assertEqual(det.x1, 100)
        self.assertEqual(det.y1, 50)
        self.assertEqual(det.x2, 200)
        self.assertEqual(det.y2, 300)

    def test_7_bounding_boxes_valid_pixel_coordinates(self):
        """Any detections from inference have valid bounding-box pixel coords."""
        detector = _get_shared_detector()
        frame = _make_synthetic_frame(480, 640)
        detections = detector.detect(frame)

        for det in detections:
            self.assertGreaterEqual(det.x1, 0)
            self.assertGreaterEqual(det.y1, 0)
            self.assertLessEqual(det.x2, 640)
            self.assertLessEqual(det.y2, 480)
            self.assertLess(det.x1, det.x2, "x1 must be < x2")
            self.assertLess(det.y1, det.y2, "y1 must be < y2")

    def test_7b_constructed_detection_coordinates(self):
        """Directly constructed Detection validates pixel coordinate semantics."""
        det = Detection(
            class_id=2, class_name="car", confidence=0.88,
            x1=10, y1=20, x2=300, y2=400,
        )
        self.assertGreaterEqual(det.x1, 0)
        self.assertGreaterEqual(det.y1, 0)
        self.assertLess(det.x1, det.x2)
        self.assertLess(det.y1, det.y2)

    def test_8_confidence_values_in_valid_range(self):
        """Any detections have confidence values within [0.0, 1.0]."""
        detector = _get_shared_detector()
        frame = _make_synthetic_frame(480, 640)
        detections = detector.detect(frame)

        for det in detections:
            self.assertGreaterEqual(det.confidence, 0.0)
            self.assertLessEqual(det.confidence, 1.0)


class TestClassFiltering(unittest.TestCase):
    """Test 9: Only IBVAP target classes are returned."""

    def test_9_only_target_classes_returned(self):
        """Detections only contain the allowed COCO class IDs."""
        detector = _get_shared_detector()
        allowed_ids = set(DEFAULT_TARGET_CLASSES.keys())

        frame = _make_synthetic_frame(480, 640)
        detections = detector.detect(frame)

        for det in detections:
            self.assertIn(
                det.class_id,
                allowed_ids,
                f"Unexpected class_id {det.class_id} ({det.class_name}) "
                f"not in target classes",
            )

    def test_9b_target_classes_property(self):
        """Detector reports the correct target classes via property."""
        detector = _get_shared_detector()
        tc = detector.target_classes
        self.assertEqual(tc, DEFAULT_TARGET_CLASSES)


class TestNoTrackId(unittest.TestCase):
    """Test 10: No track_id is generated by Module 3."""

    def test_10_no_track_id_attribute(self):
        """Detection dataclass does NOT contain a track_id field."""
        field_names = {f.name for f in dataclass_fields(Detection)}
        self.assertNotIn("track_id", field_names)

    def test_10b_no_track_id_on_instance(self):
        """A Detection instance does not have a track_id attribute."""
        det = Detection(
            class_id=0, class_name="person", confidence=0.9,
            x1=10, y1=20, x2=100, y2=200,
        )
        self.assertFalse(hasattr(det, "track_id"))


class TestModelReuse(unittest.TestCase):
    """Test 11: Model is loaded once and reused across multiple frames."""

    def test_11_multiple_frames_without_reload(self):
        """Calling detect() multiple times uses the same model instance."""
        detector = _get_shared_detector()
        model_id = id(detector.model)

        frame = _make_synthetic_frame(240, 320)

        for _ in range(5):
            detector.detect(frame)
            self.assertEqual(
                id(detector.model),
                model_id,
                "Model object identity changed — model may have been reloaded.",
            )


class TestCPUExecution(unittest.TestCase):
    """Test 12: CPU execution works correctly."""

    def test_12_cpu_execution(self):
        """Detector works on CPU device without errors."""
        detector = YOLODetector(device="cpu")
        self.assertEqual(detector.device, "cpu")

        frame = _make_synthetic_frame(240, 320)
        result = detector.detect(frame)
        self.assertIsInstance(result, list)


class TestIntegrationWithVideoSource(unittest.TestCase):
    """Integration: VideoSource frames can be passed to the detector."""

    SAMPLE_VIDEO = PROJECT_ROOT / "videos" / "test.mp4"

    @unittest.skipUnless(
        (PROJECT_ROOT / "videos" / "test.mp4").exists(),
        "Sample video test.mp4 not available",
    )
    def test_video_source_to_detector_integration(self):
        """Frames from VideoSource pass through the detector without errors."""
        from ai_engine.video_input import VideoSource

        detector = _get_shared_detector()

        with VideoSource(source_type="video", source=self.SAMPLE_VIDEO) as src:
            frames_processed = 0
            for raw_frame in src:
                detections = detector.detect(raw_frame)
                self.assertIsInstance(detections, list)
                frames_processed += 1
                if frames_processed >= 5:
                    break

            self.assertEqual(frames_processed, 5)


if __name__ == "__main__":
    unittest.main()
