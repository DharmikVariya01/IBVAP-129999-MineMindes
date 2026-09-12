"""Automated tests for IBVAP Module 1 (Unified Video Input System)."""

from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.video_input import (
    SourceType,
    VideoSource,
    VideoSourceError,
    VideoSourceNotFoundError,
    VideoSourceOpenError,
)

SAMPLE_VIDEO_PATH = PROJECT_ROOT / "videos" / "test.mp4"


class TestVideoSourceVideoFile(unittest.TestCase):
    """Tests VideoSource with local video files."""

    def setUp(self):
        self.assertTrue(
            SAMPLE_VIDEO_PATH.exists(),
            f"Required sample video not found at: {SAMPLE_VIDEO_PATH}",
        )

    def test_video_metadata_and_properties(self):
        """Verify video properties: width, height, FPS, frame count, and source type."""
        source = VideoSource(source_type="video", source=SAMPLE_VIDEO_PATH)
        self.assertEqual(source.source_type, "video")
        self.assertFalse(source.is_opened)

        source.open()
        try:
            self.assertTrue(source.is_opened)
            self.assertEqual(source.width, 256)
            self.assertEqual(source.height, 144)
            self.assertEqual(source.fps, 6.0)
            self.assertEqual(source.frame_count, 102)
            self.assertEqual(source.current_frame_index, 0)

            metadata = source.get_metadata()
            self.assertEqual(metadata["source_type"], "video")
            self.assertEqual(metadata["width"], 256)
            self.assertEqual(metadata["height"], 144)
            self.assertEqual(metadata["frame_count"], 102)
        finally:
            source.release()

        self.assertFalse(source.is_opened)

    def test_read_bgr_frame_format(self):
        """Verify that returned frames are standard 3-channel BGR numpy arrays."""
        with VideoSource(source_type="video", source=SAMPLE_VIDEO_PATH) as src:
            ret, frame = src.read()

            self.assertTrue(ret)
            self.assertIsNotNone(frame)
            self.assertIsInstance(frame, np.ndarray)
            self.assertEqual(frame.dtype, np.uint8)
            self.assertEqual(frame.ndim, 3)
            # Standard BGR shape: (height, width, 3)
            self.assertEqual(frame.shape, (144, 256, 3))
            self.assertEqual(src.current_frame_index, 1)

    def test_context_manager_lifecycle(self):
        """Verify that context manager correctly opens and releases resources."""
        source = VideoSource(source_type="video", source=SAMPLE_VIDEO_PATH)
        self.assertFalse(source.is_opened)

        with source as src:
            self.assertTrue(src.is_opened)
            ret, frame = src.read()
            self.assertTrue(ret)
            self.assertIsNotNone(frame)

        self.assertFalse(source.is_opened)

    def test_iterator_protocol(self):
        """Verify generator iteration yields valid frames."""
        with VideoSource(source_type="video", source=SAMPLE_VIDEO_PATH) as src:
            frames_read = 0
            for frame in src:
                self.assertIsInstance(frame, np.ndarray)
                self.assertEqual(frame.shape, (144, 256, 3))
                frames_read += 1
                if frames_read >= 5:
                    break

            self.assertEqual(frames_read, 5)

    def test_end_of_file_handling(self):
        """Verify that reading past the end of a video returns (False, None) cleanly."""
        with VideoSource(source_type="video", source=SAMPLE_VIDEO_PATH) as src:
            frames_read = 0
            while True:
                ret, frame = src.read()
                if not ret:
                    self.assertIsNone(frame)
                    break
                frames_read += 1

            self.assertEqual(frames_read, 102)
            self.assertEqual(src.current_frame_index, 102)

            # Subsequent read calls should continue returning (False, None) without crashing
            subsequent_ret, subsequent_frame = src.read()
            self.assertFalse(subsequent_ret)
            self.assertIsNone(subsequent_frame)

    def test_nonexistent_video_file_raises_error(self):
        """Verify that a missing video file raises VideoSourceNotFoundError."""
        missing_path = PROJECT_ROOT / "videos" / "definitely_does_not_exist_12345.mp4"
        with self.assertRaises(VideoSourceNotFoundError):
            VideoSource(source_type="video", source=missing_path)

    def test_empty_video_path_raises_error(self):
        """Verify that an empty path for video source raises ValueError."""
        with self.assertRaises(ValueError):
            VideoSource(source_type="video", source="")


