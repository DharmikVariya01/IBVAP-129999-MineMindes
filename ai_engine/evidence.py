"""Evidence Capture Module for IBVAP AI Engine.

Module 11: Standalone Security Alert Evidence Frame Capture.

Sits downstream of Module 10 (AlertEngine) in the video analytics pipeline:

    VideoSource (M1)
        -> FramePreprocessor (M2)
        -> YOLODetector (M3)
        -> ByteTrackTracker (M4)
        -> EventMemory (M5)
        -> MovementAnalyzer (M6)
        -> ZoneManager (M7)
        -> FenceBreachDetector (M8)
        -> LoiteringDetector (M9)
        -> AlertEngine (M10)
        -> EvidenceCapture (M11)  <- this module
        -> JPG evidence file

Objective:
    Capture and save the exact video frame associated with an M10 security Alert
    as a high-fidelity JPG evidence image. Maintain an immutable, serializable
    EvidenceRecord linking the saved image directly to the originating alert,
    track ID, camera, timestamp, and frame dimensions.

Key Design Principles:
- Single Responsibility: Only responsible for capturing, validating, saving,
  and cataloging evidence frames. Does not generate alerts or alter alert states.
- Immutability: EvidenceRecord is a frozen dataclass with full metadata.
- Non-destructive: Source video frame is never mutated or resized.
- Collision Safety: Every capture generates a unique, deterministic-safe filename
  and unique evidence record even across repeated captures of the same alert.
- Filesystem & Path Security: Sanitizes all alert metadata components and strictly
  enforces directory containment, preventing path traversal attacks (e.g. '../', '..\\').
- Strict Validation: Rejects invalid/None alerts, None frames, empty frames,
  unsupported dimensions, and non-uint8 data with clear domain exceptions.
- Zero External DB/API: Self-contained, lightweight, and database-independent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import logging
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

import cv2
import numpy as np

from ai_engine.alerts import Alert, AlertSeverity, AlertType

logger = logging.getLogger("ibvap.ai_engine.evidence")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class EvidenceError(Exception):
    """Base exception for all evidence capture errors."""
    pass


class EvidenceValidationError(EvidenceError):
    """Raised when an alert, frame, or parameter fails validation."""
    pass


class EvidenceCaptureError(EvidenceError):
    """Raised when saving or verifying an evidence image fails."""
    pass


class EvidenceSecurityError(EvidenceValidationError):
    """Raised when an identifier or path contains illegal path traversal sequences."""
    pass


# ---------------------------------------------------------------------------
# Data Model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceRecord:
    """Immutable record representing a saved evidence frame.

    Attributes:
        evidence_id: Unique identifier for this capture (e.g. 'EVD-00001').
        alert_id: Identifier of the associated M10 alert (e.g. 'ALT-00001').
        track_id: Persistent tracking ID of the suspect target.
        camera_id: Identifier of the source camera, if known.
        alert_type: Type of the security alert (e.g. 'FENCE_BREACH', 'LOITERING').
        severity: Severity level of the alert (e.g. 'CRITICAL', 'HIGH').
        timestamp: Time of the original alert detection.
        file_path: Absolute filesystem path to the saved JPG image.
        filename: Base filename of the evidence image.
        frame_dimensions: Dimensions of the saved frame as (width, height).
        capture_timestamp: Epoch timestamp when the evidence was captured.
    """

    evidence_id: str
    alert_id: str
    track_id: int
    camera_id: Optional[str]
    alert_type: str
    severity: str
    timestamp: float
    file_path: str
    filename: str
    frame_dimensions: Tuple[int, int]  # (width, height)
    capture_timestamp: float = field(default_factory=time.time)

    @property
    def width(self) -> int:
        """Return the horizontal resolution in pixels."""
        return self.frame_dimensions[0]

    @property
    def height(self) -> int:
        """Return the vertical resolution in pixels."""
        return self.frame_dimensions[1]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize evidence record to a JSON-compatible dictionary."""
        return {
            "evidence_id": self.evidence_id,
            "alert_id": self.alert_id,
            "track_id": self.track_id,
            "camera_id": self.camera_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "timestamp": self.timestamp,
            "file_path": self.file_path,
            "filename": self.filename,
            "frame_dimensions": list(self.frame_dimensions),
            "width": self.width,
            "height": self.height,
            "capture_timestamp": self.capture_timestamp,
        }


# ---------------------------------------------------------------------------
# Path & Filename Sanitization Helper
# ---------------------------------------------------------------------------

