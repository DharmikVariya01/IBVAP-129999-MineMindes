"""Zone SQLAlchemy ORM model for spatial surveillance regions (M7)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional, Tuple

from sqlalchemy import Boolean, Enum as SQLEnum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import ZoneType

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.camera import Camera
    from app.models.event import Event


class Zone(Base, TimestampMixin):
    """Spatial surveillance polygon zone matching M7 Zone entity."""

    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    zone_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="Unique zone identifier (e.g., 'ZONE-001', 'FENCE-NORTH')",
    )
    camera_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("cameras.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="Optional camera association if zone is camera-specific",
    )
    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Descriptive zone name (e.g., 'Restricted Perimeter')",
    )
    zone_type: Mapped[ZoneType] = mapped_column(
        SQLEnum(ZoneType, name="zone_type_enum", native_enum=False),
        nullable=False,
        comment="Zone classification type (NORMAL, SENSITIVE, RESTRICTED, FENCE)",
    )
    polygon: Mapped[List[List[int]]] = mapped_column(
        JSON,
        nullable=False,
        comment="Deterministic list of [x, y] vertex coordinates in pixel space",
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Evaluation priority (higher rank evaluated first during overlap)",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether the zone is currently active for surveillance checks",
    )
    color: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="Optional overlay color representation (e.g. '(0, 200, 0)' or hex)",
    )

    # Relationships
    camera: Mapped[Optional[Camera]] = relationship("Camera", back_populates="zones")
    events: Mapped[List[Event]] = relationship("Event", back_populates="zone")
    alerts: Mapped[List[Alert]] = relationship("Alert", back_populates="zone")

    @property
    def polygon_tuples(self) -> Tuple[Tuple[int, int], ...]:
        """Convert stored JSON polygon to M7 compatible tuple-of-tuples format."""
        if not self.polygon:
            return ()
        return tuple((int(pt[0]), int(pt[1])) for pt in self.polygon)

    def __repr__(self) -> str:
        type_val = self.zone_type.value if getattr(self, "zone_type", None) is not None else "None"
        return (
            f"<Zone(id={self.id}, zone_id='{self.zone_id}', name='{self.name}', "
            f"type='{type_val}', priority={self.priority}, active={self.is_active})>"
        )
