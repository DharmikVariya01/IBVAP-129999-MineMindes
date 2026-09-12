"""Pydantic schemas for IBVAP Module 17 Real-Time WebSocket Communication.

Defines standardized, strictly validated message formats for real-time video/AI streaming:
- connection (client connect acknowledgement)
- heartbeat (keep-alive / ping-pong)
- frame (encoded video frames with metadata)
- alert (real-time security alert events)
- camera_status (ONLINE, OFFLINE, CONNECTING, ERROR)
- stats (real-time active tracking and performance metrics)
- error (safe error reporting to client)
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


def _current_utc_iso() -> str:
    """Return current UTC timestamp in ISO 8601 string format with trailing Z."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class WebSocketMessageType(str, Enum):
    """Supported real-time message types for IBVAP WebSocket communication."""

    CONNECTION = "connection"
    HEARTBEAT = "heartbeat"
    FRAME = "frame"
    ALERT = "alert"
    CAMERA_STATUS = "camera_status"
    STATS = "stats"
    ERROR = "error"


class CameraStreamStatus(str, Enum):
    """Operating status of a camera video stream in the real-time layer."""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    CONNECTING = "CONNECTING"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
# Specific Data Payloads
# ---------------------------------------------------------------------------

class ConnectionData(BaseModel):
    """Payload for connection handshake acknowledgment messages."""

    status: str = Field(default="connected", description="Connection status indicator.")
    client_id: Optional[str] = Field(None, description="Unique client session identifier.")
    message: str = Field(default="Connected to camera stream", description="Status message.")

    model_config = ConfigDict(extra="ignore")


class HeartbeatData(BaseModel):
    """Payload for lightweight heartbeat and ping/pong messages."""

    reply: Optional[str] = Field(None, description="Optional ping/pong payload or echo token.")

    model_config = ConfigDict(extra="ignore")


class FrameData(BaseModel):
    """Payload for real-time video stream frames."""

    frame_id: Optional[int] = Field(None, description="Sequential frame counter/identifier.")
    encoded_data: str = Field(..., description="Base64-encoded video frame (JPEG/PNG).")
    width: Optional[int] = Field(None, description="Frame width in pixels.")
    height: Optional[int] = Field(None, description="Frame height in pixels.")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional per-frame analytics metadata.")

    model_config = ConfigDict(extra="ignore")


class AlertData(BaseModel):
    """Payload for real-time security alerts compatible with M10/M16."""

    alert_id: Union[int, str] = Field(..., description="Unique alert identifier.")
    camera_id: str = Field(..., description="Camera identifier where alert originated.")
    track_id: Optional[int] = Field(None, description="Associated track ID if applicable.")
    alert_type: str = Field(..., description="Security alert category (e.g. FENCE_BREACH, LOITERING).")
    severity: str = Field(..., description="Alert severity level (CRITICAL, HIGH, MEDIUM, LOW).")
    status: str = Field(..., description="Alert lifecycle state (ACTIVE, ACKNOWLEDGED, RESOLVED).")
    message: str = Field(..., description="Human-readable alert description.")
    timestamp: str = Field(..., description="Alert occurrence UTC timestamp in ISO 8601 format.")
    zone_info: Optional[Dict[str, Any]] = Field(None, description="Associated zone or boundary details.")
    evidence_reference: Optional[str] = Field(None, description="Evidence record reference or file path.")

    model_config = ConfigDict(extra="ignore")


class CameraStatusData(BaseModel):
    """Payload for real-time camera operational status notifications."""

    status: CameraStreamStatus = Field(..., description="Current camera status (ONLINE, OFFLINE, CONNECTING, ERROR).")
    details: Optional[str] = Field(None, description="Optional supplementary status details or error string.")

    model_config = ConfigDict(extra="ignore")


class StatsData(BaseModel):
    """Payload for real-time pipeline and streaming performance statistics."""

    active_tracks: int = Field(default=0, ge=0, description="Current number of actively tracked entities.")
    total_detections: int = Field(default=0, ge=0, description="Cumulative detections in current session.")
    active_alerts: int = Field(default=0, ge=0, description="Count of currently active unresolved alerts.")
    fps: float = Field(default=0.0, ge=0.0, description="Current processing frames per second.")
    connected_clients: int = Field(default=0, ge=0, description="Active WebSocket subscribers for camera.")

    model_config = ConfigDict(extra="ignore")


class ErrorData(BaseModel):
    """Payload for safe client error messaging."""

    error: str = Field(..., description="Short error code or descriptor.")
    message: str = Field(..., description="Sanitized human-readable explanation.")

    model_config = ConfigDict(extra="ignore")


# ---------------------------------------------------------------------------
# Canonical WebSocket Message Envelope
# ---------------------------------------------------------------------------

class WebSocketMessage(BaseModel):
    """Canonical WebSocket message envelope for all IBVAP real-time messages.

    Every message strictly guarantees:
    - type: The category of message (connection, heartbeat, frame, alert, etc.)
    - timestamp: ISO 8601 UTC timestamp string
    - camera_id: External camera identifier
    - data: Structured payload dictionary or typed data
    """

    type: WebSocketMessageType = Field(..., description="Category of the real-time message.")
    timestamp: str = Field(default_factory=_current_utc_iso, description="UTC ISO 8601 timestamp.")
    camera_id: str = Field(..., description="Associated external camera identifier.")
    data: Dict[str, Any] = Field(default_factory=dict, description="Structured message payload.")

    model_config = ConfigDict(extra="ignore")


# ---------------------------------------------------------------------------
# Incoming Client Message Schema
# ---------------------------------------------------------------------------

class ClientMessage(BaseModel):
    """Schema for messages sent from connected WebSocket clients to server."""

    type: str = Field(..., description="Client message command type (e.g. ping, status).")
    camera_id: Optional[str] = Field(None, description="Optional camera identifier target.")
    data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional command data payload.")

    model_config = ConfigDict(extra="ignore")
