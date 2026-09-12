"""Video input module for IBVAP AI Engine.

Provides a unified video acquisition layer capable of reading raw BGR frames
from diverse video sources (laptop webcams, local recorded video files such as MP4,
and future RTSP/IP CCTV streams) through a uniform VideoSource interface.
"""

from enum import Enum
import logging
import os
from pathlib import Path
from typing import Generator, Optional, Tuple, Union

import cv2
import numpy as np

logger = logging.getLogger("ibvap.ai_engine.video_input")


class SourceType(str, Enum):
    """Supported video source types."""
    WEBCAM = "webcam"
    VIDEO = "video"
    RTSP = "rtsp"


class VideoSourceError(Exception):
    """Base exception for video source errors in IBVAP."""
    pass


class VideoSourceNotFoundError(VideoSourceError):
    """Raised when a specified local video file cannot be found."""
    pass


class VideoSourceOpenError(VideoSourceError):
    """Raised when a video device, file, or network stream cannot be opened."""
    pass


class VideoSourceReadError(VideoSourceError):
    """Raised when an unrecoverable failure occurs while reading frames."""
    pass


class VideoSource:
    """Unified video input interface for the IBVAP AI Engine.

    Encapsulates OpenCV video capture logic and provides an identical API
    whether ingesting from a live webcam, a local video file (MP4, AVI, etc.),
    or a future RTSP stream. All frames are guaranteed to be raw 3-channel
    BGR NumPy arrays (H, W, 3) with dtype uint8.

    Example Usage:
        # Webcam
        with VideoSource(source_type="webcam", source=0) as src:
            for frame in src:
                # frame is raw BGR np.ndarray
                pass

        # Video File
        with VideoSource(source_type="video", source="videos/test.mp4") as src:
            ret, frame = src.read()
            while ret:
                # process frame
                ret, frame = src.read()
    """

    def __init__(
        self,
        source_type: Union[str, SourceType] = SourceType.WEBCAM,
        source: Optional[Union[int, str, Path]] = None,
        api_preference: int = cv2.CAP_ANY,
    ) -> None:
        """Initialize the video source.

        Args:
            source_type: Source category ('webcam', 'video', or 'rtsp').
            source: Source identifier. For 'webcam', an integer camera index
                (defaults to 0). For 'video', a file path string or Path.
                For 'rtsp', an RTSP stream URL.
            api_preference: Preferred OpenCV capture API backend (default cv2.CAP_ANY).
        """
        self._source_type = self._normalize_source_type(source_type)
        self._api_preference = api_preference
        self._cap: Optional[cv2.VideoCapture] = None
        self._current_frame_index: int = 0
        self._is_opened: bool = False

        # Metadata attributes
        self._width: int = 0
        self._height: int = 0
        self._fps: float = 0.0
        self._frame_count: Optional[int] = None

        # Source normalization & validation
        self._source = self._normalize_source(self._source_type, source)

    @staticmethod
    def _normalize_source_type(source_type: Union[str, SourceType]) -> SourceType:
        """Validate and normalize source type to SourceType enum."""
        if isinstance(source_type, SourceType):
            return source_type
        if isinstance(source_type, str):
            normalized = source_type.strip().lower()
            try:
                return SourceType(normalized)
            except ValueError:
                valid_types = [t.value for t in SourceType]
                raise ValueError(
                    f"Unsupported source_type: '{source_type}'. "
                    f"Supported types are: {', '.join(valid_types)}"
                ) from None
        raise ValueError(f"Invalid source_type type: {type(source_type).__name__}")

    @staticmethod
    def _normalize_source(
        source_type: SourceType,
        source: Optional[Union[int, str, Path]]
    ) -> Union[int, str]:
        """Validate and normalize the source identifier based on source type."""
        if source_type == SourceType.WEBCAM:
            if source is None:
                return 0
            if isinstance(source, int):
                if source < 0:
                    raise ValueError(f"Webcam camera index cannot be negative: {source}")
                return source
            if isinstance(source, str):
                try:
                    idx = int(source.strip())
                    if idx < 0:
                        raise ValueError
                    return idx
                except ValueError:
                    raise ValueError(
                        f"Invalid webcam camera index: '{source}'. Must be a non-negative integer."
                    ) from None
            raise ValueError(f"Invalid webcam source type: {type(source).__name__}")

        if source_type == SourceType.VIDEO:
            if source is None:
                raise ValueError("A valid video file path must be provided when source_type is 'video'.")
            path_str = str(source).strip()
            if not path_str:
                raise ValueError("Video file path cannot be empty.")
            video_path = Path(path_str).resolve()
            if not video_path.exists() or not video_path.is_file():
                raise VideoSourceNotFoundError(
                    f"Video file not found at: '{video_path}' (resolved from '{source}')"
                )
            return str(video_path)

        if source_type == SourceType.RTSP:
            if source is None or not str(source).strip():
                raise ValueError("An RTSP URL must be provided when source_type is 'rtsp'.")
            return str(source).strip()

        raise ValueError(f"Unhandled source type: {source_type}")

    @property
    def source_type(self) -> str:
        """Return the source type as a string ('webcam', 'video', 'rtsp')."""
        return self._source_type.value

    @property
    def source(self) -> Union[int, str]:
        """Return the configured source identifier or file path."""
        return self._source

    @property
    def is_opened(self) -> bool:
        """Return whether the underlying video stream is active and open."""
        return bool(self._is_opened and self._cap is not None and self._cap.isOpened())

    @property
    def width(self) -> int:
        """Return frame width in pixels."""
        return self._width

    @property
    def height(self) -> int:
        """Return frame height in pixels."""
        return self._height

    @property
    def fps(self) -> float:
        """Return frames per second."""
        return self._fps

    @property
    def frame_count(self) -> Optional[int]:
        """Return total frame count for video files, or None for live streams."""
        return self._frame_count

    @property
    def current_frame_index(self) -> int:
        """Return the number of frames successfully read so far."""
        return self._current_frame_index

    def open(self) -> "VideoSource":
        """Open the video capture source and read initial stream metadata.

        Returns:
            self: The opened VideoSource instance.

        Raises:
            VideoSourceOpenError: If opening the video stream or device fails.
        """
        if self.is_opened:
            return self

        logger.info("Opening %s source: %s", self._source_type.value, self._source)

        try:
            self._cap = cv2.VideoCapture(self._source, self._api_preference)
        except Exception as err:
            raise VideoSourceOpenError(
                f"Failed to initialize VideoCapture for {self._source_type.value} '{self._source}': {err}"
            ) from err

        if not self._cap.isOpened():
            if self._source_type == SourceType.WEBCAM:
                raise VideoSourceOpenError(
                    f"Failed to open webcam device at index {self._source}. "
                    "Ensure the camera is connected, not in use by another application, "
                    "and camera access permissions are enabled."
                )
            if self._source_type == SourceType.VIDEO:
                raise VideoSourceOpenError(
                    f"Failed to open or decode video file: '{self._source}'. "
                    "Verify the file is a valid, uncorrupted video supported by OpenCV."
                )
            if self._source_type == SourceType.RTSP:
                raise VideoSourceOpenError(
                    f"Failed to connect to RTSP stream: '{self._source}'. "
                    "Verify the network connection and stream URL."
                )
            raise VideoSourceOpenError(
                f"Failed to open {self._source_type.value} source '{self._source}'."
            )

        self._is_opened = True
        self._current_frame_index = 0

        # Retrieve video properties
        raw_width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        raw_height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        raw_fps = float(self._cap.get(cv2.CAP_PROP_FPS))
        raw_count = self._cap.get(cv2.CAP_PROP_FRAME_COUNT)

        self._width = raw_width if raw_width > 0 else 0
        self._height = raw_height if raw_height > 0 else 0
        self._fps = raw_fps if raw_fps > 0.0 else 0.0

        if self._source_type == SourceType.VIDEO and raw_count > 0:
            self._frame_count = int(raw_count)
        else:
            self._frame_count = None

        logger.info(
            "Opened %s source [%s]: %dx%d @ %.2f FPS (Total frames: %s)",
            self._source_type.value,
            self._source,
            self._width,
            self._height,
            self._fps,
            self._frame_count if self._frame_count is not None else "live",
        )

        return self

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read the next frame from the video source.

        Guarantees that any successfully returned frame is in 3-channel
        OpenCV BGR format (dtype=uint8, shape=(H, W, 3)).

        Returns:
            Tuple[bool, Optional[np.ndarray]]:
                (True, frame) if a frame was successfully read.
                (False, None) on end-of-file, stream termination, or read failure.
        """
        if not self.is_opened:
            try:
                self.open()
            except VideoSourceOpenError as err:
                logger.error("Auto-open failed during read(): %s", err)
                return False, None

        ret, frame = self._cap.read()

        if not ret or frame is None:
            if self._source_type == SourceType.VIDEO:
                logger.info("Reached end-of-file for video: %s", self._source)
            else:
                logger.warning("Frame read returned False for %s source: %s", self._source_type.value, self._source)
            return False, None

        # Ensure frame is standard 3-channel BGR
        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif frame.ndim == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        elif frame.ndim != 3 or frame.shape[2] != 3:
            logger.error("Encountered unexpected frame shape: %s", frame.shape)
            return False, None

        if frame.dtype != np.uint8:
            frame = frame.astype(np.uint8)

        # Update dimensions from actual frame if not previously populated
        if self._width == 0 or self._height == 0:
            self._height, self._width = frame.shape[:2]

        self._current_frame_index += 1
        return True, frame

    def release(self) -> None:
        """Release the video capture hardware or file resource cleanly."""
        if self._cap is not None:
            logger.info("Releasing %s source: %s", self._source_type.value, self._source)
            try:
                self._cap.release()
            except Exception as err:
                logger.warning("Exception while releasing VideoCapture: %s", err)
            self._cap = None
        self._is_opened = False

    def close(self) -> None:
        """Alias for release()."""
        self.release()

    def get_metadata(self) -> dict:
        """Return a dictionary of metadata describing the video source."""
        return {
            "source_type": self.source_type,
            "source": self.source,
            "is_opened": self.is_opened,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "frame_count": self.frame_count,
            "current_frame_index": self.current_frame_index,
        }

    def __iter__(self) -> Generator[np.ndarray, None, None]:
        """Iterate continuously yielding BGR frames until EOF or release."""
        while self.is_opened:
            ret, frame = self.read()
            if not ret or frame is None:
                break
            yield frame

    def __enter__(self) -> "VideoSource":
        """Context manager entry point."""
        return self.open()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit point releasing resources."""
        self.release()

    def __repr__(self) -> str:
        return (
            f"VideoSource(source_type='{self._source_type.value}', "
            f"source={self._source!r}, is_opened={self.is_opened}, "
            f"resolution=({self._width}x{self._height}), fps={self._fps})"
        )
