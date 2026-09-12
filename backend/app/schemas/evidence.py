"""Pydantic schemas for Evidence entities."""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class EvidenceResponse(BaseModel):
    """Schema representing an evidence capture record."""

    id: int = Field(..., description="Internal surrogate primary key.")
    evidence_id: str = Field(..., description="Unique external evidence identifier (e.g. 'EVD-00001').")
    alert_id: int = Field(..., description="Associated alert foreign key.")
    camera_id: Optional[int] = Field(None, description="Source camera foreign key.")
    track_id: Optional[int] = Field(None, description="Suspect track foreign key.")
    file_path: str = Field(..., description="Filesystem path of the stored evidence frame.")
    filename: str = Field(..., description="Base filename of the evidence frame.")
    frame_width: int = Field(..., description="Horizontal resolution in pixels.")
    frame_height: int = Field(..., description="Vertical resolution in pixels.")
    capture_timestamp: datetime = Field(..., description="Timestamp when evidence image was captured (UTC).")
    alert_timestamp: Optional[datetime] = Field(None, description="Detection timestamp of the associated alert.")
    evidence_metadata: Dict[str, Any] = Field(default_factory=dict, description="Contextual evidence metadata.")
    created_at: datetime = Field(..., description="Record creation UTC timestamp.")

    model_config = ConfigDict(from_attributes=True)
