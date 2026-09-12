"""Automated tests for IBVAP Module 2 (Low-Light Enhancement using CLAHE)."""

from pathlib import Path
import sys
import unittest

import cv2
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.preprocessing import (
    FramePreprocessor,
    InvalidFrameError,
    PreprocessResult,
    PreprocessingError,
)
from ai_engine.video_input import VideoSource

SAMPLE_VIDEO_PATH = PROJECT_ROOT / "videos" / "test.mp4"


class TestFramePreprocessorDetectionAndEnhancement(unittest.TestCase):
    """Tests for low-light detection, CLAHE enhancement logic, and threshold behavior."""

    def setUp(self):
        self.preprocessor = FramePreprocessor(brightness_threshold=60.0)

        # Deterministic bright frame (all channels 150 -> mean brightness 150)
        self.bright_frame = np.full((120, 160, 3), 150, dtype=np.uint8)

        # Deterministic dark frame (all channels 30 -> mean brightness 30)
        # Add some slight gradient so CLAHE has local contrast variation to equalize
        y, x = np.mgrid[0:120, 0:160]
        gradient = (20 + (x / 160.0) * 20).astype(np.uint8)
        self.dark_frame = np.stack([gradient, gradient, gradient], axis=-1)

    def test_1_normal_bright_frame_does_not_apply_clahe(self):
        """Requirement 1: Normal-bright frame does not unnecessarily apply CLAHE."""
        brightness = self.preprocessor.compute_brightness(self.bright_frame)
        self.assertGreaterEqual(brightness, 60.0)
        self.assertFalse(self.preprocessor.is_low_light(self.bright_frame))

        result = self.preprocessor.process_with_info(self.bright_frame)
        self.assertFalse(result.is_low_light)
        self.assertFalse(result.enhancement_applied)

        # Content must be identical to the original bright frame
        np.testing.assert_array_equal(result.frame, self.bright_frame)

    def test_2_dark_frame_detected_as_low_light(self):
        """Requirement 2: Dark frame is detected as low-light."""
        brightness = self.preprocessor.compute_brightness(self.dark_frame)
        self.assertLess(brightness, 60.0)
        self.assertTrue(self.preprocessor.is_low_light(self.dark_frame))

        result = self.preprocessor.process_with_info(self.dark_frame)
        self.assertTrue(result.is_low_light)
        self.assertAlmostEqual(result.brightness, brightness, places=3)

    def test_3_dark_frame_receives_clahe_enhancement(self):
        """Requirement 3: Dark frame receives CLAHE enhancement."""
        result = self.preprocessor.process_with_info(self.dark_frame)
        self.assertTrue(result.enhancement_applied)

        # The enhanced frame must have modified pixel values reflecting contrast stretching
        self.assertFalse(
            np.array_equal(result.frame, self.dark_frame),
            "Enhanced frame should differ in pixel values from the raw dark frame.",
        )
        # CLAHE enhances local contrast and increases pixel variance / dynamic range
        self.assertGreater(
            np.std(result.frame),
            np.std(self.dark_frame),
            "CLAHE enhancement must increase the standard deviation (contrast).",
        )

    def test_4_output_is_numpy_ndarray(self):
        """Requirement 4: Output is NumPy ndarray."""
        output = self.preprocessor.process(self.bright_frame)
        self.assertIsInstance(output, np.ndarray)

        output_dark = self.preprocessor.process(self.dark_frame)
        self.assertIsInstance(output_dark, np.ndarray)

    def test_5_output_dtype_is_uint8(self):
        """Requirement 5: Output dtype is uint8."""
        output_bright = self.preprocessor.process(self.bright_frame)
        self.assertEqual(output_bright.dtype, np.uint8)

        output_dark = self.preprocessor.process(self.dark_frame)
        self.assertEqual(output_dark.dtype, np.uint8)

    def test_6_output_has_exactly_3_channels(self):
        """Requirement 6: Output has exactly 3 channels."""
        output_bright = self.preprocessor.process(self.bright_frame)
        self.assertEqual(output_bright.ndim, 3)
        self.assertEqual(output_bright.shape[2], 3)

        output_dark = self.preprocessor.process(self.dark_frame)
        self.assertEqual(output_dark.ndim, 3)
        self.assertEqual(output_dark.shape[2], 3)

    def test_7_output_remains_bgr(self):
        """Requirement 7: Output remains OpenCV BGR format."""
        # Create a distinctive colored dark frame with blue dominance: B=50, G=20, R=10
        blue_dark_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        blue_dark_frame[:, :, 0] = 50  # B
        blue_dark_frame[:, :, 1] = 20  # G
        blue_dark_frame[:, :, 2] = 10  # R

        output = self.preprocessor.process(blue_dark_frame)
        self.assertEqual(output.shape, (100, 100, 3))
        self.assertEqual(output.dtype, np.uint8)

        # In BGR color space, the B channel (index 0) must remain higher than R (index 2)
        mean_b = np.mean(output[:, :, 0])
        mean_r = np.mean(output[:, :, 2])
        self.assertGreater(mean_b, mean_r, "Enhanced frame must maintain BGR channel ordering.")

    def test_8_output_resolution_equals_input_resolution(self):
        """Requirement 8: Output resolution equals input resolution."""
        for shape in [(720, 1280, 3), (480, 640, 3), (144, 256, 3), (57, 89, 3)]:
            test_img = np.full(shape, 30, dtype=np.uint8)
            out = self.preprocessor.process(test_img)
            self.assertEqual(out.shape, shape)

    def test_9_original_input_frame_is_not_modified(self):
        """Requirement 9: Original input frame is not modified."""
        dark_copy = self.dark_frame.copy()
        _ = self.preprocessor.process(self.dark_frame)
        np.testing.assert_array_equal(
            self.dark_frame,
            dark_copy,
            "Dark input frame was modified in-place during CLAHE processing!",
        )

        bright_copy = self.bright_frame.copy()
        _ = self.preprocessor.process(self.bright_frame)
        np.testing.assert_array_equal(
            self.bright_frame,
            bright_copy,
            "Bright input frame was modified in-place during bypass processing!",
        )

    def test_10_threshold_is_configurable(self):
        """Requirement 10: Threshold is configurable at init and runtime."""
        frame = np.full((100, 100, 3), 70, dtype=np.uint8)

        # With threshold 60, frame (brightness 70) is NOT low-light
        prep_low = FramePreprocessor(brightness_threshold=60.0)
        self.assertFalse(prep_low.is_low_light(frame))

        # With threshold 80, frame (brightness 70) IS low-light
        prep_high = FramePreprocessor(brightness_threshold=80.0)
        self.assertTrue(prep_high.is_low_light(frame))

        # Runtime reconfiguration
        prep_low.brightness_threshold = 75.0
        self.assertEqual(prep_low.brightness_threshold, 75.0)
        self.assertTrue(prep_low.is_low_light(frame))

    def test_11_clahe_parameters_are_configurable(self):
        """Requirement 11: CLAHE parameters are configurable at init and runtime."""
        # Test custom parameters at initialization
        custom_prep = FramePreprocessor(
            clip_limit=4.0,
            tile_grid_size=(16, 16),
            brightness_threshold=90.0,
        )
        self.assertEqual(custom_prep.clip_limit, 4.0)
        self.assertEqual(custom_prep.tile_grid_size, (16, 16))
        self.assertEqual(custom_prep.brightness_threshold, 90.0)

        # Test runtime reconfiguration
        custom_prep.clip_limit = 3.5
        self.assertEqual(custom_prep.clip_limit, 3.5)
        custom_prep.tile_grid_size = (4, 4)
        self.assertEqual(custom_prep.tile_grid_size, (4, 4))

        # Ensure processed output with high clipLimit gives stronger enhancement than low clipLimit
        prep_mild = FramePreprocessor(clip_limit=1.0, brightness_threshold=100.0)
        prep_strong = FramePreprocessor(clip_limit=5.0, brightness_threshold=100.0)

        out_mild = prep_mild.process(self.dark_frame)
        out_strong = prep_strong.process(self.dark_frame)

        self.assertGreater(np.std(out_strong), np.std(out_mild))

    def test_12_very_small_valid_frames_do_not_crash(self):
        """Requirement 12: Very small/valid frames do not crash."""
        small_sizes = [(1, 1), (2, 2), (4, 4), (8, 8), (16, 16), (24, 32)]
        for h, w in small_sizes:
            small_dark = np.full((h, w, 3), 20, dtype=np.uint8)
            output = self.preprocessor.process(small_dark)
            self.assertEqual(output.shape, (h, w, 3))
            self.assertEqual(output.dtype, np.uint8)

    def test_13_invalid_frame_input_is_handled_clearly(self):
        """Requirement 13: Invalid frame input is handled clearly with informative errors."""
        # 1. None
        with self.assertRaises(InvalidFrameError):
            self.preprocessor.process(None)

        # 2. Non-numpy input
        with self.assertRaises(InvalidFrameError):
            self.preprocessor.process([[1, 2, 3]])

        # 3. Float dtype instead of uint8
        float_frame = np.full((100, 100, 3), 0.5, dtype=np.float32)
        with self.assertRaises(InvalidFrameError):
            self.preprocessor.process(float_frame)

        # 4. 2D array (grayscale) instead of 3-channel BGR
        gray_frame = np.full((100, 100), 50, dtype=np.uint8)
        with self.assertRaises(InvalidFrameError):
            self.preprocessor.process(gray_frame)

        # 5. 4-channel BGRA array
        bgra_frame = np.full((100, 100, 4), 50, dtype=np.uint8)
        with self.assertRaises(InvalidFrameError):
            self.preprocessor.process(bgra_frame)

        # 6. Empty 0-dimension frame
        empty_frame = np.zeros((0, 0, 3), dtype=np.uint8)
        with self.assertRaises(InvalidFrameError):
            self.preprocessor.process(empty_frame)

    def test_14_video_source_integration(self):
        """Requirement 14: Module 1 VideoSource can feed frames into Module 2."""
        self.assertTrue(SAMPLE_VIDEO_PATH.exists(), f"Video file not found at: {SAMPLE_VIDEO_PATH}")

        with VideoSource(source_type="video", source=SAMPLE_VIDEO_PATH) as src:
            frames_processed = 0
            for raw_frame in src:
                # VideoSource delivers BGR uint8 frame
                self.assertEqual(raw_frame.dtype, np.uint8)
                self.assertEqual(raw_frame.ndim, 3)

                # Feed directly to preprocessor
                enhanced_frame = self.preprocessor.process(raw_frame)

                # Verify processed frame meets contract
                self.assertIsInstance(enhanced_frame, np.ndarray)
                self.assertEqual(enhanced_frame.dtype, np.uint8)
                self.assertEqual(enhanced_frame.shape, raw_frame.shape)

                frames_processed += 1
                if frames_processed >= 10:
                    break

            self.assertEqual(frames_processed, 10)

    def test_callable_and_telemetry_properties(self):
        """Verify __call__ alias and telemetry property updates."""
        res = self.preprocessor(self.dark_frame)
        self.assertEqual(res.shape, self.dark_frame.shape)

        self.assertIsNotNone(self.preprocessor.last_brightness)
        self.assertTrue(self.preprocessor.last_is_low_light)
        self.assertTrue(self.preprocessor.last_enhancement_applied)

    def test_constructor_parameter_validation(self):
        """Verify bounds checking on preprocessor constructor arguments."""
        with self.assertRaises(ValueError):
            FramePreprocessor(brightness_threshold=-1.0)
        with self.assertRaises(ValueError):
            FramePreprocessor(brightness_threshold=256.0)
        with self.assertRaises(ValueError):
            FramePreprocessor(clip_limit=0.0)
        with self.assertRaises(ValueError):
            FramePreprocessor(tile_grid_size=(0, 8))


if __name__ == "__main__":
    unittest.main()
