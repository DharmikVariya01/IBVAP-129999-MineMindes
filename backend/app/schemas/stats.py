"""Pydantic schemas for Platform Aggregated Statistics."""

from typing import Dict
from pydantic import BaseModel, Field


class StatsResponse(BaseModel):
    """Aggregate statistics for surveillance entities and security alerts."""

    cameras: int = Field(..., ge=0, description="Total registered cameras.")
    tracks: int = Field(..., ge=0, description="Total tracked objects.")
    events: int = Field(..., ge=0, description="Total pipeline detection events.")
    alerts: int = Field(..., ge=0, description="Total security alerts.")
    evidence: int = Field(..., ge=0, description="Total captured evidence records.")
    alerts_by_status: Dict[str, int] = Field(default_factory=dict, description="Alert counts grouped by status.")
    alerts_by_severity: Dict[str, int] = Field(default_factory=dict, description="Alert counts grouped by severity.")
    cameras_by_status: Dict[str, int] = Field(default_factory=dict, description="Camera counts grouped by status.")
    tracks_by_status: Dict[str, int] = Field(default_factory=dict, description="Track counts grouped by status.")
