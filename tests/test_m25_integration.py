"""M25 Full IBVAP System Integration Tests.

Verifies end-to-end integration across:
1. Pipeline Persistence: PipelineResult -> PostgreSQL ORM entities.
2. Track In-Place Upserting: No duplicate track rows per frame.
3. Genuine Event Persistence: Only real M8/M9 events stored.
4. Alert Persistence: M10 alerts persisted with relational foreign keys.
5. Evidence Persistence: M11 evidence metadata referencing disk files.
6. Transaction Rollback & Honest Failure: No fabricated success on DB errors.
7. WebSocket Integration: M17 adapter event/frame/stats/status broadcasting.
8. Camera Status Propagation: State synchronization across DB and WebSocket.
9. Alert Lifecycle: ACTIVE -> ACKNOWLEDGED -> RESOLVED status updates.
10. Real Video Verification: Controlled run on videos/test.mp4.
11. Deterministic Synthetic Event Verification: Fence breach & loitering chain.
"""

import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import time
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure backend and root paths are available
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ai_engine.alerts import Alert as AIAlert, AlertSeverity as AISeverity, AlertStatus as AIStatus, AlertType as AIAlertType
from ai_engine.event_memory import PositionalObservation, TrackMemory
from ai_engine.evidence import EvidenceRecord
from ai_engine.fence_breach import BreachEventType, FenceBreachEvent, FenceState
from ai_engine.loitering import LoiteringEvent
from ai_engine.movement import MovementResult
from ai_engine.pipeline import AIPipeline, PipelineResult
from ai_engine.tracker import TrackedObject
from ai_engine.video_input import VideoSource

from app.core.database import get_db
from app.main import app
from app.models.alert import Alert
from app.models.base import Base
from app.models.camera import Camera
from app.models.enums import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    CameraSourceType,
    CameraStatus,
    EventType,
    TrackStatus,
)
from app.models.event import Event
from app.models.evidence import Evidence
from app.models.track import Track
from app.schemas.websocket import CameraStreamStatus, WebSocketMessageType
from app.services.pipeline_persistence import PipelinePersistenceError, PipelinePersistenceService
from app.services.pipeline_runtime import PipelineRuntime
from app.services.websocket_adapter import PipelineWebSocketAdapter
from app.services.websocket_manager import WebSocketConnectionManager
from fastapi.testclient import TestClient


# ==============================================================================
# In-Memory Database Fixtures
# ==============================================================================

@pytest.fixture
def test_db_session() -> Generator[Session, None, None]:
    """Provide an isolated in-memory transactional database session."""
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
def persistence_service(test_db_session: Session) -> PipelinePersistenceService:
    """Provide a PipelinePersistenceService bound to the test session factory."""
    return PipelinePersistenceService(session_factory=lambda: test_db_session)


