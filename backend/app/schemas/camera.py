"""Pydantic schemas for Camera entities."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CameraSourceType, CameraStatus
from app.schemas.common import PaginatedResponse


class CameraResponse(BaseModel):
    """Schema representing a surveillance camera."""

    id: int = Field(..., description="Internal surrogate primary key.")
    camera_id: str = Field(..., description="Unique external camera identifier (e.g. 'CAM-01').")
    name: str = Field(..., description="Descriptive human-readable camera name.")
    source_type: CameraSourceType = Field(..., description="Video stream or input type.")
    source_reference: str = Field(..., description="Stream URI, device index, or file path.")
    location: Optional[str] = Field(None, description="Physical location or operational sector.")
    status: CameraStatus = Field(..., description="Current operational status (ONLINE, OFFLINE, ERROR).")
    created_at: datetime = Field(..., description="Creation UTC timestamp.")
    updated_at: datetime = Field(..., description="Last update UTC timestamp.")

    model_config = ConfigDict(from_attributes=True)


class CameraListResponse(PaginatedResponse[CameraResponse]):
    """Paginated list of cameras."""
    pass
