"""Pydantic schemas for Track entities."""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TrackStatus


class TrackResponse(BaseModel):
    """Schema representing a persistent tracked object."""

    id: int = Field(..., description="Internal surrogate primary key.")
    track_id: int = Field(..., description="Persistent identifier assigned by ByteTrack (M4).")
    camera_id: Optional[int] = Field(None, description="Associated camera foreign key.")
    class_id: int = Field(..., description="COCO class identifier (e.g. 0 for person).")
    class_name: str = Field(..., description="Human-readable object class label.")
    first_seen: datetime = Field(..., description="Timestamp of the very first observation (UTC).")
    last_seen: datetime = Field(..., description="Timestamp of the most recent observation (UTC).")
    frame_count: int = Field(..., ge=1, description="Total frames in which this track has been observed.")
    last_confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence from most recent frame.")
    bbox_x1: Optional[int] = Field(None, description="Bounding box top-left x.")
    bbox_y1: Optional[int] = Field(None, description="Bounding box top-left y.")
    bbox_x2: Optional[int] = Field(None, description="Bounding box bottom-right x.")
    bbox_y2: Optional[int] = Field(None, description="Bounding box bottom-right y.")
    last_center_x: Optional[float] = Field(None, description="Most recent centroid x.")
    last_center_y: Optional[float] = Field(None, description="Most recent centroid y.")
    status: TrackStatus = Field(..., description="Tracking lifecycle state (ACTIVE, LOST, COMPLETED).")
    observation_metadata: Optional[Dict[str, Any]] = Field(None, description="Additional observation diagnostics or history.")
    created_at: datetime = Field(..., description="Creation UTC timestamp.")
    updated_at: datetime = Field(..., description="Last update UTC timestamp.")
    events_count: Optional[int] = Field(None, description="Count of associated events.")
    alerts_count: Optional[int] = Field(None, description="Count of associated alerts.")

    model_config = ConfigDict(from_attributes=True)
