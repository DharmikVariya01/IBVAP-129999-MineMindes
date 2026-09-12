"""Event SQLAlchemy ORM model for pipeline detection events (M8/M9)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utc_now
from app.models.enums import EventType

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.camera import Camera
    from app.models.track import Track
    from app.models.zone import Zone


class Event(Base):
    """Pipeline detection event record reflecting M8 FenceBreachEvent and M9 LoiteringEvent."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=True,
        comment="Optional business-level event identifier (e.g. 'EVT-00001')",
    )
    camera_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("cameras.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
        comment="Camera where the event occurred",
    )
    track_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("tracks.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="Track associated with the event, if applicable",
    )
    zone_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("zones.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="Zone where the event occurred, if applicable",
    )
    event_type: Mapped[EventType] = mapped_column(
        SQLEnum(EventType, name="event_type_enum", native_enum=False),
        index=True,
        nullable=False,
        comment="Type of event (FENCE_BREACH, LOITERING, etc.)",
    )
    frame_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Video frame index where the event triggered",
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        index=True,
        nullable=False,
        comment="Detection event timestamp (UTC)",
    )
    details: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Contextual metadata (duration, displacement, breach_count, states)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    camera: Mapped[Optional[Camera]] = relationship("Camera", back_populates="events")
    track: Mapped[Optional[Track]] = relationship("Track", back_populates="events")
    zone: Mapped[Optional[Zone]] = relationship("Zone", back_populates="events")
    alerts: Mapped[List[Alert]] = relationship("Alert", back_populates="event")

    def __repr__(self) -> str:
        type_val = self.event_type.value if getattr(self, "event_type", None) is not None else "None"
        return (
            f"<Event(id={self.id}, type='{type_val}', "
            f"camera_id={self.camera_id}, track_id={self.track_id}, ts='{self.timestamp}')>"
        )
