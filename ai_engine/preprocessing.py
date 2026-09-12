"""Preprocessing module for IBVAP AI Engine.

Module 2: Low-Light Enhancement using CLAHE.
Accepts raw BGR frames from VideoSource, deterministically analyzes grayscale
brightness/luminance, and selectively applies Contrast Limited Adaptive Histogram
Equalization (CLAHE) on the Lightness (L) channel in LAB color space only when
frames fall below a configurable low-light threshold.

The output strictly complies with the BGR uint8 3-channel contract required by
subsequent analytics modules (such as Module 3: YOLO Detection).
"""

from dataclasses import dataclass
import logging
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("ibvap.ai_engine.preprocessing")


class PreprocessingError(Exception):
    """Base exception for preprocessing errors in IBVAP AI Engine."""
    pass


class InvalidFrameError(PreprocessingError, ValueError):
    """Raised when an input frame does not conform to the expected BGR image specifications."""
    pass


@dataclass(frozen=True)
class PreprocessResult:
    """Detailed result of frame preprocessing analysis and transformation.

    Attributes:
        frame: Processed BGR frame (enhanced or original content copy), uint8 (H, W, 3).
        brightness: Mean luminance / brightness value in range [0.0, 255.0].
        is_low_light: Whether the frame was classified as low-light.
        enhancement_applied: Whether CLAHE enhancement was actively applied.
    """
    frame: np.ndarray
    brightness: float
    is_low_light: bool
    enhancement_applied: bool


