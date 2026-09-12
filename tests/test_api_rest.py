"""Comprehensive REST API test suite for IBVAP Module 16.

Tests all M16 endpoints under /api/v1:
1. Cameras (list, pagination, filtering, get existing, 404, validation)
2. Alerts (list, pagination, multi-field filtering, get existing, 404, PATCH lifecycle transitions, 400 invalid transitions)
3. Tracks (get existing with associated event/alert counts, get by surrogate id, 404)
4. Events (chronological events for track, track with no events, missing track 404)
5. Evidence (metadata retrieval, 404, safe file streaming with FileResponse, missing file 404, path traversal prevention 403)
6. Statistics (pure database aggregations on empty and populated DB, status/severity breakdowns)
7. OpenAPI and Cross-Cutting error formatting.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure backend and project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models import (
    Alert,
    AlertSeverity,
    AlertStatus,
    AlertType,
    Base,
    Camera,
    CameraSourceType,
    CameraStatus,
    Event,
    EventType,
    Evidence,
    Track,
    TrackStatus,
    utc_now,
)


# ==============================================================================
# Isolated In-Memory Test Database Fixtures
# ==============================================================================


@pytest.fixture
def test_db_session():
    """Provide an isolated, transactional in-memory database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(test_db_session: Session):
    """Provide a TestClient with get_db dependency overridden to test_db_session."""
    def override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


# ==============================================================================
# 1. CAMERA API TESTS
# ==============================================================================


