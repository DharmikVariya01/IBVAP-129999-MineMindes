"""Camera SQLAlchemy ORM model for surveillance video sources."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Enum as SQLEnum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import CameraSourceType, CameraStatus

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.event import Event
    from app.models.evidence import Evidence
    from app.models.track import Track
    from app.models.zone import Zone


class Camera(Base, TimestampMixin):
    """Surveillance camera entity representing a video stream or hardware input."""

    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="Unique external camera identifier (e.g., 'CAM-01', 'GATE-NORTH')",
    )
    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Descriptive human-readable camera name",
    )
    source_type: Mapped[CameraSourceType] = mapped_column(
        SQLEnum(CameraSourceType, name="camera_source_type_enum", native_enum=False),
        default=CameraSourceType.VIDEO,
        nullable=False,
        comment="Type of source input (webcam, video, rtsp)",
    )
    source_reference: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="Stream URI, device index, or file path",
    )
    location: Mapped[Optional[str]] = mapped_column(
        String(256),
        nullable=True,
        comment="Physical location or operational sector description",
    )
    status: Mapped[CameraStatus] = mapped_column(
        SQLEnum(CameraStatus, name="camera_status_enum", native_enum=False),
        default=CameraStatus.ONLINE,
        nullable=False,
        comment="Current operational status (ONLINE, OFFLINE, ERROR)",
    )

    # Relationships
    tracks: Mapped[List[Track]] = relationship(
        "Track",
        back_populates="camera",
        cascade="all, delete-orphan",
    )
    events: Mapped[List[Event]] = relationship(
        "Event",
        back_populates="camera",
        cascade="all, delete-orphan",
    )
    alerts: Mapped[List[Alert]] = relationship(
        "Alert",
        back_populates="camera",
        cascade="all, delete-orphan",
    )
    evidence_records: Mapped[List[Evidence]] = relationship(
        "Evidence",
        back_populates="camera",
    )
    zones: Mapped[List[Zone]] = relationship(
        "Zone",
        back_populates="camera",
    )

    def __repr__(self) -> str:
        status_val = self.status.value if getattr(self, "status", None) is not None else "None"
        return f"<Camera(id={self.id}, camera_id='{self.camera_id}', name='{self.name}', status='{status_val}')>"
