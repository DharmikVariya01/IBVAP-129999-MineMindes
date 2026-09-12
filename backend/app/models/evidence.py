"""Evidence SQLAlchemy ORM model for captured alert frames (M11)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.camera import Camera
    from app.models.track import Track


class Evidence(Base):
    """Evidence image capture record matching M11 EvidenceRecord entity."""

    __tablename__ = "evidence"

    __table_args__ = (
        Index("ix_evidence_alert_id", "alert_id"),
        Index("ix_evidence_camera_id", "camera_id"),
        Index("ix_evidence_track_id", "track_id"),
        Index("ix_evidence_capture_timestamp", "capture_timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evidence_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="Unique external evidence identifier (e.g., 'EVD-00001')",
    )
    alert_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
        comment="Associated alert foreign key",
    )
    camera_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("cameras.id", ondelete="SET NULL"),
        nullable=True,
        comment="Source camera foreign key, if known",
    )
    track_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("tracks.id", ondelete="SET NULL"),
        nullable=True,
        comment="Suspect track foreign key, if known",
    )
    file_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        comment="Absolute or relative filesystem path to the saved JPEG image",
    )
    filename: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        comment="Base filename of the evidence frame",
    )
    frame_width: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Horizontal resolution in pixels",
    )
    frame_height: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Vertical resolution in pixels",
    )
    capture_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
        comment="Timestamp when evidence image was captured and saved (UTC)",
    )
    alert_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Original detection timestamp of the associated alert",
    )
    evidence_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Contextual metadata (bounding box, detection confidence, alert type, severity)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    alert: Mapped[Alert] = relationship("Alert", back_populates="evidence_records")
    camera: Mapped[Optional[Camera]] = relationship("Camera", back_populates="evidence_records")
    track: Mapped[Optional[Track]] = relationship("Track", back_populates="evidence_records")

    @property
    def frame_dimensions(self) -> Tuple[int, int]:
        """Return (width, height) resolution tuple matching M11 format."""
        return (self.frame_width, self.frame_height)

    @property
    def width(self) -> int:
        """Return horizontal frame width in pixels."""
        return self.frame_width

    @property
    def height(self) -> int:
        """Return vertical frame height in pixels."""
        return self.frame_height

    def __repr__(self) -> str:
        return (
            f"<Evidence(id={self.id}, evidence_id='{self.evidence_id}', "
            f"alert_id={self.alert_id}, filename='{self.filename}')>"
        )
