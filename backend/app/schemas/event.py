"""Pydantic schemas for Detection Event entities."""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EventType


class EventResponse(BaseModel):
    """Schema representing a pipeline detection event (M8/M9)."""

    id: int = Field(..., description="Internal surrogate primary key.")
    event_id: Optional[str] = Field(None, description="Optional business-level event identifier (e.g. 'EVT-00001').")
    camera_id: Optional[int] = Field(None, description="Camera where the event occurred.")
    track_id: Optional[int] = Field(None, description="Track associated with the event.")
    zone_id: Optional[int] = Field(None, description="Zone where the event occurred.")
    event_type: EventType = Field(..., description="Type of event (FENCE_BREACH, LOITERING, etc.).")
    frame_id: Optional[int] = Field(None, description="Video frame index where the event triggered.")
    timestamp: datetime = Field(..., description="Detection event timestamp (UTC).")
    details: Dict[str, Any] = Field(default_factory=dict, description="Contextual event metadata.")
    created_at: datetime = Field(..., description="Record creation UTC timestamp.")

    model_config = ConfigDict(from_attributes=True)
