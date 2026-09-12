"""Comprehensive tests for Module 11: Evidence Capture.

Covers:
- EvidenceCapture initialization & custom output directory
- Automatic directory creation
- Valid frame capture & JPG file creation
- File existence & non-zero file size
- Image reopening with cv2.imread & integrity validation
- Original frame resolution preservation
- Metadata preservation in EvidenceRecord
- EvidenceRecord immutability (frozen dataclass)
- Serialization via to_dict()
- Unique filenames & collision avoidance
- Multiple alerts captured into separate files
- Repeated capture behavior for identical alerts (no accidental overwrite)
- Input validation: None alert, non-Alert object, None frame, empty frame,
  malformed dimensions, wrong channel count, non-uint8 data
- Source frame immutability (frame not modified in-place)
- Filesystem-safe filenames & special character sanitization
- Path traversal protection (../, ..\\, absolute path tokens)
- Write failure handling & exception propagation
- In-memory querying: get_evidence, list_evidence, get_evidence_by_alert, clear, count
- Deterministic M10 AlertEngine integration test
"""

from dataclasses import FrozenInstanceError
from pathlib import Path
import time
from unittest.mock import patch

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
from ai_engine.evidence import (
    EvidenceCapture,
    EvidenceCaptureError,
    EvidenceError,
    EvidenceRecord,
    EvidenceSecurityError,
    EvidenceValidationError,
    sanitize_filename_component,
)


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_alert() -> Alert:
    """Return a deterministic M10 Alert instance."""
    return Alert(
        alert_id="ALT-00001",
        track_id=42,
        alert_type=AlertType.FENCE_BREACH,
        severity=AlertSeverity.CRITICAL,
        status=AlertStatus.ACTIVE,
        timestamp=1726138500.0,
        camera_id="CAM_NORTH_01",
        zone_id="ZONE_PERIMETER",
        zone_name="North Fence Line",
        zone_type="RESTRICTED",
        center=(320.0, 240.0),
        message="Fence breach detected by target 42",
    )


