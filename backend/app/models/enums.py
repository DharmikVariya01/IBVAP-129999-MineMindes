"""Canonical enumeration definitions for IBVAP persistent data models.

Preserves exact 1:1 conceptual compatibility with AI engine modules:
- CameraSourceType -> M1 SourceType
- ZoneType -> M7 ZoneType
- AlertType -> M10 AlertType
- AlertSeverity -> M10 AlertSeverity
- AlertStatus -> M10 AlertStatus
"""

from enum import Enum


class CameraSourceType(str, Enum):
    """Supported video ingestion source types."""

    WEBCAM = "webcam"
    VIDEO = "video"
    RTSP = "rtsp"


class CameraStatus(str, Enum):
    """Operating status of a surveillance camera."""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"


class TrackStatus(str, Enum):
    """Lifecycle status of a tracked object session."""

    ACTIVE = "ACTIVE"
    LOST = "LOST"
    COMPLETED = "COMPLETED"


class ZoneType(str, Enum):
    """Spatial zone classification types (M7)."""

    NORMAL = "NORMAL"
    SENSITIVE = "SENSITIVE"
    RESTRICTED = "RESTRICTED"
    FENCE = "FENCE"


class EventType(str, Enum):
    """Pipeline detection event categories."""

    FENCE_BREACH = "FENCE_BREACH"
    LOITERING = "LOITERING"
    ZONE_ENTRY = "ZONE_ENTRY"
    ZONE_EXIT = "ZONE_EXIT"
    MOTION = "MOTION"


class AlertType(str, Enum):
    """Security alert classification types (M10)."""

    FENCE_BREACH = "FENCE_BREACH"
    LOITERING = "LOITERING"


class AlertSeverity(str, Enum):
    """Security alert severity levels (M10)."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AlertStatus(str, Enum):
    """Security alert lifecycle status (M10)."""

    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
