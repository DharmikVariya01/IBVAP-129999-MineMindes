"""Camera REST API endpoints."""

import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.camera import Camera
from app.models.enums import CameraSourceType, CameraStatus
from app.schemas.camera import CameraListResponse, CameraResponse

router = APIRouter(prefix="/cameras", tags=["Cameras"])


@router.get(
    "",
    response_model=CameraListResponse,
    status_code=status.HTTP_200_OK,
    summary="List surveillance cameras",
    description="Retrieve paginated list of surveillance cameras with optional status and source type filtering.",
)
def list_cameras(
    status_filter: Optional[CameraStatus] = Query(None, alias="status", description="Filter by operational status"),
    source_type: Optional[CameraSourceType] = Query(None, description="Filter by source type (webcam, video, rtsp)"),
    search: Optional[str] = Query(None, max_length=128, description="Search term matching camera name, ID, or location"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    db: Session = Depends(get_db),
) -> CameraListResponse:
    """List cameras with pagination and filtering."""
    query = select(Camera)

    if status_filter is not None:
        query = query.where(Camera.status == status_filter)
    if source_type is not None:
        query = query.where(Camera.source_type == source_type)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Camera.name.ilike(term),
                Camera.camera_id.ilike(term),
                Camera.location.ilike(term),
            )
        )

    # Database-level count
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    items = db.scalars(
        query.order_by(Camera.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return CameraListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{camera_id}",
    response_model=CameraResponse,
    status_code=status.HTTP_200_OK,
    summary="Get camera details",
    description="Retrieve surveillance camera information by external camera identifier (or surrogate ID).",
)
def get_camera(
    camera_id: str,
    db: Session = Depends(get_db),
) -> CameraResponse:
    """Retrieve a single camera by external or surrogate ID."""
    stmt = select(Camera).where(Camera.camera_id == camera_id)
    camera = db.scalar(stmt)

    if camera is None and camera_id.isdigit():
        camera = db.scalar(select(Camera).where(Camera.id == int(camera_id)))

    if camera is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )

    return CameraResponse.model_validate(camera)
