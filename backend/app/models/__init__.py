"""SQLAlchemy ORM models package for IBVAP.

Exports:
- Base: Declarative base class for all persistent entities.
- Camera: Surveillance camera input streams.
- Track: Persistent object track records (ByteTrack M4/M5).
- Zone: Spatial surveillance polygons (M7).
- Event: Pipeline detection events (Fence Breach M8, Loitering M9).
- Alert: Security alerts and lifecycle management (M10).
- Evidence: Captured evidence image records (M11).
- Enums: CameraSourceType, CameraStatus, TrackStatus, ZoneType, EventType,
         AlertType, AlertSeverity, AlertStatus.
"""

from app.models.alert import Alert
from app.models.base import Base, TimestampMixin, utc_now
from app.models.camera import Camera
from app.models.enums import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    CameraSourceType,
    CameraStatus,
    EventType,
    TrackStatus,
    ZoneType,
)
from app.models.event import Event
from app.models.evidence import Evidence
from app.models.track import Track
from app.models.zone import Zone

__all__ = [
    "Base",
    "TimestampMixin",
    "utc_now",
    "Camera",
    "Track",
    "Zone",
    "Event",
    "Alert",
    "Evidence",
    "CameraSourceType",
    "CameraStatus",
    "TrackStatus",
    "ZoneType",
    "EventType",
    "AlertType",
    "AlertSeverity",
    "AlertStatus",
]