class FramePreprocessor:
    """Deterministic low-light detection and adaptive CLAHE preprocessor.

    Receives raw BGR NumPy frames from any VideoSource (webcam, MP4, RTSP),
    calculates grayscale luminance, and applies CLAHE in LAB color space if the
    frame is darker than a configurable threshold.

    Guarantees:
    - Never modifies the original input frame array in-place.
    - Preserves input resolution and dimensions exactly.
    - Always returns a valid 3-channel BGR uint8 NumPy array.
    - Fast, deterministic execution without heavy AI/ML dependencies.
    """

    DEFAULT_BRIGHTNESS_THRESHOLD: float = 60.0
    DEFAULT_CLIP_LIMIT: float = 2.0
    DEFAULT_TILE_GRID_SIZE: Tuple[int, int] = (8, 8)

    def __init__(
        self,
        brightness_threshold: float = DEFAULT_BRIGHTNESS_THRESHOLD,
        clip_limit: float = DEFAULT_CLIP_LIMIT,
        tile_grid_size: Tuple[int, int] = DEFAULT_TILE_GRID_SIZE,
    ) -> None:
        """Initialize the FramePreprocessor with configurable thresholds and parameters.

        Args:
            brightness_threshold: Grayscale mean brightness threshold [0.0, 255.0].
                Frames with mean brightness < threshold are classified as low-light.
            clip_limit: Threshold for contrast limiting in OpenCV CLAHE.
                Higher values produce stronger contrast; lower values avoid noise.
            tile_grid_size: Contextual grid size (columns, rows) for adaptive equalization.
                Default is (8, 8).

        Raises:
            ValueError: If parameters are outside valid operational ranges.
        """
        if not (0.0 <= brightness_threshold <= 255.0):
            raise ValueError(
                f"brightness_threshold must be between 0.0 and 255.0, got: {brightness_threshold}"
            )
        if clip_limit <= 0.0:
            raise ValueError(f"clip_limit must be greater than 0.0, got: {clip_limit}")
        if (
            len(tile_grid_size) != 2
            or tile_grid_size[0] < 1
            or tile_grid_size[1] < 1
        ):
            raise ValueError(
                f"tile_grid_size must be a tuple of 2 positive ints (width, height), got: {tile_grid_size}"
            )

        self._brightness_threshold = float(brightness_threshold)
        self._clip_limit = float(clip_limit)
        self._tile_grid_size = (int(tile_grid_size[0]), int(tile_grid_size[1]))

        # Telemetry / state of the most recent frame processed
        self._last_brightness: Optional[float] = None
        self._last_is_low_light: Optional[bool] = None
        self._last_enhancement_applied: Optional[bool] = None

        logger.info(
            "FramePreprocessor initialized (threshold=%.1f, clip_limit=%.1f, tile_grid=%s)",
            self._brightness_threshold,
            self._clip_limit,
            self._tile_grid_size,
        )

    # -------------------------------------------------------------------------
    # Properties & Configuration
    # -------------------------------------------------------------------------

    @property
    def brightness_threshold(self) -> float:
        """Return the current low-light brightness threshold."""
        return self._brightness_threshold

    @brightness_threshold.setter
    def brightness_threshold(self, value: float) -> None:
        """Set a new low-light brightness threshold at runtime."""
        if not (0.0 <= value <= 255.0):
            raise ValueError(f"brightness_threshold must be in [0.0, 255.0], got: {value}")
        self._brightness_threshold = float(value)

    @property
    def clip_limit(self) -> float:
        """Return the CLAHE contrast clip limit."""
        return self._clip_limit

    @clip_limit.setter
    def clip_limit(self, value: float) -> None:
        """Set a new CLAHE contrast clip limit at runtime."""
        if value <= 0.0:
            raise ValueError(f"clip_limit must be greater than 0.0, got: {value}")
        self._clip_limit = float(value)

    @property
    def tile_grid_size(self) -> Tuple[int, int]:
        """Return the CLAHE tile grid size."""
        return self._tile_grid_size

    @tile_grid_size.setter
    def tile_grid_size(self, value: Tuple[int, int]) -> None:
        """Set a new CLAHE tile grid size at runtime."""
        if len(value) != 2 or value[0] < 1 or value[1] < 1:
            raise ValueError(f"tile_grid_size must be 2 positive ints, got: {value}")
        self._tile_grid_size = (int(value[0]), int(value[1]))

    @property
    def last_brightness(self) -> Optional[float]:
        """Return mean luminance value of the last processed frame."""
        return self._last_brightness

    @property
    def last_is_low_light(self) -> Optional[bool]:
        """Return whether the last processed frame was detected as low-light."""
        return self._last_is_low_light

    @property
    def last_enhancement_applied(self) -> Optional[bool]:
        """Return whether enhancement was actively applied to the last processed frame."""
        return self._last_enhancement_applied

    # -------------------------------------------------------------------------
    # Frame Validation
    # -------------------------------------------------------------------------

    def validate_frame(self, frame: np.ndarray) -> None:
        """Validate that the input array meets OpenCV BGR image requirements.

        Args:
            frame: Object to validate.

        Raises:
            InvalidFrameError: If the input is not a valid 3-channel uint8 image.
        """
        if frame is None:
            raise InvalidFrameError("Input frame is None.")

        if not isinstance(frame, np.ndarray):
            raise InvalidFrameError(f"Expected numpy.ndarray, got: {type(frame).__name__}")

        if frame.dtype != np.uint8:
            raise InvalidFrameError(
                f"Expected frame dtype uint8, got: {frame.dtype}"
            )

        if frame.ndim != 3:
            raise InvalidFrameError(
                f"Expected 3-dimensional array (H, W, C), got ndim={frame.ndim} with shape {frame.shape}"
            )

        if frame.shape[2] != 3:
            raise InvalidFrameError(
                f"Expected 3 channels (BGR), got {frame.shape[2]} channels with shape {frame.shape}"
            )

        height, width = frame.shape[:2]
        if height < 1 or width < 1:
            raise InvalidFrameError(
                f"Frame dimensions must be at least 1x1, got: {width}x{height}"
            )

    # -------------------------------------------------------------------------
    # Luminance Analysis & Low-Light Detection
    # -------------------------------------------------------------------------

    def compute_brightness(self, frame: np.ndarray) -> float:
        """Deterministically calculate the average luminance of a BGR frame.

        Converts frame to grayscale and computes the arithmetic mean pixel intensity.

        Args:
            frame: Valid OpenCV BGR frame (H, W, 3).

        Returns:
            Mean luminance as a float in the range [0.0, 255.0].
        """
        self.validate_frame(frame)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return float(np.mean(gray))

    def is_low_light(self, frame: np.ndarray) -> bool:
        """Check whether a frame's average luminance is below the threshold.

        Args:
            frame: Valid OpenCV BGR frame (H, W, 3).

        Returns:
            True if the frame is classified as low-light; False otherwise.
        """
        brightness = self.compute_brightness(frame)
        return brightness < self._brightness_threshold

    # -------------------------------------------------------------------------
    # CLAHE Enhancement
    # -------------------------------------------------------------------------

    def apply_clahe(self, frame: np.ndarray) -> np.ndarray:
        """Apply CLAHE enhancement on the Lightness (L) channel in LAB color space.

        Pipeline:
        1. Convert BGR to LAB.
        2. Extract Lightness (L) channel.
        3. Apply CLAHE to L channel using configured clipLimit and tileGridSize.
        4. Merge enhanced L channel with original A and B chrominance channels.
        5. Convert LAB back to BGR.

        The original frame is never modified.

        Args:
            frame: Valid OpenCV BGR frame (H, W, 3) with uint8 dtype.

        Returns:
            Enhanced BGR frame with identical resolution, shape, and uint8 dtype.
        """
        self.validate_frame(frame)

        height, width = frame.shape[:2]

        # Adapt tile grid size safely if frame is smaller than the default tile size
        effective_tile_grid = (
            max(1, min(self._tile_grid_size[0], width)),
            max(1, min(self._tile_grid_size[1], height)),
        )

        # Convert to LAB color space
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)

        # Apply CLAHE to Lightness channel only
        clahe = cv2.createCLAHE(
            clipLimit=self._clip_limit,
            tileGridSize=effective_tile_grid,
        )
        l_enhanced = clahe.apply(l_channel)

        # Merge channels and convert back to BGR
        lab_enhanced = cv2.merge((l_enhanced, a_channel, b_channel))
        enhanced_bgr = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

        return enhanced_bgr

    # -------------------------------------------------------------------------
    # Main Processing Pipeline
    # -------------------------------------------------------------------------

    def process_with_info(self, frame: np.ndarray) -> PreprocessResult:
        """Process a BGR frame, returning both the output frame and metadata.

        If the frame is classified as low-light, CLAHE enhancement is applied.
        If the frame has normal lighting, an unchanged copy of the original
        frame is returned, bypassing CLAHE.

        Args:
            frame: Raw OpenCV BGR frame from VideoSource (uint8, H, W, 3).

        Returns:
            PreprocessResult containing:
                - frame: Processed BGR frame (H, W, 3, uint8)
                - brightness: Float mean brightness [0.0, 255.0]
                - is_low_light: Bool indicating low-light condition
                - enhancement_applied: Bool indicating whether CLAHE was applied
        """
        self.validate_frame(frame)

        brightness = self.compute_brightness(frame)
        is_dark = brightness < self._brightness_threshold

        if is_dark:
            output_frame = self.apply_clahe(frame)
            enhancement_applied = True
        else:
            output_frame = frame.copy()
            enhancement_applied = False

        # Update telemetry cache
        self._last_brightness = brightness
        self._last_is_low_light = is_dark
        self._last_enhancement_applied = enhancement_applied

        return PreprocessResult(
            frame=output_frame,
            brightness=brightness,
            is_low_light=is_dark,
            enhancement_applied=enhancement_applied,
        )

    def process(self, frame: np.ndarray) -> np.ndarray:
        """Primary processing method for downstream consumption (e.g. Module 3 YOLO).

        Input: Raw BGR frame.
        Output: Enhanced BGR frame (if low-light) or copy of original (if normal).

        Args:
            frame: Raw OpenCV BGR frame (uint8, H, W, 3).

        Returns:
            Processed OpenCV BGR frame (uint8, H, W, 3).
        """
        result = self.process_with_info(frame)
        return result.frame

    def __call__(self, frame: np.ndarray) -> np.ndarray:
        """Callable alias for process(frame)."""
        return self.process(frame)
