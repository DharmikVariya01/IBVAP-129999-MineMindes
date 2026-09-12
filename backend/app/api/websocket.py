"""WebSocket API Endpoint for IBVAP Module 17.

Provides the real-time bidirectional streaming endpoint under:
WS /api/v1/ws/{camera_id}

Handles client lifecycle, input validation, keepalive heartbeats,
and clean disconnection without leaking server exceptions or secrets.
"""

import json
import logging
import re
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.schemas.websocket import (
    CameraStatusData,
    CameraStreamStatus,
    ClientMessage,
    ErrorData,
    HeartbeatData,
    WebSocketMessage,
    WebSocketMessageType,
)
from app.services.websocket_manager import websocket_manager

logger = logging.getLogger("ibvap.api.websocket")

router = APIRouter(tags=["WebSocket"])

# Camera ID validation: alphanumeric, hyphens, and underscores, 1–64 characters
CAMERA_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


@router.websocket("/ws/{camera_id}")
async def websocket_camera_stream(websocket: WebSocket, camera_id: str):
    """Real-time WebSocket endpoint for camera stream video, alerts, and analytics.

    Subscribes the connecting client to real-time events for the specified camera.
    """
    # 1. Validate camera_id input
    if not camera_id or not CAMERA_ID_PATTERN.match(camera_id):
        logger.warning("Rejected WebSocket connection with invalid camera_id: %r", camera_id)
        # Cannot use HTTP exceptions on WebSocket; close with policy violation
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid camera_id format")
        return

    # 2. Register connection in manager
    try:
        subscription = await websocket_manager.connect(camera_id, websocket)
    except Exception as exc:
        logger.error("Failed to accept and register WebSocket for camera %s: %s", camera_id, exc)
        return

    # 3. Client Message Inbound Loop
    try:
        while True:
            raw_text = await websocket.receive_text()

            # Parse incoming text as JSON
            try:
                payload = json.loads(raw_text)
            except (json.JSONDecodeError, UnicodeDecodeError):
                error_msg = WebSocketMessage(
                    type=WebSocketMessageType.ERROR,
                    camera_id=camera_id,
                    data=ErrorData(
                        error="INVALID_JSON",
                        message="Malformed JSON received from client",
                    ).model_dump(),
                )
                await subscription.enqueue(error_msg.model_dump())
                continue

            if not isinstance(payload, dict):
                error_msg = WebSocketMessage(
                    type=WebSocketMessageType.ERROR,
                    camera_id=camera_id,
                    data=ErrorData(
                        error="INVALID_PAYLOAD",
                        message="WebSocket payload must be a JSON object",
                    ).model_dump(),
                )
                await subscription.enqueue(error_msg.model_dump())
                continue

            # Validate client message structure
            msg_type = payload.get("type")
            if not msg_type:
                error_msg = WebSocketMessage(
                    type=WebSocketMessageType.ERROR,
                    camera_id=camera_id,
                    data=ErrorData(
                        error="MISSING_TYPE",
                        message="Message object missing required 'type' field",
                    ).model_dump(),
                )
                await subscription.enqueue(error_msg.model_dump())
                continue

            # Process supported client commands
            cmd_type = str(msg_type).lower()

            if cmd_type == "ping":
                # Reply with heartbeat
                reply_val = payload.get("data", {}).get("token", "pong") if isinstance(payload.get("data"), dict) else "pong"
                hb_msg = WebSocketMessage(
                    type=WebSocketMessageType.HEARTBEAT,
                    camera_id=camera_id,
                    data=HeartbeatData(reply=reply_val).model_dump(),
                )
                await subscription.enqueue(hb_msg.model_dump())

            elif cmd_type in ("status", "status_request"):
                # Report current camera stream status and active subscriber count
                sub_count = websocket_manager.get_camera_connection_count(camera_id)
                status_msg = WebSocketMessage(
                    type=WebSocketMessageType.CAMERA_STATUS,
                    camera_id=camera_id,
                    data=CameraStatusData(
                        status=CameraStreamStatus.ONLINE,
                        details=f"Active subscribers: {sub_count}",
                    ).model_dump(),
                )
                await subscription.enqueue(status_msg.model_dump())

            else:
                # Unsupported client command: report clean error without disconnecting
                logger.debug("Received unsupported command '%s' from client %s", cmd_type, subscription.client_id)
                error_msg = WebSocketMessage(
                    type=WebSocketMessageType.ERROR,
                    camera_id=camera_id,
                    data=ErrorData(
                        error="UNSUPPORTED_TYPE",
                        message=f"Unsupported client message type '{msg_type}'",
                    ).model_dump(),
                )
                await subscription.enqueue(error_msg.model_dump())

    except (WebSocketDisconnect, ConnectionResetError, RuntimeError):
        logger.info("Client %s cleanly disconnected from camera %s", subscription.client_id, camera_id)
    except Exception as exc:
        logger.warning(
            "Unexpected error on WebSocket connection for camera %s (client %s): %s",
            camera_id,
            subscription.client_id,
            exc,
        )
    finally:
        await websocket_manager.disconnect(camera_id, websocket)
