"""Pydantic schemas for Security Alert entities."""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AlertSeverity, AlertStatus, AlertType
from app.schemas.common import PaginatedResponse


class AlertResponse(BaseModel):
    """Schema representing a security alert."""

    id: int = Field(..., description="Internal surrogate primary key.")
    alert_id: str = Field(..., description="Unique external alert identifier (e.g. 'ALT-00001').")
    camera_id: Optional[int] = Field(None, description="Source camera foreign key.")
    track_id: Optional[int] = Field(None, description="Associated track foreign key.")
    event_id: Optional[int] = Field(None, description="Triggering source event foreign key.")
    zone_id: Optional[int] = Field(None, description="Associated zone foreign key.")
    alert_type: AlertType = Field(..., description="Alert category (FENCE_BREACH, LOITERING).")
    severity: AlertSeverity = Field(..., description="Alert severity ranking.")
    status: AlertStatus = Field(..., description="Lifecycle status (ACTIVE, ACKNOWLEDGED, RESOLVED).")
    message: str = Field(..., description="Concise human-readable alert message.")
    alert_timestamp: datetime = Field(..., description="Timestamp when the alert was triggered (UTC).")
    alert_metadata: Dict[str, Any] = Field(default_factory=dict, description="Contextual telemetry and spatial coordinates.")
    acknowledged_at: Optional[datetime] = Field(None, description="Timestamp when operator acknowledged this alert.")
    acknowledged_by: Optional[str] = Field(None, description="Operator identity who acknowledged.")
    resolved_at: Optional[datetime] = Field(None, description="Timestamp when alert was resolved.")
    resolved_by: Optional[str] = Field(None, description="Operator identity who resolved.")
    created_at: datetime = Field(..., description="Record creation UTC timestamp.")
    updated_at: datetime = Field(..., description="Record last update UTC timestamp.")

    model_config = ConfigDict(from_attributes=True)


class AlertUpdate(BaseModel):
    """Request schema for updating/transitioning an alert's lifecycle status."""

    status: Optional[AlertStatus] = Field(None, description="Target lifecycle status (ACKNOWLEDGED or RESOLVED).")
    acknowledged_by: Optional[str] = Field(None, max_length=128, description="Operator identity performing acknowledgement.")
    resolved_by: Optional[str] = Field(None, max_length=128, description="Operator identity performing resolution.")

    model_config = ConfigDict(extra="forbid")


class AlertListResponse(PaginatedResponse[AlertResponse]):
    """Paginated list of alerts."""
    pass
