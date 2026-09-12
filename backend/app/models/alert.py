"""Alert SQLAlchemy ORM model for security alerts (M10)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, utc_now
from app.models.enums import AlertSeverity, AlertStatus, AlertType

if TYPE_CHECKING:
    from app.models.camera import Camera
    from app.models.event import Event
    from app.models.evidence import Evidence
    from app.models.track import Track
    from app.models.zone import Zone


class Alert(Base, TimestampMixin):
    """Security alert record matching M10 Alert entity."""

    __tablename__ = "alerts"

    __table_args__ = (
        Index("ix_alerts_status_severity", "status", "severity"),
        Index("ix_alerts_camera_timestamp", "camera_id", "alert_timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="Unique external alert identifier (e.g. 'ALT-00001')",
    )
    camera_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("cameras.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
        comment="Source camera foreign key",
    )
    track_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("tracks.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="Associated track foreign key",
    )
    event_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("events.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="Triggering source event foreign key",
    )
    zone_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("zones.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="Associated zone foreign key",
    )
    alert_type: Mapped[AlertType] = mapped_column(
        SQLEnum(AlertType, name="alert_type_enum", native_enum=False),
        index=True,
        nullable=False,
        comment="Alert category (FENCE_BREACH, LOITERING)",
    )
    severity: Mapped[AlertSeverity] = mapped_column(
        SQLEnum(AlertSeverity, name="alert_severity_enum", native_enum=False),
        index=True,
        nullable=False,
        comment="Alert severity ranking (CRITICAL, HIGH, MEDIUM, LOW)",
    )
    status: Mapped[AlertStatus] = mapped_column(
        SQLEnum(AlertStatus, name="alert_status_enum", native_enum=False),
        default=AlertStatus.ACTIVE,
        index=True,
        nullable=False,
        comment="Lifecycle status (ACTIVE, ACKNOWLEDGED, RESOLVED)",
    )
    message: Mapped[str] = mapped_column(
        String(512),
        default="",
        nullable=False,
        comment="Concise human-readable alert message",
    )
    alert_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        index=True,
        nullable=False,
        comment="Timestamp when the alert was triggered (UTC)",
    )
    alert_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Contextual telemetry, diagnostics, and spatial coordinates",
    )

    # Lifecycle management timestamps & audit
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when operator acknowledged this alert",
    )
    acknowledged_by: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="Operator identity who acknowledged",
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when alert was resolved",
    )
    resolved_by: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="Operator identity who resolved",
    )

    # Relationships
    camera: Mapped[Optional[Camera]] = relationship("Camera", back_populates="alerts")
    track: Mapped[Optional[Track]] = relationship("Track", back_populates="alerts")
    event: Mapped[Optional[Event]] = relationship("Event", back_populates="alerts")
    zone: Mapped[Optional[Zone]] = relationship("Zone", back_populates="alerts")
    evidence_records: Mapped[List[Evidence]] = relationship(
        "Evidence",
        back_populates="alert",
        cascade="all, delete-orphan",
    )

    @property
    def is_active(self) -> bool:
        """Return True if alert status is ACTIVE."""
        return self.status == AlertStatus.ACTIVE

    def __repr__(self) -> str:
        type_val = self.alert_type.value if getattr(self, "alert_type", None) is not None else "None"
        sev_val = self.severity.value if getattr(self, "severity", None) is not None else "None"
        status_val = self.status.value if getattr(self, "status", None) is not None else "None"
        return (
            f"<Alert(id={self.id}, alert_id='{self.alert_id}', type='{type_val}', "
            f"severity='{sev_val}', status='{status_val}')>"
        )