class TestVideoSourceWebcam(unittest.TestCase):
    """Tests VideoSource with laptop webcam configurations."""

    def test_webcam_default_index(self):
        """Verify webcam defaults to camera index 0."""
        source = VideoSource(source_type="webcam")
        self.assertEqual(source.source_type, "webcam")
        self.assertEqual(source.source, 0)

    def test_webcam_configurable_index(self):
        """Verify configurable integer and string camera indices."""
        src_int = VideoSource(source_type="webcam", source=2)
        self.assertEqual(src_int.source, 2)

        src_str = VideoSource(source_type="webcam", source="1")
        self.assertEqual(src_str.source, 1)

    def test_webcam_invalid_index_raises_error(self):
        """Verify negative or non-integer indices raise ValueError."""
        with self.assertRaises(ValueError):
            VideoSource(source_type="webcam", source=-1)

        with self.assertRaises(ValueError):
            VideoSource(source_type="webcam", source="not_a_number")

    def test_webcam_live_hardware_capture(self):
        """Verify reading from real physical laptop webcam if accessible."""
        try:
            source = VideoSource(source_type="webcam", source=0)
            source.open()
        except VideoSourceOpenError:
            self.skipTest("Physical webcam device 0 not accessible in this execution context.")
            return

        try:
            self.assertTrue(source.is_opened)
            ret, frame = source.read()
            self.assertTrue(ret)
            self.assertIsNotNone(frame)
            self.assertIsInstance(frame, np.ndarray)
            self.assertEqual(frame.dtype, np.uint8)
            self.assertEqual(frame.ndim, 3)
            self.assertEqual(frame.shape[2], 3)  # BGR 3-channel
            self.assertGreater(source.width, 0)
            self.assertGreater(source.height, 0)
        finally:
            source.release()

        self.assertFalse(source.is_opened)

    @patch("cv2.VideoCapture")
    def test_webcam_unavailable_raises_open_error(self, mock_cv_capture):
        """Verify VideoSourceOpenError is raised when webcam device cannot be opened."""
        mock_instance = MagicMock()
        mock_instance.isOpened.return_value = False
        mock_cv_capture.return_value = mock_instance

        source = VideoSource(source_type="webcam", source=99)
        with self.assertRaises(VideoSourceOpenError) as ctx:
            source.open()

        self.assertIn("Failed to open webcam", str(ctx.exception))


class TestVideoSourceUnifiedInterface(unittest.TestCase):
    """Tests the unified behavior and contract across source types."""

    def test_invalid_source_type(self):
        """Verify unsupported source type raises ValueError."""
        with self.assertRaises(ValueError):
            VideoSource(source_type="unknown_source_type")

    def test_future_rtsp_validation(self):
        """Verify RTSP source type accepts a URL string without requiring testing."""
        rtsp_source = VideoSource(source_type="rtsp", source="rtsp://192.168.1.100:554/live")
        self.assertEqual(rtsp_source.source_type, "rtsp")
        self.assertEqual(rtsp_source.source, "rtsp://192.168.1.100:554/live")

        with self.assertRaises(ValueError):
            VideoSource(source_type="rtsp", source="")

    def test_double_release_is_safe(self):
        """Verify calling release multiple times is idempotent and safe."""
        source = VideoSource(source_type="video", source=SAMPLE_VIDEO_PATH)
        source.open()
        source.release()
        self.assertFalse(source.is_opened)
        # Should not throw
        source.release()
        self.assertFalse(source.is_opened)


if __name__ == "__main__":
    unittest.main()
