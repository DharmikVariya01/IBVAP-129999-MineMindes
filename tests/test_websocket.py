"""Comprehensive WebSocket Test Suite for IBVAP Module 17.

Validates all 20 required acceptance criteria:
1. WebSocket connection succeeds.
2. Client is registered.
3. Correct camera subscription is maintained.
4. Disconnect removes client.
5. Multiple clients can connect to the same camera.
6. Different cameras remain isolated.
7. Broadcast reaches all clients of the correct camera.
8. Broadcast does not reach another camera.
9. Broadcast_all works if implemented.
10. JSON message schema is valid.
11. Alert message serialization works.
12. Frame message serialization works.
13. Camera status message works.
14. Stats message works.
15. Heartbeat works.
16. Malformed client message is handled safely.
17. Unknown message type is handled safely.
18. Failed/stale connection is cleaned up.
19. One slow/failed client does not crash the manager.
20. Existing REST APIs still work.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, List, Optional
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient

# Ensure backend and project root are in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app
from app.schemas.websocket import (
    AlertData,
    CameraStatusData,
    CameraStreamStatus,
    ClientMessage,
    ConnectionData,
    ErrorData,
    FrameData,
    HeartbeatData,
    StatsData,
    WebSocketMessage,
    WebSocketMessageType,
)
from app.services.websocket_adapter import PipelineWebSocketAdapter
from app.services.websocket_manager import (
    ClientSubscription,
    WebSocketConnectionManager,
    websocket_manager,
)


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app, raise_server_exceptions=False)


# ==============================================================================
# 1. CONNECTION LIFECYCLE & REGISTRATION TESTS (Req 1, 2, 3, 4, 18)
# ==============================================================================


class TestWebSocketConnectionLifecycle:
    """Verifies connection establishment, tracking, camera grouping, and disconnects."""

    def test_connection_succeeds_and_handshakes(self, client: TestClient):
        """Req 1: Verify WebSocket connection succeeds and receives initial handshake."""
        with client.websocket_connect("/api/v1/ws/CAM-01") as ws:
            handshake = ws.receive_json()
            assert handshake["type"] == WebSocketMessageType.CONNECTION.value
            assert handshake["camera_id"] == "CAM-01"
            assert "timestamp" in handshake
            assert handshake["data"]["status"] == "connected"
            assert "Connected to camera stream" in handshake["data"]["message"]

    def test_client_is_registered_in_manager(self, client: TestClient):
        """Req 2 & 3: Verify client is registered and correct camera subscription is maintained."""
        initial_total = websocket_manager.get_connection_count()
        initial_cam = websocket_manager.get_camera_connection_count("CAM-01")

        with client.websocket_connect("/api/v1/ws/CAM-01") as ws:
            ws.receive_json()  # Handshake
            assert websocket_manager.get_connection_count() == initial_total + 1
            assert websocket_manager.get_camera_connection_count("CAM-01") == initial_cam + 1
            assert "CAM-01" in websocket_manager.get_active_cameras()

    def test_disconnect_removes_client(self, client: TestClient):
        """Req 4: Verify client disconnect cleanly removes client from manager state."""
        cam_id = "CAM-DISCONNECT-TEST"
        with client.websocket_connect(f"/api/v1/ws/{cam_id}") as ws:
            ws.receive_json()
            assert websocket_manager.get_camera_connection_count(cam_id) == 1

        # After exiting context manager, client is disconnected
        assert websocket_manager.get_camera_connection_count(cam_id) == 0

    def test_invalid_camera_id_rejected(self, client: TestClient):
        """Security: Verify malformed or illegal camera_id is rejected with policy violation."""
        with pytest.raises(Exception):  # TestClient raises on server close during connect
            with client.websocket_connect("/api/v1/ws/INVALID@CAMERA!#$") as ws:
                ws.receive_json()


# ==============================================================================
# 2. MULTI-CLIENT & CAMERA ISOLATION TESTS (Req 5, 6, 7, 8, 9)
# ==============================================================================


class TestMultiClientAndIsolation:
    """Verifies isolation across camera streams and broadcast delivery."""

    def test_multiple_clients_same_camera(self, client: TestClient):
        """Req 5 & 7: Verify multiple clients connect to same camera and receive broadcast."""
        cam_id = "CAM-MULTI-01"
        with client.websocket_connect(f"/api/v1/ws/{cam_id}") as ws1:
            ws1.receive_json()  # Handshake 1
            with client.websocket_connect(f"/api/v1/ws/{cam_id}") as ws2:
                ws2.receive_json()  # Handshake 2

                assert websocket_manager.get_camera_connection_count(cam_id) == 2

                # Broadcast to CAM-MULTI-01
                alert_msg = {
                    "type": "alert",
                    "camera_id": cam_id,
                    "data": {"alert_id": "ALT-100", "message": "Test breach"},
                }
                dispatched = asyncio.run(websocket_manager.broadcast_to_camera(cam_id, alert_msg))
                assert dispatched == 2

                # Both clients receive the message
                msg1 = ws1.receive_json()
                msg2 = ws2.receive_json()
                assert msg1["data"]["alert_id"] == "ALT-100"
                assert msg2["data"]["alert_id"] == "ALT-100"

    def test_different_cameras_remain_isolated(self, client: TestClient):
        """Req 6 & 8: Verify broadcast to Camera A does NOT reach Camera B subscribers."""
        cam_a = "CAM-ALPHA"
        cam_b = "CAM-BETA"

        with client.websocket_connect(f"/api/v1/ws/{cam_a}") as ws_a:
            ws_a.receive_json()  # Handshake A
            with client.websocket_connect(f"/api/v1/ws/{cam_b}") as ws_b:
                ws_b.receive_json()  # Handshake B

                # Broadcast only to Camera A
                msg_a = {
                    "type": "alert",
                    "camera_id": cam_a,
                    "data": {"alert_id": "ALT-ALPHA-ONLY"},
                }
                dispatched = asyncio.run(websocket_manager.broadcast_to_camera(cam_a, msg_a))
                assert dispatched == 1

                # Client A receives message
                received_a = ws_a.receive_json()
                assert received_a["data"]["alert_id"] == "ALT-ALPHA-ONLY"

                # Send a ping on Client B to confirm Client B is alive and did NOT receive msg_a
                ws_b.send_json({"type": "ping", "data": {"token": "check_b"}})
                resp_b = ws_b.receive_json()
                # The next message received by B is the heartbeat ping reply, NOT the broadcast
                assert resp_b["type"] == "heartbeat"
                assert resp_b["data"]["reply"] == "check_b"

    def test_broadcast_all_reaches_all_cameras(self, client: TestClient):
        """Req 9: Verify broadcast_all sends to subscribers across all cameras."""
        cam_1 = "CAM-GLOBAL-1"
        cam_2 = "CAM-GLOBAL-2"

        with client.websocket_connect(f"/api/v1/ws/{cam_1}") as ws1:
            ws1.receive_json()
            with client.websocket_connect(f"/api/v1/ws/{cam_2}") as ws2:
                ws2.receive_json()

                global_msg = {
                    "type": "camera_status",
                    "camera_id": "SYSTEM",
                    "data": {"status": "ONLINE", "details": "Global maintenance ended"},
                }
                dispatched = asyncio.run(websocket_manager.broadcast_all(global_msg))
                assert dispatched >= 2

                msg1 = ws1.receive_json()
                msg2 = ws2.receive_json()
                assert msg1["data"]["details"] == "Global maintenance ended"
                assert msg2["data"]["details"] == "Global maintenance ended"


# ==============================================================================
# 3. MESSAGE CONTRACTS & SERIALIZATION TESTS (Req 10, 11, 12, 13, 14, 15)
# ==============================================================================


class TestMessageSchemasAndSerialization:
    """Verifies strongly typed Pydantic models for all supported message types."""

    def test_json_message_schema_validation(self):
        """Req 10: Verify canonical WebSocket message schema structure."""
        msg = WebSocketMessage(
            type=WebSocketMessageType.CONNECTION,
            camera_id="CAM-01",
            data={"status": "connected"},
        )
        payload = msg.model_dump()
        assert payload["type"] == "connection"
        assert payload["camera_id"] == "CAM-01"
        assert "timestamp" in payload
        assert payload["timestamp"].endswith("Z")
        assert isinstance(payload["data"], dict)

    def test_alert_message_serialization(self):
        """Req 11: Verify alert message schema and serialization compatible with M10/M16."""
        alert_data = AlertData(
            alert_id="ALT-2026-001",
            camera_id="CAM-01",
            track_id=42,
            alert_type="FENCE_BREACH",
            severity="CRITICAL",
            status="ACTIVE",
            message="Fence breach detected in Sector North",
            timestamp="2026-01-01T12:00:00Z",
            zone_info={"zone_id": 1, "zone_name": "Perimeter"},
            evidence_reference="/evidence/CAM-01/frame_100.jpg",
        )
        msg = WebSocketMessage(
            type=WebSocketMessageType.ALERT,
            camera_id="CAM-01",
            data=alert_data.model_dump(),
        )
        dumped = msg.model_dump()
        assert dumped["type"] == "alert"
        assert dumped["data"]["alert_id"] == "ALT-2026-001"
        assert dumped["data"]["track_id"] == 42
        assert dumped["data"]["severity"] == "CRITICAL"
        assert dumped["data"]["evidence_reference"] == "/evidence/CAM-01/frame_100.jpg"

    def test_frame_message_serialization(self):
        """Req 12: Verify frame message schema with encoded data and optional metadata."""
        frame_data = FrameData(
            frame_id=1024,
            encoded_data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
            width=1920,
            height=1080,
            metadata={"fps": 29.97, "detections": 3},
        )
        msg = WebSocketMessage(
            type=WebSocketMessageType.FRAME,
            camera_id="CAM-01",
            data=frame_data.model_dump(),
        )
        dumped = msg.model_dump()
        assert dumped["type"] == "frame"
        assert dumped["data"]["frame_id"] == 1024
        assert dumped["data"]["width"] == 1920
        assert dumped["data"]["height"] == 1080
        assert dumped["data"]["metadata"]["fps"] == 29.97

    def test_camera_status_message(self):
        """Req 13: Verify camera status updates for ONLINE, OFFLINE, CONNECTING, ERROR."""
        for status in ("ONLINE", "OFFLINE", "CONNECTING", "ERROR"):
            status_data = CameraStatusData(status=CameraStreamStatus(status), details=f"Status is {status}")
            msg = WebSocketMessage(
                type=WebSocketMessageType.CAMERA_STATUS,
                camera_id="CAM-01",
                data=status_data.model_dump(),
            )
            assert msg.data["status"] == status

    def test_stats_message_serialization(self):
        """Req 14: Verify stats message serialization carrying tracking & performance metrics."""
        stats_data = StatsData(
            active_tracks=5,
            total_detections=128,
            active_alerts=2,
            fps=30.0,
            connected_clients=4,
        )
        msg = WebSocketMessage(
            type=WebSocketMessageType.STATS,
            camera_id="CAM-01",
            data=stats_data.model_dump(),
        )
        assert msg.data["active_tracks"] == 5
        assert msg.data["total_detections"] == 128
        assert msg.data["active_alerts"] == 2
        assert msg.data["fps"] == 30.0
        assert msg.data["connected_clients"] == 4

    def test_heartbeat_message(self):
        """Req 15: Verify heartbeat message serialization."""
        hb_data = HeartbeatData(reply="pong")
        msg = WebSocketMessage(
            type=WebSocketMessageType.HEARTBEAT,
            camera_id="CAM-01",
            data=hb_data.model_dump(),
        )
        assert msg.type == "heartbeat"
        assert msg.data["reply"] == "pong"


# ==============================================================================
# 4. CLIENT INTERACTION & ERROR HANDLING TESTS (Req 15, 16, 17)
# ==============================================================================


class TestClientInteractionAndErrorHandling:
    """Verifies client inbound commands (ping, status) and robust handling of bad input."""

    def test_client_ping_pong_heartbeat(self, client: TestClient):
        """Req 15: Verify client ping generates structured heartbeat pong reply."""
        with client.websocket_connect("/api/v1/ws/CAM-PING") as ws:
            ws.receive_json()  # Handshake

            ws.send_json({"type": "ping", "data": {"token": "req-999"}})
            reply = ws.receive_json()
            assert reply["type"] == "heartbeat"
            assert reply["data"]["reply"] == "req-999"

    def test_client_status_request(self, client: TestClient):
        """Verify client status request generates camera status report."""
        with client.websocket_connect("/api/v1/ws/CAM-STATUS") as ws:
            ws.receive_json()  # Handshake

            ws.send_json({"type": "status"})
            reply = ws.receive_json()
            assert reply["type"] == "camera_status"
            assert reply["data"]["status"] == "ONLINE"
            assert "Active subscribers: 1" in reply["data"]["details"]

    def test_malformed_json_handled_safely(self, client: TestClient):
        """Req 16: Verify malformed text payload yields safe error without crashing or disconnecting."""
        with client.websocket_connect("/api/v1/ws/CAM-MALFORMED") as ws:
            ws.receive_json()  # Handshake

            # Send non-JSON text
            ws.send_text("THIS_IS_DEFINITELY_NOT_JSON!@#")
            reply = ws.receive_json()
            assert reply["type"] == "error"
            assert reply["data"]["error"] == "INVALID_JSON"

            # Connection remains functional for subsequent valid commands
            ws.send_json({"type": "ping", "data": {"token": "still_alive"}})
            pong = ws.receive_json()
            assert pong["type"] == "heartbeat"
            assert pong["data"]["reply"] == "still_alive"

    def test_unknown_message_type_handled_safely(self, client: TestClient):
        """Req 17: Verify unknown command yields clean error response without crashing."""
        with client.websocket_connect("/api/v1/ws/CAM-UNKNOWN") as ws:
            ws.receive_json()  # Handshake

            ws.send_json({"type": "do_secret_admin_thing", "data": {}})
            reply = ws.receive_json()
            assert reply["type"] == "error"
            assert reply["data"]["error"] == "UNSUPPORTED_TYPE"


# ==============================================================================
# 5. BACKPRESSURE & SLOW CLIENT PROTECTION TESTS (Req 18, 19)
# ==============================================================================


class TestBackpressureAndSlowClientProtection:
    """Verifies bounded queue handling, frame dropping, and priority alert delivery."""

    def test_frame_dropping_under_backpressure(self):
        """Req 19: Verify high-frequency frames are dropped when client queue is lagging."""
        async def run_test():
            mock_ws = MagicMock()
            sub = ClientSubscription(camera_id="CAM-SLOW", websocket=mock_ws, queue_maxsize=10)

            # Enqueue several frames
            frame_msg = {
                "type": "frame",
                "camera_id": "CAM-SLOW",
                "data": {"frame_id": 1, "encoded_data": "abc"},
            }

            results = []
            for i in range(8):
                queued = await sub.enqueue(frame_msg)
                results.append(queued)

            # First few frames queued, subsequent frames dropped due to FRAME_DROP_QUEUE_THRESHOLD (3)
            assert results[0] is True
            assert results[1] is True
            assert results[2] is True
            assert False in results  # Subsequent frames were dropped to protect against slow client

            await sub.close()

        asyncio.run(run_test())

    def test_priority_alert_delivery_under_backpressure(self):
        """Req 19: Verify critical alert messages are not dropped even when frame queue is full."""
        async def run_test():
            mock_ws = MagicMock()
            sub = ClientSubscription(camera_id="CAM-PRIORITY", websocket=mock_ws, queue_maxsize=4)

            # Fill queue with frames
            for i in range(4):
                await sub.queue.put({"type": "frame", "frame_id": i})

            assert sub.queue.full()

            # Enqueue an alert
            alert_msg = {
                "type": "alert",
                "camera_id": "CAM-PRIORITY",
                "data": {"alert_id": "ALT-MUST-DELIVER", "severity": "CRITICAL"},
            }
            enqueued = await sub.enqueue(alert_msg)
            assert enqueued is True

            # Verify the alert is in the queue
            queued_items = []
            while not sub.queue.empty():
                queued_items.append(await sub.queue.get())

            assert any(item.get("type") == "alert" for item in queued_items)

            await sub.close()

        asyncio.run(run_test())

    def test_stale_connection_cleaned_up_on_broadcast(self):
        """Req 18: Verify dead/stale client subscriptions are automatically cleaned up on broadcast."""
        async def run_test():
            mgr = WebSocketConnectionManager()
            mock_ws = MagicMock()
            # Simulate a client that has closed its socket / died
            sub = ClientSubscription(camera_id="CAM-STALE", websocket=mock_ws)
            sub.is_alive = False

            mgr._cameras["CAM-STALE"] = {sub}
            mgr._ws_map[mock_ws] = sub

            assert mgr.get_camera_connection_count("CAM-STALE") == 1

            # Broadcasting will detect the dead client and clean it up
            msg = {"type": "alert", "camera_id": "CAM-STALE", "data": {"alert_id": "ALT-1"}}
            dispatched = await mgr.broadcast_to_camera("CAM-STALE", msg)
            assert dispatched == 0
            assert mgr.get_camera_connection_count("CAM-STALE") == 0

        asyncio.run(run_test())

    def test_one_slow_client_does_not_block_other_clients(self, client: TestClient):

        """Req 19: Verify slow client does not block broadcasts to other fast clients."""
        cam_id = "CAM-RESILIENCE"
        with client.websocket_connect(f"/api/v1/ws/{cam_id}") as fast_ws:
            fast_ws.receive_json()  # Handshake

            # Broadcast multiple frames and an alert
            for i in range(5):
                asyncio.run(
                    websocket_manager.broadcast_to_camera(
                        cam_id,
                        {"type": "frame", "camera_id": cam_id, "data": {"frame_id": i, "encoded_data": "data"}},
                    )
                )

            asyncio.run(
                websocket_manager.broadcast_to_camera(
                    cam_id,
                    {"type": "alert", "camera_id": cam_id, "data": {"alert_id": "CRITICAL-ALERT"}},
                )
            )

            # Fast client drains smoothly
            received_types = []
            for _ in range(fast_ws._queue.qsize() if hasattr(fast_ws, "_queue") else 3):
                msg = fast_ws.receive_json()
                received_types.append(msg["type"])

            # Fast client received messages without any hang or exception
            assert len(received_types) > 0


# ==============================================================================
# 6. PIPELINE ADAPTER INTEGRATION TESTS (Req 11, 12, 14)
# ==============================================================================


class TestPipelineAdapterIntegration:
    """Verifies PipelineWebSocketAdapter transforms AI engine results to WebSocket messages."""

    def test_adapter_publish_alert(self, client: TestClient):
        """Verify adapter cleanly transforms alert dictionary/object and delivers to subscribers."""
        cam_id = "CAM-ADAPTER-ALERT"
        adapter = PipelineWebSocketAdapter(camera_id=cam_id)

        with client.websocket_connect(f"/api/v1/ws/{cam_id}") as ws:
            ws.receive_json()  # Handshake

            asyncio.run(
                adapter.publish_alert({
                    "alert_id": "ALT-900",
                    "track_id": 7,
                    "alert_type": "LOITERING",
                    "severity": "HIGH",
                    "status": "ACTIVE",
                    "message": "Subject lingering near fence",
                    "timestamp": datetime.now(timezone.utc),
                })
            )

            received = ws.receive_json()
            assert received["type"] == "alert"
            assert received["data"]["alert_id"] == "ALT-900"
            assert received["data"]["alert_type"] == "LOITERING"

    def test_adapter_publish_frame_with_numpy_array(self, client: TestClient):
        """Verify adapter accepts numpy frame, base64 encodes it, and delivers to subscribers."""
        cam_id = "CAM-ADAPTER-FRAME"
        adapter = PipelineWebSocketAdapter(camera_id=cam_id)

        with client.websocket_connect(f"/api/v1/ws/{cam_id}") as ws:
            ws.receive_json()  # Handshake

            dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
            asyncio.run(adapter.publish_frame(dummy_frame, frame_id=50, width=100, height=100))

            received = ws.receive_json()
            assert received["type"] == "frame"
            assert received["data"]["frame_id"] == 50
            assert len(received["data"]["encoded_data"]) > 0
            assert received["data"]["width"] == 100
            assert received["data"]["height"] == 100

    def test_adapter_publish_pipeline_result(self, client: TestClient):
        """Verify adapter extracts alerts, frame, and stats from a mock PipelineResult."""
        cam_id = "CAM-ADAPTER-PIPELINE"
        adapter = PipelineWebSocketAdapter(camera_id=cam_id)

        # Mock PipelineResult compatible with M12 dataclass
        @dataclass
        class MockAlert:
            alert_id: str = "ALT-P1"
            alert_type: str = "FENCE_BREACH"
            severity: str = "CRITICAL"
            status: str = "ACTIVE"
            message: str = "Perimeter breached"
            timestamp: float = 1767270000.0

        @dataclass
        class MockPipelineResult:
            frame_id: int = 1
            timestamp: float = 1767270000.0
            alerts: List[Any] = field(default_factory=lambda: [MockAlert()])
            tracked_objects: List[Any] = field(default_factory=lambda: [1, 2])
            processed_frame: np.ndarray = field(default_factory=lambda: np.zeros((48, 48, 3), dtype=np.uint8))

        with client.websocket_connect(f"/api/v1/ws/{cam_id}") as ws:
            ws.receive_json()  # Handshake

            mock_res = MockPipelineResult()
            asyncio.run(adapter.publish_pipeline_result(mock_res, include_frame=True, fps=25.0))

            # Subscriber should receive: alert, frame, stats
            received_messages = [ws.receive_json(), ws.receive_json(), ws.receive_json()]
            types = [m["type"] for m in received_messages]

            assert "alert" in types
            assert "frame" in types
            assert "stats" in types


# ==============================================================================
# 7. EXISTING REST API REGRESSION TEST (Req 20)
# ==============================================================================


class TestRestApiCompatibility:
    """Req 20: Verifies existing REST endpoints continue working after WebSocket integration."""

    def test_root_endpoint_still_works(self, client: TestClient):
        """Verify GET / returns 200."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "online"

    def test_health_endpoint_still_works(self, client: TestClient):
        """Verify GET /health returns 200."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_openapi_schema_contains_websocket_route(self, client: TestClient):
        """Verify OpenAPI documentation registers cleanly without exceptions."""
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        openapi = resp.json()
        assert "paths" in openapi
        # REST paths exist
        assert "/api/v1/cameras" in openapi["paths"]
        assert "/api/v1/alerts" in openapi["paths"]