@pytest.fixture
def sample_frame() -> np.ndarray:
    """Return a valid synthetic 640x480 3-channel BGR image."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Add some color gradients and shapes for realistic non-empty pixels
    cv2.rectangle(frame, (100, 100), (300, 300), (0, 255, 0), -1)
    cv2.circle(frame, (400, 250), 50, (0, 0, 255), -1)
    return frame


@pytest.fixture
def evidence_capture(tmp_path: Path) -> EvidenceCapture:
    """Return an EvidenceCapture instance bound to a temporary directory."""
    return EvidenceCapture(output_dir=tmp_path / "evidence_test")


# ---------------------------------------------------------------------------
# Initialization & Directory Creation Tests
# ---------------------------------------------------------------------------

class TestEvidenceCaptureInit:
    """Tests for EvidenceCapture initialization and directory handling."""

    def test_default_initialization(self, tmp_path: Path):
        """Verify default initialization creates the target directory."""
        target_dir = tmp_path / "default_evidence"
        assert not target_dir.exists()

        capture_engine = EvidenceCapture(output_dir=target_dir)
        assert target_dir.exists()
        assert target_dir.is_dir()
        assert capture_engine.output_dir == target_dir.resolve()
        assert capture_engine.jpeg_quality == 95
        assert capture_engine.count == 0

    def test_custom_jpeg_quality(self, tmp_path: Path):
        """Verify custom jpeg_quality setting."""
        capture_engine = EvidenceCapture(output_dir=tmp_path, jpeg_quality=80)
        assert capture_engine.jpeg_quality == 80

    def test_invalid_jpeg_quality_raises(self, tmp_path: Path):
        """Verify invalid jpeg_quality raises EvidenceValidationError."""
        with pytest.raises(EvidenceValidationError, match="jpeg_quality"):
            EvidenceCapture(output_dir=tmp_path, jpeg_quality=0)

        with pytest.raises(EvidenceValidationError, match="jpeg_quality"):
            EvidenceCapture(output_dir=tmp_path, jpeg_quality=101)


# ---------------------------------------------------------------------------
# Capture & File Integrity Tests
# ---------------------------------------------------------------------------

class TestEvidenceCaptureExecution:
    """Tests for the capture() workflow, file verification, and integrity."""

    def test_valid_frame_capture_creates_jpg(
        self,
        evidence_capture: EvidenceCapture,
        sample_alert: Alert,
        sample_frame: np.ndarray,
    ):
        """Verify successful capture creates a valid JPG file on disk."""
        record = evidence_capture.capture(sample_alert, sample_frame)

        assert isinstance(record, EvidenceRecord)
        assert record.evidence_id == "EVD-00001"
        assert record.alert_id == sample_alert.alert_id
        assert record.track_id == 42
        assert record.camera_id == "CAM_NORTH_01"
        assert record.alert_type == "FENCE_BREACH"
        assert record.severity == "CRITICAL"
        assert record.timestamp == 1726138500.0
        assert record.filename.endswith(".jpg")
        assert record.frame_dimensions == (640, 480)
        assert record.width == 640
        assert record.height == 480

        # Verify file exists on disk and is non-empty
        file_path = Path(record.file_path)
        assert file_path.exists()
        assert file_path.is_file()
        assert file_path.stat().st_size > 0

    def test_saved_image_can_be_reopened_and_matches_dimensions(
        self,
        evidence_capture: EvidenceCapture,
        sample_alert: Alert,
        sample_frame: np.ndarray,
    ):
        """Verify saved image is a readable, uncorrupted JPEG matching original dimensions."""
        record = evidence_capture.capture(sample_alert, sample_frame)

        # Reopen with cv2.imread
        decoded = cv2.imread(record.file_path)
        assert decoded is not None
        assert isinstance(decoded, np.ndarray)
        assert decoded.shape == sample_frame.shape
        assert decoded.shape == (480, 640, 3)

    def test_original_resolution_preserved(
        self,
        evidence_capture: EvidenceCapture,
        sample_alert: Alert,
    ):
        """Verify original non-standard resolution is preserved without auto-resizing."""
        custom_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        record = evidence_capture.capture(sample_alert, custom_frame)

        assert record.frame_dimensions == (1280, 720)
        assert record.width == 1280
        assert record.height == 720

        decoded = cv2.imread(record.file_path)
        assert decoded is not None
        assert decoded.shape == (720, 1280, 3)

    def test_source_frame_immutability(
        self,
        evidence_capture: EvidenceCapture,
        sample_alert: Alert,
        sample_frame: np.ndarray,
    ):
        """Verify capture() does not modify the source frame in-place."""
        frame_copy = sample_frame.copy()

        evidence_capture.capture(sample_alert, sample_frame)

        assert np.array_equal(sample_frame, frame_copy)


# ---------------------------------------------------------------------------
# Multiple Captures & Collision Avoidance Tests
# ---------------------------------------------------------------------------

class TestCollisionAndMultipleCaptures:
    """Tests for handling multiple alerts and collision-safe repeated captures."""

    def test_multiple_different_alerts_create_separate_files(
        self,
        evidence_capture: EvidenceCapture,
        sample_alert: Alert,
        sample_frame: np.ndarray,
    ):
        """Verify different alerts produce distinct files and distinct records."""
        alert1 = sample_alert
        alert2 = Alert(
            alert_id="ALT-00002",
            track_id=99,
            alert_type=AlertType.LOITERING,
            severity=AlertSeverity.HIGH,
            status=AlertStatus.ACTIVE,
            timestamp=1726138600.0,
            camera_id="CAM_SOUTH_02",
        )

        rec1 = evidence_capture.capture(alert1, sample_frame)
        rec2 = evidence_capture.capture(alert2, sample_frame)

        assert rec1.evidence_id != rec2.evidence_id
        assert rec1.filename != rec2.filename
        assert rec1.file_path != rec2.file_path
        assert Path(rec1.file_path).exists()
        assert Path(rec2.file_path).exists()
        assert evidence_capture.count == 2

    def test_repeated_capture_same_alert_does_not_overwrite(
        self,
        evidence_capture: EvidenceCapture,
        sample_alert: Alert,
        sample_frame: np.ndarray,
    ):
        """Verify capturing the same alert again creates a unique file and record."""
        rec1 = evidence_capture.capture(sample_alert, sample_frame)
        rec2 = evidence_capture.capture(sample_alert, sample_frame)

        assert rec1.evidence_id != rec2.evidence_id
        assert rec1.filename != rec2.filename
        assert rec1.file_path != rec2.file_path
        assert Path(rec1.file_path).exists()
        assert Path(rec2.file_path).exists()
        assert evidence_capture.count == 2

        # Verify querying by alert returns both records
        records_for_alert = evidence_capture.get_evidence_by_alert(sample_alert.alert_id)
        assert len(records_for_alert) == 2
        assert records_for_alert[0].evidence_id == rec1.evidence_id
        assert records_for_alert[1].evidence_id == rec2.evidence_id

    def test_file_collision_suffix_handling(
        self,
        evidence_capture: EvidenceCapture,
        sample_alert: Alert,
        sample_frame: np.ndarray,
    ):
        """Verify that if a filename already exists, a collision suffix is cleanly appended."""
        # Pre-create a dummy file at the expected base path
        rec1 = evidence_capture.capture(sample_alert, sample_frame)
        path1 = Path(rec1.file_path)
        assert path1.exists()

        # If we manually mock counter and timestamp collision
        with patch("ai_engine.evidence.time.time", return_value=rec1.capture_timestamp):
            # Temporarily rewind counter to test collision resolution logic
            evidence_capture._counter = 0
            rec2 = evidence_capture.capture(sample_alert, sample_frame)

        assert rec2.filename != rec1.filename
        assert Path(rec2.file_path).exists()
        assert Path(rec1.file_path).exists()


# ---------------------------------------------------------------------------
# Input Validation Tests
# ---------------------------------------------------------------------------

class TestEvidenceValidation:
    """Tests for rejecting malformed inputs with domain exceptions."""

    def test_reject_none_alert(
        self,
        evidence_capture: EvidenceCapture,
        sample_frame: np.ndarray,
    ):
        """Verify None alert is rejected."""
        with pytest.raises(EvidenceValidationError, match="Alert cannot be None"):
            evidence_capture.capture(None, sample_frame)  # type: ignore

    def test_reject_invalid_alert_type(
        self,
        evidence_capture: EvidenceCapture,
        sample_frame: np.ndarray,
    ):
        """Verify non-Alert object is rejected."""
        with pytest.raises(EvidenceValidationError, match="Expected Alert instance"):
            evidence_capture.capture({"alert_id": "ALT-01"}, sample_frame)  # type: ignore

        with pytest.raises(EvidenceValidationError, match="Expected Alert instance"):
            evidence_capture.capture("not_an_alert", sample_frame)  # type: ignore

    def test_reject_none_frame(
        self,
        evidence_capture: EvidenceCapture,
        sample_alert: Alert,
    ):
        """Verify None frame is rejected."""
        with pytest.raises(EvidenceValidationError, match="Frame cannot be None"):
            evidence_capture.capture(sample_alert, None)  # type: ignore

    def test_reject_non_ndarray_frame(
        self,
        evidence_capture: EvidenceCapture,
        sample_alert: Alert,
    ):
        """Verify non-ndarray frame is rejected."""
        with pytest.raises(EvidenceValidationError, match="Frame must be a numpy.ndarray"):
            evidence_capture.capture(sample_alert, [[1, 2], [3, 4]])  # type: ignore

    def test_reject_empty_frame(
        self,
        evidence_capture: EvidenceCapture,
        sample_alert: Alert,
    ):
        """Verify empty ndarray is rejected."""
        empty_frame = np.empty((0, 0, 3), dtype=np.uint8)
        with pytest.raises(EvidenceValidationError, match="empty"):
            evidence_capture.capture(sample_alert, empty_frame)

        zero_dim_frame = np.empty((480, 0, 3), dtype=np.uint8)
        with pytest.raises(EvidenceValidationError, match="empty|invalid dimensions"):
            evidence_capture.capture(sample_alert, zero_dim_frame)

    def test_reject_unsupported_dimensions(
        self,
        evidence_capture: EvidenceCapture,
        sample_alert: Alert,
    ):
        """Verify frames with wrong ndim or channel count are rejected."""
        # 2D grayscale image
        gray_frame = np.zeros((480, 640), dtype=np.uint8)
        with pytest.raises(EvidenceValidationError, match="Unsupported frame dimensionality"):
            evidence_capture.capture(sample_alert, gray_frame)

        # 4-channel BGRA image
        bgra_frame = np.zeros((480, 640, 4), dtype=np.uint8)
        with pytest.raises(EvidenceValidationError, match="Unsupported frame dimensionality"):
            evidence_capture.capture(sample_alert, bgra_frame)

        # 1-channel 3D image
        single_channel = np.zeros((480, 640, 1), dtype=np.uint8)
        with pytest.raises(EvidenceValidationError, match="Unsupported frame dimensionality"):
            evidence_capture.capture(sample_alert, single_channel)

    def test_reject_non_uint8_dtype(
        self,
        evidence_capture: EvidenceCapture,
        sample_alert: Alert,
    ):
        """Verify non-uint8 arrays (e.g. float32, int32) are rejected."""
        float_frame = np.zeros((480, 640, 3), dtype=np.float32)
        with pytest.raises(EvidenceValidationError, match="Unsupported frame data type.*np.uint8"):
            evidence_capture.capture(sample_alert, float_frame)

        int_frame = np.zeros((480, 640, 3), dtype=np.int32)
        with pytest.raises(EvidenceValidationError, match="Unsupported frame data type.*np.uint8"):
            evidence_capture.capture(sample_alert, int_frame)


# ---------------------------------------------------------------------------
# Security & Path Traversal Tests
# ---------------------------------------------------------------------------

class TestEvidenceSecurityAndPathSafety:
    """Tests for path traversal prevention and filesystem-safe filenames."""

    def test_path_traversal_in_alert_id_rejected(
        self,
        evidence_capture: EvidenceCapture,
        sample_frame: np.ndarray,
    ):
        """Verify path traversal patterns in alert_id raise EvidenceSecurityError."""
        traversal_alert = Alert(
            alert_id="../../malicious_escape",
            track_id=1,
            alert_type=AlertType.FENCE_BREACH,
            severity=AlertSeverity.CRITICAL,
        )

        with pytest.raises(EvidenceSecurityError, match="Path traversal sequence detected"):
            evidence_capture.capture(traversal_alert, sample_frame)

    def test_path_traversal_with_leading_slashes_rejected(
        self,
        evidence_capture: EvidenceCapture,
        sample_frame: np.ndarray,
    ):
        """Verify absolute path attempts in alert_id are rejected."""
        abs_alert = Alert(
            alert_id="/etc/passwd",
            track_id=1,
            alert_type=AlertType.FENCE_BREACH,
            severity=AlertSeverity.CRITICAL,
        )

        with pytest.raises(EvidenceSecurityError, match="Path traversal sequence detected"):
            evidence_capture.capture(abs_alert, sample_frame)

    def test_path_traversal_in_camera_id_rejected(
        self,
        evidence_capture: EvidenceCapture,
        sample_frame: np.ndarray,
    ):
        """Verify path traversal patterns in camera_id raise EvidenceSecurityError."""
        traversal_cam_alert = Alert(
            alert_id="ALT-100",
            track_id=1,
            alert_type=AlertType.FENCE_BREACH,
            severity=AlertSeverity.CRITICAL,
            camera_id="../escape_cam",
        )

        with pytest.raises(EvidenceSecurityError, match="Path traversal sequence detected in camera_id"):
            evidence_capture.capture(traversal_cam_alert, sample_frame)

    def test_sanitize_filename_component_replaces_illegal_characters(self):
        """Verify sanitization helper cleans forbidden filesystem characters."""
        dirty_id = 'ALERT:001/SUB\\TEST*NAME?"<BAR>|'
        clean = sanitize_filename_component(dirty_id)
        for char in '/\\:*?"<>|':
            assert char not in clean

        assert sanitize_filename_component(None) == "unknown"
        assert sanitize_filename_component("   ") == "unknown"
        assert sanitize_filename_component("..") == "unknown"


# ---------------------------------------------------------------------------
# Write Failure Handling Tests
# ---------------------------------------------------------------------------

class TestEvidenceWriteFailures:
    """Tests for handling disk write and OpenCV imwrite failures."""

    def test_cv2_imwrite_failure_raises_evidence_capture_error(
        self,
        evidence_capture: EvidenceCapture,
        sample_alert: Alert,
        sample_frame: np.ndarray,
    ):
        """Verify that cv2.imwrite returning False raises EvidenceCaptureError."""
        with patch("cv2.imwrite", return_value=False):
            with pytest.raises(EvidenceCaptureError, match="cv2.imwrite returned False"):
                evidence_capture.capture(sample_alert, sample_frame)

    def test_cv2_imwrite_exception_raises_evidence_capture_error(
        self,
        evidence_capture: EvidenceCapture,
        sample_alert: Alert,
        sample_frame: np.ndarray,
    ):
        """Verify that cv2.imwrite throwing an OS/IO error raises EvidenceCaptureError."""
        with patch("cv2.imwrite", side_effect=OSError("Disk write permission denied")):
            with pytest.raises(EvidenceCaptureError, match="Exception writing evidence image"):
                evidence_capture.capture(sample_alert, sample_frame)


# ---------------------------------------------------------------------------
# EvidenceRecord & Query Method Tests
# ---------------------------------------------------------------------------

class TestEvidenceRecordAndQueries:
    """Tests for EvidenceRecord immutability, serialization, and session queries."""

    def test_evidence_record_immutability(
        self,
        evidence_capture: EvidenceCapture,
        sample_alert: Alert,
        sample_frame: np.ndarray,
    ):
        """Verify EvidenceRecord is frozen and raises on attribute modification."""
        record = evidence_capture.capture(sample_alert, sample_frame)

        with pytest.raises(FrozenInstanceError):
            record.evidence_id = "NEW-ID"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            record.alert_id = "NEW-ALERT"  # type: ignore

    def test_evidence_record_to_dict(
        self,
        evidence_capture: EvidenceCapture,
        sample_alert: Alert,
        sample_frame: np.ndarray,
    ):
        """Verify to_dict returns a complete, serializable dictionary."""
        record = evidence_capture.capture(sample_alert, sample_frame)
        d = record.to_dict()

        assert isinstance(d, dict)
        assert d["evidence_id"] == record.evidence_id
        assert d["alert_id"] == "ALT-00001"
        assert d["track_id"] == 42
        assert d["camera_id"] == "CAM_NORTH_01"
        assert d["alert_type"] == "FENCE_BREACH"
        assert d["severity"] == "CRITICAL"
        assert d["file_path"] == record.file_path
        assert d["filename"] == record.filename
        assert d["frame_dimensions"] == [640, 480]
        assert d["width"] == 640
        assert d["height"] == 480
        assert isinstance(d["capture_timestamp"], float)

    def test_query_methods_and_clear(
        self,
        evidence_capture: EvidenceCapture,
        sample_alert: Alert,
        sample_frame: np.ndarray,
    ):
        """Verify get_evidence, list_evidence, and clear."""
        rec1 = evidence_capture.capture(sample_alert, sample_frame)

        # Retrieve by evidence ID
        retrieved = evidence_capture.get_evidence(rec1.evidence_id)
        assert retrieved == rec1

        # Non-existent ID returns None
        assert evidence_capture.get_evidence("NON_EXISTENT") is None

        # List evidence
        all_records = evidence_capture.list_evidence()
        assert len(all_records) == 1
        assert all_records[0] == rec1

        # Clear in-memory session records
        evidence_capture.clear()
        assert evidence_capture.count == 0
        assert evidence_capture.get_evidence(rec1.evidence_id) is None
        # Verify file itself still persists on disk
        assert Path(rec1.file_path).exists()


# ---------------------------------------------------------------------------
# M10 Alert Engine End-to-End Integration Test
# ---------------------------------------------------------------------------

class TestM10AlertEngineIntegration:
    """Deterministic end-to-end integration test connecting M10 and M11."""

    def test_alert_engine_to_evidence_capture_pipeline(
        self,
        tmp_path: Path,
        sample_frame: np.ndarray,
    ):
        """Verify end-to-end flow: M10 AlertEngine -> Alert -> EvidenceCapture -> JPG -> EvidenceRecord."""
        # 1. Initialize M10 AlertEngine
        alert_engine = AlertEngine(default_camera_id="CAM_PERIMETER_01")

        # 2. Trigger synthetic fence breach event in AlertEngine
        from ai_engine.fence_breach import BreachEventType, FenceBreachEvent, FenceState

        fence_event = FenceBreachEvent(
            track_id=88,
            event_type=BreachEventType.FENCE_BREACH,
            previous_state=FenceState.OUTSIDE,
            current_state=FenceState.INSIDE,
            frame_id=45,
            timestamp=1726139000.0,
            center=(320.0, 240.0),
            fence_id="FENCE_ALPHA",
            zone_id="ZONE_RESTRICTED",
            breach_count=1,
            metadata={"zone_name": "Perimeter Wall", "zone_type": "RESTRICTED"},
        )
        alert = alert_engine.process_fence_breach(fence_event)
        assert alert is not None
        assert isinstance(alert, Alert)
        assert alert.alert_type == AlertType.FENCE_BREACH
        assert alert.severity == AlertSeverity.CRITICAL

        # 3. Initialize M11 EvidenceCapture
        evidence_capture = EvidenceCapture(output_dir=tmp_path / "integration_evidence")

        # 4. Capture evidence frame for the M10 alert
        evidence_record = evidence_capture.capture(alert, sample_frame)

        # 5. Validate EvidenceRecord and disk output
        assert evidence_record.alert_id == alert.alert_id
        assert evidence_record.track_id == 88
        assert evidence_record.camera_id == "CAM_PERIMETER_01"
        assert evidence_record.alert_type == "FENCE_BREACH"
        assert evidence_record.severity == "CRITICAL"

        evidence_file = Path(evidence_record.file_path)
        assert evidence_file.exists()
        assert evidence_file.suffix == ".jpg"

        # 6. Reopen saved JPG and verify integrity
        reopened = cv2.imread(str(evidence_file))
        assert reopened is not None
        assert reopened.shape == sample_frame.shape