def sanitize_filename_component(text: Any) -> str:
    """Sanitize arbitrary text into a safe filesystem filename component.

    Strips or replaces path separators ('/', '\\'), forbidden characters,
    leading/trailing dots, and whitespace to prevent path traversal or
    corrupted filesystem paths.
    """
    if text is None:
        return "unknown"
    s = str(text).strip()
    if not s:
        return "unknown"
    # Replace dangerous characters (Windows/Linux forbidden chars)
    s = re.sub(r'[/\\:*?"<>|]', '_', s)
    # Collapse multiple consecutive underscores
    s = re.sub(r'_+', '_', s)
    # Strip leading/trailing dots and whitespace
    s = s.strip('. ')
    return s or "unknown"


# ---------------------------------------------------------------------------
# EvidenceCapture Engine
# ---------------------------------------------------------------------------

class EvidenceCapture:
    """Evidence capture engine for saving security alert video frames as JPG images.

    Accepts an M10 Alert and corresponding OpenCV BGR video frame, validates inputs,
    generates collision-free filenames, writes the JPG to disk, verifies write integrity,
    and returns an immutable EvidenceRecord.
    """

    DEFAULT_OUTPUT_DIR = Path("evidence")

    def __init__(
        self,
        output_dir: Union[str, Path] = DEFAULT_OUTPUT_DIR,
        jpeg_quality: int = 95,
    ) -> None:
        """Initialize EvidenceCapture with a configurable output directory.

        Args:
            output_dir: Destination directory where evidence images are saved.
                Defaults to 'evidence/'. Automatically created if missing.
            jpeg_quality: JPEG compression quality (1-100). Default is 95.

        Raises:
            EvidenceValidationError: If jpeg_quality is out of range.
            EvidenceCaptureError: If output_dir cannot be created.
        """
        if not (1 <= jpeg_quality <= 100):
            raise EvidenceValidationError(
                f"jpeg_quality must be between 1 and 100, got {jpeg_quality}"
            )

        self._output_dir = Path(output_dir).resolve()
        self._jpeg_quality = jpeg_quality
        self._counter: int = 0
        self._records: Dict[str, EvidenceRecord] = {}

        # Ensure evidence directory exists
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise EvidenceCaptureError(
                f"Failed to create evidence directory {self._output_dir}: {e}"
            ) from e

        logger.info(
            "EvidenceCapture initialized. Output directory: %s (quality: %d)",
            self._output_dir,
            self._jpeg_quality,
        )

    @property
    def output_dir(self) -> Path:
        """Return the resolved output directory path."""
        return self._output_dir

    @property
    def jpeg_quality(self) -> int:
        """Return the configured JPEG compression quality."""
        return self._jpeg_quality

    @property
    def count(self) -> int:
        """Return the count of captured evidence records in this session."""
        return len(self._records)

    def capture(
        self,
        alert: Alert,
        frame: np.ndarray,
    ) -> EvidenceRecord:
        """Capture and save an evidence image for a security Alert.

        Args:
            alert: Valid M10 Alert instance.
            frame: Valid OpenCV BGR video frame (H, W, 3) with np.uint8 dtype.

        Returns:
            Immutable EvidenceRecord with metadata and file path.

        Raises:
            EvidenceValidationError: If alert or frame is invalid/empty/malformed.
            EvidenceSecurityError: If alert metadata attempts path traversal.
            EvidenceCaptureError: If saving the image to disk fails or verification fails.
        """
        # 1. Validate inputs
        self._validate_alert(alert)
        self._validate_frame(frame)

        # 2. Extract alert metadata
        alert_id_str = str(alert.alert_id)
        clean_alert_id = sanitize_filename_component(alert_id_str)
        clean_track_id = int(alert.track_id)
        capture_time = time.time()

        # 3. Generate unique sequential ID & collision-safe filename
        self._counter += 1
        evidence_id = f"EVD-{self._counter:05d}"

        dt = datetime.fromtimestamp(capture_time)
        date_str = dt.strftime("%Y%m%d_%H%M%S")

        # Filename pattern: ALERT-ID_TRACK-ID_YYYYMMDD_HHMMSS_EVD-ID.jpg
        base_filename = f"{clean_alert_id}_TRACK-{clean_track_id}_{date_str}_{evidence_id}.jpg"
        target_path = self._output_dir / base_filename

        # Collision avoidance: If a file with this name already exists, append counter suffix
        collision_idx = 1
        while target_path.exists():
            collision_filename = (
                f"{clean_alert_id}_TRACK-{clean_track_id}_{date_str}_{evidence_id}_{collision_idx}.jpg"
            )
            target_path = self._output_dir / collision_filename
            collision_idx += 1

        # 4. Strict directory containment safety check
        try:
            resolved_file = target_path.resolve()
            if not resolved_file.is_relative_to(self._output_dir):
                raise EvidenceSecurityError(
                    f"Target path {resolved_file} escapes evidence directory {self._output_dir}"
                )
        except (ValueError, RuntimeError) as e:
            raise EvidenceSecurityError(f"Security validation failed for path {target_path}: {e}") from e

        # 5. Save frame to disk without mutating input frame
        height, width = frame.shape[:2]
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality]

        try:
            success = cv2.imwrite(str(target_path), frame, encode_params)
        except Exception as e:
            raise EvidenceCaptureError(
                f"Exception writing evidence image to {target_path}: {e}"
            ) from e

        if not success:
            raise EvidenceCaptureError(
                f"cv2.imwrite returned False for destination: {target_path}"
            )

        # 6. Verify file existence and non-zero size
        if not target_path.exists() or target_path.stat().st_size == 0:
            raise EvidenceCaptureError(
                f"Evidence file was not successfully created or is 0 bytes: {target_path}"
            )

        # 7. Construct immutable EvidenceRecord
        alert_type_val = (
            alert.alert_type.value
            if hasattr(alert.alert_type, "value")
            else str(alert.alert_type)
        )
        severity_val = (
            alert.severity.value
            if hasattr(alert.severity, "value")
            else str(alert.severity)
        )

        record = EvidenceRecord(
            evidence_id=evidence_id,
            alert_id=alert.alert_id,
            track_id=int(alert.track_id),
            camera_id=alert.camera_id,
            alert_type=alert_type_val,
            severity=severity_val,
            timestamp=float(alert.timestamp),
            file_path=str(target_path),
            filename=target_path.name,
            frame_dimensions=(width, height),
            capture_timestamp=capture_time,
        )

        self._records[evidence_id] = record
        logger.debug("Captured evidence %s -> %s", evidence_id, target_path.name)
        return record

    def get_evidence(self, evidence_id: str) -> Optional[EvidenceRecord]:
        """Retrieve a captured EvidenceRecord by its ID."""
        return self._records.get(evidence_id)

    def list_evidence(self) -> List[EvidenceRecord]:
        """Return a list of all EvidenceRecords captured in this session."""
        return list(self._records.values())

    def get_evidence_by_alert(self, alert_id: str) -> List[EvidenceRecord]:
        """Return all EvidenceRecords associated with a given alert ID."""
        return [rec for rec in self._records.values() if rec.alert_id == alert_id]

    def clear(self) -> None:
        """Clear in-memory evidence records (does not delete saved image files)."""
        self._records.clear()

    # -----------------------------------------------------------------------
    # Internal Validation Helpers
    # -----------------------------------------------------------------------

    def _validate_alert(self, alert: Any) -> None:
        """Validate alert object and check for path traversal patterns."""
        if alert is None:
            raise EvidenceValidationError("Alert cannot be None")

        if not isinstance(alert, Alert):
            raise EvidenceValidationError(
                f"Expected Alert instance, got {type(alert).__name__}"
            )

        # Path traversal guard in alert_id or camera_id
        alert_id_str = str(alert.alert_id)
        if ".." in alert_id_str or alert_id_str.startswith(("/", "\\")):
            raise EvidenceSecurityError(
                f"Path traversal sequence detected in alert_id: {alert_id_str}"
            )

        if alert.camera_id is not None:
            cam_str = str(alert.camera_id)
            if ".." in cam_str or cam_str.startswith(("/", "\\")):
                raise EvidenceSecurityError(
                    f"Path traversal sequence detected in camera_id: {cam_str}"
                )

    def _validate_frame(self, frame: Any) -> None:
        """Validate OpenCV video frame."""
        if frame is None:
            raise EvidenceValidationError("Frame cannot be None")

        if not isinstance(frame, np.ndarray):
            raise EvidenceValidationError(
                f"Frame must be a numpy.ndarray, got {type(frame).__name__}"
            )

        if frame.size == 0:
            raise EvidenceValidationError("Frame is empty (size is 0)")

        if frame.ndim != 3 or frame.shape[2] != 3:
            raise EvidenceValidationError(
                f"Unsupported frame dimensionality: expected 3-channel BGR image (H, W, 3), "
                f"got shape {frame.shape}"
            )

        if frame.shape[0] == 0 or frame.shape[1] == 0:
            raise EvidenceValidationError(
                f"Frame has invalid dimensions: {frame.shape}"
            )

        if frame.dtype != np.uint8:
            raise EvidenceValidationError(
                f"Unsupported frame data type: expected np.uint8, got {frame.dtype}"
            )