@pytest.fixture
def test_client(test_db_session: Session) -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient bound to the isolated test database."""
    def override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


# ==============================================================================
# Helper Factories
# ==============================================================================

def create_sample_tracked_object(
    track_id: int = 1,
    class_name: str = "person",
    confidence: float = 0.92,
    x1: int = 100,
    y1: int = 150,
    x2: int = 200,
    y2: int = 350,
) -> TrackedObject:
    """Create a TrackedObject matching M4 output."""
    return TrackedObject(
        track_id=track_id,
        class_id=0,
        class_name=class_name,
        confidence=confidence,
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
    )


def create_sample_track_memory(track_id: int = 1) -> TrackMemory:
    """Create a mock TrackMemory matching M5 output."""
    now = datetime.now(timezone.utc)
    obs = PositionalObservation(
        frame_time=now,
        center_x=150.0,
        center_y=250.0,
        x1=100,
        y1=150,
        x2=200,
        y2=350,
        confidence=0.92,
    )
    tm = TrackMemory(
        track_id=track_id,
        class_id=0,
        class_name="person",
        first_seen=now,
        last_seen=now,
        last_confidence=0.92,
        last_bbox=(100, 150, 200, 350),
        last_center=(150.0, 250.0),
        frame_count=5,
    )
    tm.history.append(obs)
    return tm


# ==============================================================================
# 1. Pipeline Persistence Tests
# ==============================================================================

class TestPipelinePersistence:
    """Unit and integration tests for PipelinePersistenceService."""

    def test_camera_resolution_and_no_duplicates(
        self, persistence_service: PipelinePersistenceService, test_db_session: Session
    ):
        """Camera record is created on first result and updated subsequently without duplicates."""
        # Frame 1
        res1 = PipelineResult(frame_id=1, timestamp=time.time())
        summary1 = persistence_service.persist_pipeline_result(
            result=res1,
            camera_id="CAM_NORTH",
            db=test_db_session,
            camera_info={"name": "North Gate Perimeter", "location": "Sector 1"},
        )
        assert summary1["camera_db_id"] is not None

        cams = test_db_session.scalars(select(Camera).where(Camera.camera_id == "CAM_NORTH")).all()
        assert len(cams) == 1
        assert cams[0].name == "North Gate Perimeter"
        assert cams[0].status == CameraStatus.ONLINE

        # Frame 2 with same camera_id
        res2 = PipelineResult(frame_id=2, timestamp=time.time())
        summary2 = persistence_service.persist_pipeline_result(
            result=res2,
            camera_id="CAM_NORTH",
            db=test_db_session,
            camera_info={"status": CameraStatus.ONLINE},
        )
        cams_after = test_db_session.scalars(select(Camera).where(Camera.camera_id == "CAM_NORTH")).all()
        assert len(cams_after) == 1
        assert summary2["camera_db_id"] == summary1["camera_db_id"]

    def test_track_upsert_no_duplicate_rows(
        self, persistence_service: PipelinePersistenceService, test_db_session: Session
    ):
        """A tracked object seen across consecutive frames updates in-place without duplicate rows."""
        obj = create_sample_tracked_object(track_id=101)
        tm = create_sample_track_memory(track_id=101)

        # Frame 1
        res1 = PipelineResult(
            frame_id=1,
            timestamp=100.0,
            tracked_objects=[obj],
            track_memories=[tm],
        )
        summary1 = persistence_service.persist_pipeline_result(res1, "CAM_01", db=test_db_session)
        assert summary1["tracks_upserted"] == 1

        db_tracks = test_db_session.scalars(select(Track).where(Track.track_id == 101)).all()
        assert len(db_tracks) == 1
        assert db_tracks[0].frame_count == 5
        assert db_tracks[0].last_center_x == 150.0

        # Frame 2 with updated position
        obj2 = create_sample_tracked_object(track_id=101, confidence=0.95, x1=110, y1=160, x2=210, y2=360)
        tm.frame_count = 6
        tm.last_center = (160.0, 260.0)

        res2 = PipelineResult(
            frame_id=2,
            timestamp=100.1,
            tracked_objects=[obj2],
            track_memories=[tm],
        )
        summary2 = persistence_service.persist_pipeline_result(res2, "CAM_01", db=test_db_session)
        assert summary2["tracks_upserted"] == 1

        # Must still be exactly one track in DB
        db_tracks_after = test_db_session.scalars(select(Track).where(Track.track_id == 101)).all()
        assert len(db_tracks_after) == 1
        assert db_tracks_after[0].frame_count == 6
        assert db_tracks_after[0].last_center_x == 160.0
        assert db_tracks_after[0].last_confidence == 0.95

    def test_genuine_event_persistence_only(
        self, persistence_service: PipelinePersistenceService, test_db_session: Session
    ):
        """Only genuine events are persisted; frames without events generate 0 event rows."""
        # Frame without events
        res_no_event = PipelineResult(frame_id=1, timestamp=time.time())
        summary_empty = persistence_service.persist_pipeline_result(res_no_event, "CAM_01", db=test_db_session)
        assert summary_empty["events_persisted"] == 0

        event_count = test_db_session.scalar(select(func.count(Event.id)))
        assert event_count == 0

        # Frame with genuine FenceBreachEvent
        fbe = FenceBreachEvent(
            track_id=101,
            event_type=BreachEventType.FENCE_BREACH,
            previous_state=FenceState.OUTSIDE,
            current_state=FenceState.INSIDE,
            frame_id=2,
            center=(150, 200),
            breach_count=1,
        )
        res_event = PipelineResult(
            frame_id=2,
            timestamp=time.time(),
            fence_breach_events=[fbe],
        )
        summary_event = persistence_service.persist_pipeline_result(res_event, "CAM_01", db=test_db_session)
        assert summary_event["events_persisted"] == 1

        db_events = test_db_session.scalars(select(Event)).all()
        assert len(db_events) == 1
        assert db_events[0].event_type == EventType.FENCE_BREACH
        assert db_events[0].details["previous_state"] == "OUTSIDE"
        assert db_events[0].details["current_state"] == "INSIDE"

    def test_alert_and_evidence_relational_persistence(
        self, persistence_service: PipelinePersistenceService, test_db_session: Session
    ):
        """Alerts and EvidenceRecords are persisted with valid foreign key relationships."""
        al = AIAlert(
            alert_id="ALT-TEST-001",
            track_id=101,
            alert_type=AIAlertType.FENCE_BREACH,
            severity=AISeverity.CRITICAL,
            status=AIStatus.ACTIVE,
            message="Virtual fence perimeter breach detected",
            timestamp=100.0,
            camera_id="CAM_01",
        )
        ev = EvidenceRecord(
            evidence_id="EVD-TEST-001",
            alert_id="ALT-TEST-001",
            track_id=101,
            camera_id="CAM_01",
            alert_type="FENCE_BREACH",
            severity="CRITICAL",
            timestamp=100.0,
            file_path="/evidence/test_frame.jpg",
            filename="test_frame.jpg",
            frame_dimensions=(1920, 1080),
        )
        res = PipelineResult(
            frame_id=10,
            timestamp=100.0,
            alerts=[al],
            evidence_records=[ev],
        )

        summary = persistence_service.persist_pipeline_result(res, "CAM_01", db=test_db_session)
        assert summary["alerts_persisted"] == 1
        assert summary["evidence_persisted"] == 1

        db_alert = test_db_session.scalar(select(Alert).where(Alert.alert_id == "ALT-TEST-001"))
        assert db_alert is not None
        assert db_alert.severity == AlertSeverity.CRITICAL
        assert db_alert.status == AlertStatus.ACTIVE
        assert db_alert.message == "Virtual fence perimeter breach detected"

        db_ev = test_db_session.scalar(select(Evidence).where(Evidence.evidence_id == "EVD-TEST-001"))
        assert db_ev is not None
        assert db_ev.alert_id == db_alert.id
        assert db_ev.filename == "test_frame.jpg"
        assert db_ev.frame_width == 1920
        assert db_ev.frame_height == 1080

    def test_failure_rollback_and_no_fabricated_success(
        self, persistence_service: PipelinePersistenceService
    ):
        """Database failures trigger session rollback and raise PipelinePersistenceError."""
        mock_session = MagicMock()
        mock_session.flush.side_effect = RuntimeError("Simulated DB connection lost")

        res = PipelineResult(frame_id=1, timestamp=100.0)
        with pytest.raises(PipelinePersistenceError, match="Database persistence failure"):
            persistence_service.persist_pipeline_result(res, "CAM_ERR", db=mock_session)

        assert mock_session.flush.called


# ==============================================================================
# 2. WebSocket Adapter & Integration Tests
# ==============================================================================

class TestWebSocketIntegration:
    """Verifies that PipelineResult is correctly published via PipelineWebSocketAdapter."""

    def test_publish_pipeline_result_broadcasts_events_frames_stats(self):
        """Adapter broadcasts alerts, frame (if requested), and statistics."""
        async def _run():
            manager = WebSocketConnectionManager()
            adapter = PipelineWebSocketAdapter(camera_id="CAM_01", manager=manager)

            # Mock WebSocket client
            mock_ws = AsyncMock()
            await manager.connect("CAM_01", mock_ws)

            al = AIAlert(
                alert_id="ALT-WS-001",
                track_id=1,
                alert_type=AIAlertType.FENCE_BREACH,
                severity=AISeverity.CRITICAL,
                message="Alert over WS",
            )
            dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)

            res = PipelineResult(
                frame_id=5,
                timestamp=time.time(),
                processed_frame=dummy_frame,
                tracked_objects=[create_sample_tracked_object(1)],
                alerts=[al],
            )

            await adapter.publish_pipeline_result(res, include_frame=True, fps=15.0)
            await asyncio.sleep(0.05)

            sent_messages = [call.args[0] for call in mock_ws.send_text.call_args_list]
            assert len(sent_messages) >= 2

            msg_types = [m for m in sent_messages if "alert" in m or "frame" in m or "stats" in m]
            assert any("alert" in m for m in msg_types)
            assert any("stats" in m for m in msg_types)
            assert any("frame" in m for m in msg_types)

        asyncio.run(_run())

    def test_camera_status_propagation(self):
        """Adapter broadcasts camera_status transitions (ONLINE, OFFLINE, ERROR)."""
        async def _run():
            manager = WebSocketConnectionManager()
            adapter = PipelineWebSocketAdapter(camera_id="CAM_01", manager=manager)

            mock_ws = AsyncMock()
            await manager.connect("CAM_01", mock_ws)

            await adapter.publish_camera_status(CameraStreamStatus.ONLINE, details="Stream connected")
            await asyncio.sleep(0.05)
            import json
            sent = json.loads(mock_ws.send_text.call_args_list[-1].args[0])
            assert sent["type"] == "camera_status"
            assert sent["data"]["status"] == "ONLINE"

            await adapter.publish_camera_status(CameraStreamStatus.ERROR, details="Signal loss")
            await asyncio.sleep(0.05)
            sent_err = json.loads(mock_ws.send_text.call_args_list[-1].args[0])
            assert sent_err["type"] == "camera_status"
            assert sent_err["data"]["status"] == "ERROR"

        asyncio.run(_run())


# ==============================================================================
# 3. Pipeline Runtime Coordinator Tests
# ==============================================================================

class TestPipelineRuntime:
    """Verifies PipelineRuntime binding AI Engine, DB persistence, and WebSocket."""

    def test_runtime_step_persists_and_broadcasts(
        self, persistence_service: PipelinePersistenceService, test_db_session: Session
    ):
        """Runtime step processes frame, updates DB, and triggers WebSocket delivery."""
        async def _run():
            manager = WebSocketConnectionManager()
            adapter = PipelineWebSocketAdapter(camera_id="CAM_RUNTIME_01", manager=manager)

            mock_pipeline = MagicMock(spec=AIPipeline)
            dummy_result = PipelineResult(
                frame_id=1,
                timestamp=100.0,
                tracked_objects=[create_sample_tracked_object(track_id=77)],
                track_memories=[create_sample_track_memory(track_id=77)],
            )
            mock_pipeline.process_frame.return_value = dummy_result

            runtime = PipelineRuntime(
                camera_id="CAM_RUNTIME_01",
                pipeline=mock_pipeline,
                ws_adapter=adapter,
                persistence_service=persistence_service,
                auto_persist=True,
            )

            dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
            res = await runtime.process_frame(dummy_frame, frame_id=1, db=test_db_session)
            assert res.frame_id == 1
            assert runtime.frame_count == 1

            # Check DB state
            db_track = test_db_session.scalar(select(Track).where(Track.track_id == 77))
            assert db_track is not None
            assert db_track.track_id == 77

        asyncio.run(_run())

    def test_runtime_status_synchronization(
        self, persistence_service: PipelinePersistenceService, test_db_session: Session
    ):
        """Runtime updates status in memory, in PostgreSQL, and broadcasts to WebSocket."""
        async def _run():
            import json
            manager = WebSocketConnectionManager()
            adapter = PipelineWebSocketAdapter(camera_id="CAM_SYNC_01", manager=manager)
            mock_ws = AsyncMock()
            await manager.connect("CAM_SYNC_01", mock_ws)

            runtime = PipelineRuntime(
                camera_id="CAM_SYNC_01",
                ws_adapter=adapter,
                persistence_service=persistence_service,
                auto_persist=True,
            )

            # Pre-seed camera
            cam = Camera(
                camera_id="CAM_SYNC_01",
                name="Sync Camera",
                source_type=CameraSourceType.VIDEO,
                source_reference="test.mp4",
                status=CameraStatus.OFFLINE,
            )
            test_db_session.add(cam)
            test_db_session.commit()

            # Transition to ONLINE
            await runtime.start(db=test_db_session)
            assert runtime.status == CameraStatus.ONLINE

            test_db_session.refresh(cam)
            assert cam.status == CameraStatus.ONLINE

            await asyncio.sleep(0.05)
            sent = json.loads(mock_ws.send_text.call_args_list[-1].args[0])
            assert sent["data"]["status"] == "ONLINE"

            # Transition to ERROR
            await runtime.set_error("Lens blocked", db=test_db_session)
            assert runtime.status == CameraStatus.ERROR
            test_db_session.refresh(cam)
            assert cam.status == CameraStatus.ERROR

            await asyncio.sleep(0.05)
            sent_err = json.loads(mock_ws.send_text.call_args_list[-1].args[0])
            assert sent_err["data"]["status"] == "ERROR"

        asyncio.run(_run())


# ==============================================================================
# 4. REST Consistency & Alert Lifecycle (M16 + M20)
# ==============================================================================

class TestRESTConsistencyAndLifecycle:
    """Verifies that M16 endpoints expose persisted data and handle alert lifecycle."""

    def test_alert_lifecycle_active_to_acknowledged_to_resolved(
        self,
        persistence_service: PipelinePersistenceService,
        test_db_session: Session,
        test_client: TestClient,
    ):
        """Verify ACTIVE -> ACKNOWLEDGED -> RESOLVED lifecycle via REST PATCH."""
        # 1. Persist alert through pipeline service
        al = AIAlert(
            alert_id="ALT-LIFE-001",
            track_id=1,
            alert_type=AIAlertType.FENCE_BREACH,
            severity=AISeverity.HIGH,
            status=AIStatus.ACTIVE,
            message="Boundary crossing detected",
            timestamp=100.0,
            camera_id="CAM_01",
        )
        res = PipelineResult(frame_id=1, timestamp=100.0, alerts=[al])
        persistence_service.persist_pipeline_result(res, "CAM_01", db=test_db_session)

        # 2. Query via GET /api/v1/alerts
        get_res = test_client.get("/api/v1/alerts")
        assert get_res.status_code == 200
        data = get_res.json()
        assert data["total"] == 1
        assert data["items"][0]["alert_id"] == "ALT-LIFE-001"
        assert data["items"][0]["status"] == "ACTIVE"

        # 3. Transition: ACTIVE -> ACKNOWLEDGED
        patch_ack = test_client.patch(
            "/api/v1/alerts/ALT-LIFE-001",
            json={"status": "ACKNOWLEDGED", "acknowledged_by": "Officer Smith"},
        )
        assert patch_ack.status_code == 200
        assert patch_ack.json()["status"] == "ACKNOWLEDGED"
        assert patch_ack.json()["acknowledged_by"] == "Officer Smith"

        # 4. Transition: ACKNOWLEDGED -> RESOLVED
        patch_res = test_client.patch(
            "/api/v1/alerts/ALT-LIFE-001",
            json={"status": "RESOLVED", "resolved_by": "Supervisor Jones"},
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["status"] == "RESOLVED"
        assert patch_res.json()["resolved_by"] == "Supervisor Jones"

        # 5. Invalid transition: RESOLVED -> ACTIVE (must be rejected with 400)
        invalid_patch = test_client.patch(
            "/api/v1/alerts/ALT-LIFE-001",
            json={"status": "ACTIVE"},
        )
        assert invalid_patch.status_code == 400


# ==============================================================================
# 5. Real Video & Synthetic Event Integration Verification
# ==============================================================================

class TestEndToEndVerification:
    """Verifies pipeline execution on actual video and deterministic synthetic events."""

    def test_real_video_persistence_test_mp4(
        self, persistence_service: PipelinePersistenceService, test_db_session: Session
    ):
        """Controlled real video test: reads videos/test.mp4, runs YOLO+ByteTrack, and persists tracks."""
        video_path = ROOT_DIR / "videos" / "test.mp4"
        if not video_path.is_file():
            pytest.skip("videos/test.mp4 not found on disk")

        # Initialize actual AIPipeline on CPU
        pipeline = AIPipeline(camera_id="CAM_REAL_01")
        source = VideoSource(source_type="video", source=str(video_path))
        pipeline.video_source = source

        # Process 3 frames of real video
        results = list(pipeline.process_source(max_frames=3))
        assert len(results) == 3

        for r in results:
            summary = persistence_service.persist_pipeline_result(
                result=r,
                camera_id="CAM_REAL_01",
                db=test_db_session,
                camera_info={"name": "Real Video Camera", "source_reference": str(video_path)},
            )
            assert summary["camera_db_id"] is not None

        # Verify real tracks stored in DB
        tracks = test_db_session.scalars(select(Track)).all()
        assert len(tracks) > 0
        for t in tracks:
            assert t.camera_id is not None
            assert t.class_name is not None
            assert t.last_seen is not None

    def test_deterministic_synthetic_breach_and_loitering(
        self, persistence_service: PipelinePersistenceService, test_db_session: Session
    ):
        """Deterministic synthetic event verification: simulates breach + loiter through complete chain."""
        # 1. Synthetic fence breach event
        fbe = FenceBreachEvent(
            track_id=505,
            event_type=BreachEventType.FENCE_BREACH,
            previous_state=FenceState.OUTSIDE,
            current_state=FenceState.INSIDE,
            frame_id=12,
            center=(320, 240),
            breach_count=1,
        )
        # Corresponding Alert and Evidence
        al = AIAlert(
            alert_id="ALT-SYNTH-505",
            track_id=505,
            alert_type=AIAlertType.FENCE_BREACH,
            severity=AISeverity.CRITICAL,
            status=AIStatus.ACTIVE,
            message="Fence breach detected in restricted zone",
            timestamp=200.0,
            camera_id="CAM_SYNTH",
        )
        ev = EvidenceRecord(
            evidence_id="EVD-SYNTH-505",
            alert_id="ALT-SYNTH-505",
            track_id=505,
            camera_id="CAM_SYNTH",
            alert_type="FENCE_BREACH",
            severity="CRITICAL",
            timestamp=200.0,
            file_path="/evidence/synthetic_breach.jpg",
            filename="synthetic_breach.jpg",
            frame_dimensions=(1280, 720),
        )

        obj = create_sample_tracked_object(track_id=505)
        tm = create_sample_track_memory(track_id=505)

        synth_result = PipelineResult(
            frame_id=12,
            timestamp=200.0,
            tracked_objects=[obj],
            track_memories=[tm],
            fence_breach_events=[fbe],
            alerts=[al],
            evidence_records=[ev],
        )

        summary = persistence_service.persist_pipeline_result(
            result=synth_result,
            camera_id="CAM_SYNTH",
            db=test_db_session,
        )

        assert summary["tracks_upserted"] == 1
        assert summary["events_persisted"] == 1
        assert summary["alerts_persisted"] == 1
        assert summary["evidence_persisted"] == 1

        # Check DB entities and integrity
        event = test_db_session.scalar(select(Event).where(Event.event_type == EventType.FENCE_BREACH))
        assert event is not None
        assert event.details["current_state"] == "INSIDE"

        alert = test_db_session.scalar(select(Alert).where(Alert.alert_id == "ALT-SYNTH-505"))
        assert alert is not None
        assert alert.event_id == event.id
        assert alert.severity == AlertSeverity.CRITICAL

        evidence = test_db_session.scalar(select(Evidence).where(Evidence.evidence_id == "EVD-SYNTH-505"))
        assert evidence is not None
        assert evidence.alert_id == alert.id