class TestCameraEndpoints:
    """Test suite for /api/v1/cameras endpoints."""

    def test_list_cameras_empty(self, client: TestClient):
        """GET /cameras returns 200 and empty list when no cameras exist."""
        resp = client.get("/api/v1/cameras")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert data["total_pages"] == 0

    def test_list_cameras_populated_and_pagination(
        self, client: TestClient, test_db_session: Session
    ):
        """GET /cameras correctly paginates results."""
        for i in range(1, 11):
            cam = Camera(
                camera_id=f"CAM-{i:02d}",
                name=f"Camera {i}",
                source_type=CameraSourceType.RTSP if i % 2 == 0 else CameraSourceType.VIDEO,
                source_reference=f"rtsp://192.168.1.{i}/live",
                location="Perimeter North" if i <= 5 else "Perimeter South",
                status=CameraStatus.ONLINE if i <= 8 else CameraStatus.OFFLINE,
            )
            test_db_session.add(cam)
        test_db_session.commit()

        # Page 1, size 4
        resp = client.get("/api/v1/cameras?page=1&page_size=4")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 10
        assert data["page"] == 1
        assert data["page_size"] == 4
        assert data["total_pages"] == 3
        assert len(data["items"]) == 4
        assert data["items"][0]["camera_id"] == "CAM-01"

        # Page 3, size 4 (remaining 2)
        resp2 = client.get("/api/v1/cameras?page=3&page_size=4")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["items"]) == 2
        assert data2["items"][0]["camera_id"] == "CAM-09"

    def test_list_cameras_filter_by_status(
        self, client: TestClient, test_db_session: Session
    ):
        """GET /cameras filters accurately by status."""
        test_db_session.add(
            Camera(
                camera_id="CAM-ON",
                name="Online Cam",
                source_type=CameraSourceType.VIDEO,
                source_reference="video.mp4",
                status=CameraStatus.ONLINE,
            )
        )
        test_db_session.add(
            Camera(
                camera_id="CAM-OFF",
                name="Offline Cam",
                source_type=CameraSourceType.VIDEO,
                source_reference="video.mp4",
                status=CameraStatus.OFFLINE,
            )
        )
        test_db_session.commit()

        resp = client.get("/api/v1/cameras?status=OFFLINE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["camera_id"] == "CAM-OFF"
        assert data["items"][0]["status"] == "OFFLINE"

    def test_list_cameras_filter_by_source_type(
        self, client: TestClient, test_db_session: Session
    ):
        """GET /cameras filters accurately by source_type."""
        test_db_session.add(
            Camera(
                camera_id="CAM-RTSP",
                name="RTSP Cam",
                source_type=CameraSourceType.RTSP,
                source_reference="rtsp://stream",
                status=CameraStatus.ONLINE,
            )
        )
        test_db_session.add(
            Camera(
                camera_id="CAM-WEBCAM",
                name="Webcam",
                source_type=CameraSourceType.WEBCAM,
                source_reference="0",
                status=CameraStatus.ONLINE,
            )
        )
        test_db_session.commit()

        resp = client.get("/api/v1/cameras?source_type=webcam")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["camera_id"] == "CAM-WEBCAM"

    def test_list_cameras_search_filter(
        self, client: TestClient, test_db_session: Session
    ):
        """GET /cameras search query matches name, camera_id, or location."""
        test_db_session.add(
            Camera(
                camera_id="CAM-ALPHA",
                name="Main Entrance Gate",
                source_type=CameraSourceType.VIDEO,
                source_reference="vid.mp4",
                location="Sector North Gate",
                status=CameraStatus.ONLINE,
            )
        )
        test_db_session.add(
            Camera(
                camera_id="CAM-BETA",
                name="Rear Fence View",
                source_type=CameraSourceType.VIDEO,
                source_reference="vid.mp4",
                location="Outpost South",
                status=CameraStatus.ONLINE,
            )
        )
        test_db_session.commit()

        # Search by keyword in name
        resp = client.get("/api/v1/cameras?search=Entrance")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["camera_id"] == "CAM-ALPHA"

        # Search by keyword in location
        resp2 = client.get("/api/v1/cameras?search=South")
        assert resp2.status_code == 200
        assert resp2.json()["total"] == 1
        assert resp2.json()["items"][0]["camera_id"] == "CAM-BETA"

    def test_get_camera_success(
        self, client: TestClient, test_db_session: Session
    ):
        """GET /cameras/{camera_id} returns 200 and camera data for valid ID."""
        cam = Camera(
            camera_id="GATE-01",
            name="Gate Surveillance",
            source_type=CameraSourceType.VIDEO,
            source_reference="feed.mp4",
            location="Gate 1",
            status=CameraStatus.ONLINE,
        )
        test_db_session.add(cam)
        test_db_session.commit()

        # By external camera_id
        resp = client.get("/api/v1/cameras/GATE-01")
        assert resp.status_code == 200
        data = resp.json()
        assert data["camera_id"] == "GATE-01"
        assert data["name"] == "Gate Surveillance"
        assert data["status"] == "ONLINE"
        assert data["created_at"] is not None

        # By surrogate ID
        resp_by_id = client.get(f"/api/v1/cameras/{cam.id}")
        assert resp_by_id.status_code == 200
        assert resp_by_id.json()["camera_id"] == "GATE-01"

    def test_get_camera_missing_returns_404(self, client: TestClient):
        """GET /cameras/{camera_id} returns 404 for unknown camera ID."""
        resp = client.get("/api/v1/cameras/NONEXISTENT-CAM")
        assert resp.status_code == 404
        data = resp.json()
        assert data["status_code"] == 404
        assert "not found" in data["detail"].lower()

    def test_camera_pagination_validation_errors(self, client: TestClient):
        """GET /cameras returns 422 on invalid page or page_size."""
        # Page < 1
        resp = client.get("/api/v1/cameras?page=0")
        assert resp.status_code == 422

        # Page size > 100
        resp2 = client.get("/api/v1/cameras?page_size=200")
        assert resp2.status_code == 422


# ==============================================================================
# 2. ALERT API TESTS
# ==============================================================================


class TestAlertEndpoints:
    """Test suite for /api/v1/alerts endpoints."""

    def test_list_alerts_empty(self, client: TestClient):
        """GET /alerts returns 200 and empty list when no alerts exist."""
        resp = client.get("/api/v1/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_alerts_populated_and_ordering(
        self, client: TestClient, test_db_session: Session
    ):
        """GET /alerts returns alerts sorted chronologically descending."""
        now = datetime.now(timezone.utc)
        for i in range(1, 4):
            al = Alert(
                alert_id=f"ALT-{i:05d}",
                alert_type=AlertType.FENCE_BREACH,
                severity=AlertSeverity.HIGH,
                status=AlertStatus.ACTIVE,
                message=f"Fence breach #{i}",
                alert_timestamp=now + timedelta(minutes=i * 10),
                alert_metadata={"breach_index": i},
            )
            test_db_session.add(al)
        test_db_session.commit()

        resp = client.get("/api/v1/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        # Most recent timestamp should be first
        assert data["items"][0]["alert_id"] == "ALT-00003"
        assert data["items"][2]["alert_id"] == "ALT-00001"

    def test_list_alerts_filtering(
        self, client: TestClient, test_db_session: Session
    ):
        """GET /alerts filters correctly by status, severity, alert_type, and time."""
        now = datetime.now(timezone.utc)
        cam = Camera(
            camera_id="CAM-01",
            name="Cam 1",
            source_type=CameraSourceType.VIDEO,
            source_reference="v.mp4",
            status=CameraStatus.ONLINE,
        )
        test_db_session.add(cam)
        test_db_session.commit()

        a1 = Alert(
            alert_id="ALT-CRIT",
            camera_id=cam.id,
            alert_type=AlertType.FENCE_BREACH,
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.ACTIVE,
            message="Critical Fence Breach",
            alert_timestamp=now - timedelta(hours=2),
            alert_metadata={},
        )
        a2 = Alert(
            alert_id="ALT-LOIT",
            camera_id=cam.id,
            alert_type=AlertType.LOITERING,
            severity=AlertSeverity.MEDIUM,
            status=AlertStatus.RESOLVED,
            message="Medium Loitering",
            alert_timestamp=now - timedelta(hours=1),
            alert_metadata={},
        )
        test_db_session.add_all([a1, a2])
        test_db_session.commit()

        # Filter by severity
        resp_sev = client.get("/api/v1/alerts?severity=CRITICAL")
        assert resp_sev.status_code == 200
        assert resp_sev.json()["total"] == 1
        assert resp_sev.json()["items"][0]["alert_id"] == "ALT-CRIT"

        # Filter by status
        resp_stat = client.get("/api/v1/alerts?status=RESOLVED")
        assert resp_stat.status_code == 200
        assert resp_stat.json()["total"] == 1
        assert resp_stat.json()["items"][0]["alert_id"] == "ALT-LOIT"

        # Filter by alert_type
        resp_type = client.get("/api/v1/alerts?alert_type=FENCE_BREACH")
        assert resp_type.status_code == 200
        assert resp_type.json()["total"] == 1
        assert resp_type.json()["items"][0]["alert_id"] == "ALT-CRIT"

        # Filter by camera_id
        resp_cam = client.get("/api/v1/alerts?camera_id=CAM-01")
        assert resp_cam.status_code == 200
        assert resp_cam.json()["total"] == 2

    def test_get_alert_by_id_success(
        self, client: TestClient, test_db_session: Session
    ):
        """GET /alerts/{alert_id} returns 200 and alert data."""
        al = Alert(
            alert_id="ALT-12345",
            alert_type=AlertType.FENCE_BREACH,
            severity=AlertSeverity.HIGH,
            status=AlertStatus.ACTIVE,
            message="Perimeter violation",
            alert_metadata={"sensor": "virtual_fence"},
        )
        test_db_session.add(al)
        test_db_session.commit()

        resp = client.get("/api/v1/alerts/ALT-12345")
        assert resp.status_code == 200
        data = resp.json()
        assert data["alert_id"] == "ALT-12345"
        assert data["severity"] == "HIGH"
        assert data["status"] == "ACTIVE"
        assert data["alert_metadata"]["sensor"] == "virtual_fence"

    def test_get_alert_missing_returns_404(self, client: TestClient):
        """GET /alerts/{alert_id} returns 404 for unknown alert."""
        resp = client.get("/api/v1/alerts/ALT-99999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_patch_alert_acknowledge_lifecycle(
        self, client: TestClient, test_db_session: Session
    ):
        """PATCH /alerts/{alert_id} transitions ACTIVE -> ACKNOWLEDGED."""
        al = Alert(
            alert_id="ALT-ACK-01",
            alert_type=AlertType.FENCE_BREACH,
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.ACTIVE,
            message="Breach alert",
            alert_metadata={},
        )
        test_db_session.add(al)
        test_db_session.commit()

        payload = {
            "status": "ACKNOWLEDGED",
            "acknowledged_by": "operator_alice",
        }
        resp = client.patch("/api/v1/alerts/ALT-ACK-01", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ACKNOWLEDGED"
        assert data["acknowledged_by"] == "operator_alice"
        assert data["acknowledged_at"] is not None

    def test_patch_alert_resolve_lifecycle(
        self, client: TestClient, test_db_session: Session
    ):
        """PATCH /alerts/{alert_id} transitions ACKNOWLEDGED -> RESOLVED."""
        now = datetime.now(timezone.utc)
        al = Alert(
            alert_id="ALT-RES-01",
            alert_type=AlertType.LOITERING,
            severity=AlertSeverity.HIGH,
            status=AlertStatus.ACKNOWLEDGED,
            acknowledged_at=now,
            acknowledged_by="operator_bob",
            message="Loitering alert",
            alert_metadata={},
        )
        test_db_session.add(al)
        test_db_session.commit()

        payload = {
            "status": "RESOLVED",
            "resolved_by": "officer_charlie",
        }
        resp = client.patch("/api/v1/alerts/ALT-RES-01", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "RESOLVED"
        assert data["resolved_by"] == "officer_charlie"
        assert data["resolved_at"] is not None
        assert data["acknowledged_by"] == "operator_bob"

    def test_patch_alert_invalid_transition_returns_400(
        self, client: TestClient, test_db_session: Session
    ):
        """PATCH /alerts/{alert_id} returns 400 when attempting illegal state transition."""
        now = datetime.now(timezone.utc)
        al = Alert(
            alert_id="ALT-TERMINAL",
            alert_type=AlertType.FENCE_BREACH,
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.RESOLVED,
            resolved_at=now,
            resolved_by="admin",
            message="Already resolved alert",
            alert_metadata={},
        )
        test_db_session.add(al)
        test_db_session.commit()

        # Cannot reopen a RESOLVED alert to ACTIVE
        resp = client.patch("/api/v1/alerts/ALT-TERMINAL", json={"status": "ACTIVE"})
        assert resp.status_code == 400
        data = resp.json()
        assert "invalid alert state transition" in data["detail"].lower()

        # Cannot transition RESOLVED to ACKNOWLEDGED
        resp2 = client.patch("/api/v1/alerts/ALT-TERMINAL", json={"status": "ACKNOWLEDGED"})
        assert resp2.status_code == 400

    def test_patch_alert_missing_returns_404(self, client: TestClient):
        """PATCH /alerts/{alert_id} returns 404 for unknown alert."""
        resp = client.patch(
            "/api/v1/alerts/ALT-UNKNOWN",
            json={"status": "ACKNOWLEDGED", "acknowledged_by": "op1"},
        )
        assert resp.status_code == 404


# ==============================================================================
# 3. TRACK API TESTS
# ==============================================================================


class TestTrackEndpoints:
    """Test suite for /api/v1/tracks/{track_id} endpoints."""

    def test_get_track_success_with_counts(
        self, client: TestClient, test_db_session: Session
    ):
        """GET /tracks/{track_id} returns 200, track fields, and associated counts."""
        now = datetime.now(timezone.utc)
        tr = Track(
            track_id=42,
            class_id=0,
            class_name="person",
            first_seen=now,
            last_seen=now,
            frame_count=25,
            last_confidence=0.92,
            bbox_x1=50,
            bbox_y1=100,
            bbox_x2=150,
            bbox_y2=300,
            last_center_x=100.0,
            last_center_y=200.0,
            status=TrackStatus.ACTIVE,
            observation_metadata={"speed": "slow"},
        )
        test_db_session.add(tr)
        test_db_session.flush()

        # Add associated event and alert
        ev = Event(
            event_id="EVT-42",
            track_id=tr.id,
            event_type=EventType.FENCE_BREACH,
            timestamp=now,
            details={"breach": True},
        )
        al = Alert(
            alert_id="ALT-42",
            track_id=tr.id,
            alert_type=AlertType.FENCE_BREACH,
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.ACTIVE,
            message="Breach by track 42",
            alert_metadata={},
        )
        test_db_session.add_all([ev, al])
        test_db_session.commit()

        # Query by ByteTrack track_id
        resp = client.get("/api/v1/tracks/42")
        assert resp.status_code == 200
        data = resp.json()
        assert data["track_id"] == 42
        assert data["class_name"] == "person"
        assert data["last_confidence"] == 0.92
        assert data["events_count"] == 1
        assert data["alerts_count"] == 1
        assert data["bbox_x1"] == 50

    def test_get_track_missing_returns_404(self, client: TestClient):
        """GET /tracks/{track_id} returns 404 for unknown track."""
        resp = client.get("/api/v1/tracks/9999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ==============================================================================
# 4. EVENT API TESTS
# ==============================================================================


class TestEventEndpoints:
    """Test suite for /api/v1/events/{track_id} endpoints."""

    def test_get_events_for_track_with_events(
        self, client: TestClient, test_db_session: Session
    ):
        """GET /events/{track_id} returns chronological events for existing track."""
        now = datetime.now(timezone.utc)
        tr = Track(
            track_id=10,
            class_id=0,
            class_name="person",
            first_seen=now,
            last_seen=now,
            status=TrackStatus.ACTIVE,
        )
        test_db_session.add(tr)
        test_db_session.flush()

        ev1 = Event(
            event_id="EVT-01",
            track_id=tr.id,
            event_type=EventType.FENCE_BREACH,
            timestamp=now - timedelta(seconds=10),
            details={"breach_step": 1},
        )
        ev2 = Event(
            event_id="EVT-02",
            track_id=tr.id,
            event_type=EventType.LOITERING,
            timestamp=now,
            details={"duration": 15.0},
        )
        test_db_session.add_all([ev1, ev2])
        test_db_session.commit()

        resp = client.get("/api/v1/events/10")
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 2
        assert events[0]["event_id"] == "EVT-01"
        assert events[1]["event_id"] == "EVT-02"

    def test_get_events_for_track_with_no_events_returns_empty_list(
        self, client: TestClient, test_db_session: Session
    ):
        """GET /events/{track_id} returns 200 and empty list if track exists with no events."""
        now = datetime.now(timezone.utc)
        tr = Track(
            track_id=20,
            class_id=0,
            class_name="person",
            first_seen=now,
            last_seen=now,
            status=TrackStatus.ACTIVE,
        )
        test_db_session.add(tr)
        test_db_session.commit()

        resp = client.get("/api/v1/events/20")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_events_for_missing_track_returns_404(self, client: TestClient):
        """GET /events/{track_id} returns 404 if track does not exist."""
        resp = client.get("/api/v1/events/8888")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ==============================================================================
# 5. EVIDENCE API TESTS
# ==============================================================================


class TestEvidenceEndpoints:
    """Test suite for /api/v1/evidence endpoints."""

    def test_get_evidence_metadata_success(
        self, client: TestClient, test_db_session: Session
    ):
        """GET /evidence/{evidence_id} returns 200 and record metadata."""
        al = Alert(
            alert_id="ALT-EVD-01",
            alert_type=AlertType.FENCE_BREACH,
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.ACTIVE,
            message="Alert with evidence",
            alert_metadata={},
        )
        test_db_session.add(al)
        test_db_session.flush()

        evd = Evidence(
            evidence_id="EVD-00001",
            alert_id=al.id,
            file_path="/evidence/EVD-00001.jpg",
            filename="EVD-00001.jpg",
            frame_width=1920,
            frame_height=1080,
            evidence_metadata={"confidence": 0.95},
        )
        test_db_session.add(evd)
        test_db_session.commit()

        resp = client.get("/api/v1/evidence/EVD-00001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["evidence_id"] == "EVD-00001"
        assert data["frame_width"] == 1920
        assert data["frame_height"] == 1080
        assert data["filename"] == "EVD-00001.jpg"

    def test_get_evidence_metadata_missing_returns_404(self, client: TestClient):
        """GET /evidence/{evidence_id} returns 404 for unknown evidence."""
        resp = client.get("/api/v1/evidence/EVD-NONEXISTENT")
        assert resp.status_code == 404

    def test_get_evidence_file_safe_retrieval(
        self, client: TestClient, test_db_session: Session, tmp_path: Path
    ):
        """GET /evidence/{evidence_id}/file safely streams file when valid and inside evidence_dir."""
        # Create a sample JPG file inside tmp_path
        evidence_folder = tmp_path / "evidence"
        evidence_folder.mkdir()
        sample_file = evidence_folder / "test_frame.jpg"
        sample_file.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb")

        al = Alert(
            alert_id="ALT-FILE-01",
            alert_type=AlertType.FENCE_BREACH,
            severity=AlertSeverity.HIGH,
            status=AlertStatus.ACTIVE,
            message="File test",
            alert_metadata={},
        )
        test_db_session.add(al)
        test_db_session.flush()

        evd = Evidence(
            evidence_id="EVD-FILE-01",
            alert_id=al.id,
            file_path=str(sample_file),
            filename="test_frame.jpg",
            frame_width=640,
            frame_height=480,
            evidence_metadata={},
        )
        test_db_session.add(evd)
        test_db_session.commit()

        # Configure evidence_dir to evidence_folder
        with patch.object(settings, "evidence_dir", str(evidence_folder)):
            resp = client.get("/api/v1/evidence/EVD-FILE-01/file")
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "image/jpeg"
            assert resp.content.startswith(b"\xff\xd8\xff")

    def test_get_evidence_file_missing_on_disk_returns_404(
        self, client: TestClient, test_db_session: Session, tmp_path: Path
    ):
        """GET /evidence/{evidence_id}/file returns 404 if file record exists but file is missing on disk."""
        al = Alert(
            alert_id="ALT-NOFILE",
            alert_type=AlertType.FENCE_BREACH,
            severity=AlertSeverity.LOW,
            status=AlertStatus.ACTIVE,
            message="No file test",
            alert_metadata={},
        )
        test_db_session.add(al)
        test_db_session.flush()

        evd = Evidence(
            evidence_id="EVD-NOFILE",
            alert_id=al.id,
            file_path=str(tmp_path / "does_not_exist.jpg"),
            filename="does_not_exist.jpg",
            frame_width=640,
            frame_height=480,
            evidence_metadata={},
        )
        test_db_session.add(evd)
        test_db_session.commit()

        with patch.object(settings, "evidence_dir", str(tmp_path)):
            resp = client.get("/api/v1/evidence/EVD-NOFILE/file")
            assert resp.status_code == 404
            assert "not found on disk" in resp.json()["detail"].lower()

    def test_get_evidence_file_path_traversal_forbidden(
        self, client: TestClient, test_db_session: Session, tmp_path: Path
    ):
        """GET /evidence/{evidence_id}/file returns 403 when file path attempts path traversal out of evidence_dir."""
        evidence_folder = tmp_path / "evidence_safe"
        evidence_folder.mkdir()

        # An external unauthorized file outside evidence_dir
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("TOP SECRET")

        al = Alert(
            alert_id="ALT-TRAVERSAL",
            alert_type=AlertType.FENCE_BREACH,
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.ACTIVE,
            message="Path traversal test",
            alert_metadata={},
        )
        test_db_session.add(al)
        test_db_session.flush()

        evd = Evidence(
            evidence_id="EVD-TRAVERSAL",
            alert_id=al.id,
            # Pointing outside evidence_dir via directory traversal
            file_path=str(evidence_folder / ".." / "secret.txt"),
            filename="secret.txt",
            frame_width=100,
            frame_height=100,
            evidence_metadata={},
        )
        test_db_session.add(evd)
        test_db_session.commit()

        with patch.object(settings, "evidence_dir", str(evidence_folder)):
            resp = client.get("/api/v1/evidence/EVD-TRAVERSAL/file")
            assert resp.status_code == 403
            assert "forbidden" in resp.json()["detail"].lower()


# ==============================================================================
# 6. STATISTICS API TESTS
# ==============================================================================


class TestStatsEndpoints:
    """Test suite for /api/v1/stats aggregate endpoint."""

    def test_get_stats_empty_database(self, client: TestClient):
        """GET /stats returns all zeros on empty database without error."""
        resp = client.get("/api/v1/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cameras"] == 0
        assert data["tracks"] == 0
        assert data["events"] == 0
        assert data["alerts"] == 0
        assert data["evidence"] == 0
        assert data["alerts_by_status"] == {}
        assert data["alerts_by_severity"] == {}

    def test_get_stats_populated_database(
        self, client: TestClient, test_db_session: Session
    ):
        """GET /stats accurately aggregates counts and breakdowns via SQL."""
        now = datetime.now(timezone.utc)

        # Cameras: 2 ONLINE, 1 OFFLINE
        test_db_session.add(Camera(camera_id="C1", name="C1", source_type=CameraSourceType.VIDEO, source_reference="r", status=CameraStatus.ONLINE))
        test_db_session.add(Camera(camera_id="C2", name="C2", source_type=CameraSourceType.VIDEO, source_reference="r", status=CameraStatus.ONLINE))
        test_db_session.add(Camera(camera_id="C3", name="C3", source_type=CameraSourceType.VIDEO, source_reference="r", status=CameraStatus.OFFLINE))

        # Tracks: 2 ACTIVE, 1 LOST
        test_db_session.add(Track(track_id=1, class_id=0, class_name="person", first_seen=now, last_seen=now, status=TrackStatus.ACTIVE))
        test_db_session.add(Track(track_id=2, class_id=0, class_name="person", first_seen=now, last_seen=now, status=TrackStatus.ACTIVE))
        test_db_session.add(Track(track_id=3, class_id=0, class_name="car", first_seen=now, last_seen=now, status=TrackStatus.LOST))

        # Events: 2
        test_db_session.add(Event(event_id="E1", event_type=EventType.FENCE_BREACH, timestamp=now, details={}))
        test_db_session.add(Event(event_id="E2", event_type=EventType.LOITERING, timestamp=now, details={}))

        # Alerts: 2 CRITICAL (ACTIVE), 1 HIGH (RESOLVED)
        al1 = Alert(alert_id="A1", alert_type=AlertType.FENCE_BREACH, severity=AlertSeverity.CRITICAL, status=AlertStatus.ACTIVE, message="m", alert_metadata={})
        al2 = Alert(alert_id="A2", alert_type=AlertType.FENCE_BREACH, severity=AlertSeverity.CRITICAL, status=AlertStatus.ACTIVE, message="m", alert_metadata={})
        al3 = Alert(alert_id="A3", alert_type=AlertType.LOITERING, severity=AlertSeverity.HIGH, status=AlertStatus.RESOLVED, message="m", alert_metadata={})
        test_db_session.add_all([al1, al2, al3])
        test_db_session.flush()

        # Evidence: 1
        evd = Evidence(
            evidence_id="EV1",
            alert_id=al1.id,
            file_path="f.jpg",
            filename="f.jpg",
            frame_width=640,
            frame_height=480,
            evidence_metadata={},
        )
        test_db_session.add(evd)
        test_db_session.commit()

        resp = client.get("/api/v1/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cameras"] == 3
        assert data["tracks"] == 3
        assert data["events"] == 2
        assert data["alerts"] == 3
        assert data["evidence"] == 1

        # Breakdowns
        assert data["cameras_by_status"]["ONLINE"] == 2
        assert data["cameras_by_status"]["OFFLINE"] == 1
        assert data["tracks_by_status"]["ACTIVE"] == 2
        assert data["tracks_by_status"]["LOST"] == 1
        assert data["alerts_by_status"]["ACTIVE"] == 2
        assert data["alerts_by_status"]["RESOLVED"] == 1
        assert data["alerts_by_severity"]["CRITICAL"] == 2
        assert data["alerts_by_severity"]["HIGH"] == 1


# ==============================================================================
# 7. OPENAPI & CROSS-CUTTING SPECIFICATION TESTS
# ==============================================================================


class TestOpenAPISpecification:
    """Test suite ensuring all endpoints are registered in OpenAPI under /api/v1."""

    def test_openapi_schema_contains_all_m16_routes(self, client: TestClient):
        """Verify OpenAPI schema documents all required M16 routes under /api/v1."""
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        paths = schema.get("paths", {})

        expected_paths = [
            "/api/v1/cameras",
            "/api/v1/cameras/{camera_id}",
            "/api/v1/alerts",
            "/api/v1/alerts/{alert_id}",
            "/api/v1/tracks/{track_id}",
            "/api/v1/events/{track_id}",
            "/api/v1/evidence/{evidence_id}",
            "/api/v1/evidence/{evidence_id}/file",
            "/api/v1/stats",
        ]

        for p in expected_paths:
            assert p in paths, f"Expected endpoint '{p}' not registered in OpenAPI schema."

        # Verify PATCH method on /api/v1/alerts/{alert_id}
        assert "patch" in paths["/api/v1/alerts/{alert_id}"]
        # Verify GET methods
        assert "get" in paths["/api/v1/cameras"]
        assert "get" in paths["/api/v1/alerts"]
        assert "get" in paths["/api/v1/tracks/{track_id}"]
        assert "get" in paths["/api/v1/events/{track_id}"]
        assert "get" in paths["/api/v1/evidence/{evidence_id}"]
        assert "get" in paths["/api/v1/evidence/{evidence_id}/file"]
        assert "get" in paths["/api/v1/stats"]
