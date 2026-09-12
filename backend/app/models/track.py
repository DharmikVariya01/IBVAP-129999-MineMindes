"""Track SQLAlchemy ORM model for persistent object tracking (M4/M5)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy import DateTime, Enum as SQLEnum, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import TrackStatus

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.camera import Camera
    from app.models.event import Event
    from app.models.evidence import Evidence


class Track(Base, TimestampMixin):
    """Persistent object tracking record reflecting M4 TrackedObject and M5 TrackMemory."""

    __tablename__ = "tracks"

    __table_args__ = (
        Index("ix_tracks_camera_track_id", "camera_id", "track_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_id: Mapped[int] = mapped_column(
        Integer,
        index=True,
        nullable=False,
        comment="Persistent identifier assigned by ByteTrack (M4)",
    )
    camera_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("cameras.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
        comment="Associated camera foreign key",
    )
    class_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="COCO class identifier (e.g. 0 for person)",
    )
    class_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Human-readable object class label (e.g. 'person', 'car')",
    )
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Timestamp of the very first observation",
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Timestamp of the most recent observation",
    )
    frame_count: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="Total frames in which this track has been observed",
    )
    last_confidence: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        comment="Detection confidence from most recent frame in [0.0, 1.0]",
    )

    # Bounding box coordinates (M4 TrackedObject x1, y1, x2, y2)
    bbox_x1: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bbox_y1: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bbox_x2: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bbox_y2: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Centroid coordinates (M5 PositionalObservation center_x, center_y)
    last_center_x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_center_y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    status: Mapped[TrackStatus] = mapped_column(
        SQLEnum(TrackStatus, name="track_status_enum", native_enum=False),
        default=TrackStatus.ACTIVE,
        nullable=False,
        comment="Current tracking state (ACTIVE, LOST, COMPLETED)",
    )
    observation_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        nullable=True,
        comment="Additional observation diagnostics or history summary",
    )

    # Relationships
    camera: Mapped[Optional[Camera]] = relationship("Camera", back_populates="tracks")
    events: Mapped[List[Event]] = relationship("Event", back_populates="track")
    alerts: Mapped[List[Alert]] = relationship("Alert", back_populates="track")
    evidence_records: Mapped[List[Evidence]] = relationship("Evidence", back_populates="track")

    @property
    def last_bbox(self) -> Optional[Tuple[int, int, int, int]]:
        """Return bounding box tuple (x1, y1, x2, y2) if coordinates exist."""
        if (
            self.bbox_x1 is not None
            and self.bbox_y1 is not None
            and self.bbox_x2 is not None
            and self.bbox_y2 is not None
        ):
            return (self.bbox_x1, self.bbox_y1, self.bbox_x2, self.bbox_y2)
        return None

    @property
    def last_center(self) -> Optional[Tuple[float, float]]:
        """Return centroid tuple (cx, cy) if coordinates exist."""
        if self.last_center_x is not None and self.last_center_y is not None:
            return (self.last_center_x, self.last_center_y)
        return None

    def __repr__(self) -> str:
        status_val = self.status.value if getattr(self, "status", None) is not None else "None"
        return (
            f"<Track(id={self.id}, track_id={self.track_id}, class_name='{self.class_name}', "
            f"camera_id={self.camera_id}, status='{status_val}')>"
        )
