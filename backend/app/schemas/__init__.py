"""Pydantic schemas package for IBVAP REST API.

Exports request and response models for cameras, alerts, tracks, events, evidence, and stats.
"""

from app.schemas.alert import AlertListResponse, AlertResponse, AlertUpdate
from app.schemas.camera import CameraListResponse, CameraResponse
from app.schemas.common import PaginatedResponse
from app.schemas.event import EventResponse
from app.schemas.evidence import EvidenceResponse
from app.schemas.stats import StatsResponse
from app.schemas.track import TrackResponse
from app.schemas.websocket import (
    AlertData,
    CameraStatusData,
    CameraStreamStatus,
    ClientMessage,
    ConnectionData,
    FrameData,
    HeartbeatData,
    StatsData,
    WebSocketMessage,
    WebSocketMessageType,
)

__all__ = [
    "PaginatedResponse",
    "CameraResponse",
    "CameraListResponse",
    "AlertResponse",
    "AlertListResponse",
    "AlertUpdate",
    "TrackResponse",
    "EventResponse",
    "EvidenceResponse",
    "StatsResponse",
    "WebSocketMessage",
    "WebSocketMessageType",
    "CameraStreamStatus",
    "ConnectionData",
    "HeartbeatData",
    "FrameData",
    "AlertData",
    "CameraStatusData",
    "StatsData",
    "ClientMessage",
]

