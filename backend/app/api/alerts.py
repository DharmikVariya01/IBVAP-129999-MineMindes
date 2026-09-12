"""Security Alert REST API endpoints."""

from datetime import datetime
import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.alert import Alert
from app.models.base import utc_now
from app.models.camera import Camera
from app.models.enums import AlertSeverity, AlertStatus, AlertType
from app.schemas.alert import AlertListResponse, AlertResponse, AlertUpdate

router = APIRouter(prefix="/alerts", tags=["Alerts"])

# Canonical state transitions adhering to M10 Alert Lifecycle
VALID_STATUS_TRANSITIONS = {
    AlertStatus.ACTIVE: {AlertStatus.ACKNOWLEDGED, AlertStatus.RESOLVED},
    AlertStatus.ACKNOWLEDGED: {AlertStatus.RESOLVED},
    AlertStatus.RESOLVED: set(),
}


@router.get(
    "",
    response_model=AlertListResponse,
    status_code=status.HTTP_200_OK,
    summary="List security alerts",
    description="Retrieve paginated security alerts with filtering by status, severity, alert type, camera, or time range.",
)
def list_alerts(
    status_filter: Optional[AlertStatus] = Query(None, alias="status", description="Filter by alert status"),
    severity: Optional[AlertSeverity] = Query(None, description="Filter by severity level"),
    alert_type: Optional[AlertType] = Query(None, description="Filter by alert type"),
    camera_id: Optional[str] = Query(None, description="Filter by camera external identifier or surrogate ID"),
    start_time: Optional[datetime] = Query(None, description="Filter alerts triggered on or after timestamp (UTC)"),
    end_time: Optional[datetime] = Query(None, description="Filter alerts triggered on or before timestamp (UTC)"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    db: Session = Depends(get_db),
) -> AlertListResponse:
    """List security alerts with pagination, ordering, and multi-field filtering."""
    query = select(Alert)

    if status_filter is not None:
        query = query.where(Alert.status == status_filter)
    if severity is not None:
        query = query.where(Alert.severity == severity)
    if alert_type is not None:
        query = query.where(Alert.alert_type == alert_type)
    if start_time is not None:
        query = query.where(Alert.alert_timestamp >= start_time)
    if end_time is not None:
        query = query.where(Alert.alert_timestamp <= end_time)

    if camera_id is not None:
        clean_cam = camera_id.strip()
        if clean_cam.isdigit():
            query = query.where(Alert.camera_id == int(clean_cam))
        else:
            query = query.join(Alert.camera).where(Camera.camera_id == clean_cam)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    items = db.scalars(
        query.order_by(Alert.alert_timestamp.desc(), Alert.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return AlertListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{alert_id}",
    response_model=AlertResponse,
    status_code=status.HTTP_200_OK,
    summary="Get alert details",
    description="Retrieve full details for a security alert by external identifier (or surrogate ID).",
)
def get_alert(
    alert_id: str,
    db: Session = Depends(get_db),
) -> AlertResponse:
    """Retrieve a single alert by external or surrogate ID."""
    stmt = select(Alert).where(Alert.alert_id == alert_id)
    alert = db.scalar(stmt)

    if alert is None and alert_id.isdigit():
        alert = db.scalar(select(Alert).where(Alert.id == int(alert_id)))

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{alert_id}' not found.",
        )

    return AlertResponse.model_validate(alert)


@router.patch(
    "/{alert_id}",
    response_model=AlertResponse,
    status_code=status.HTTP_200_OK,
    summary="Update alert lifecycle status",
    description="Transition alert lifecycle status (ACKNOWLEDGE or RESOLVE) and record operator audit details.",
)
def update_alert(
    alert_id: str,
    update_data: AlertUpdate,
    db: Session = Depends(get_db),
) -> AlertResponse:
    """Apply lifecycle status transition and audit metadata to an alert."""
    stmt = select(Alert).where(Alert.alert_id == alert_id)
    alert = db.scalar(stmt)

    if alert is None and alert_id.isdigit():
        alert = db.scalar(select(Alert).where(Alert.id == int(alert_id)))

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{alert_id}' not found.",
        )

    target_status = update_data.status
    if target_status is not None and target_status != alert.status:
        allowed_transitions = VALID_STATUS_TRANSITIONS.get(alert.status, set())
        if target_status not in allowed_transitions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid alert state transition from '{alert.status.value}' to '{target_status.value}'.",
            )

        now = utc_now()
        if target_status == AlertStatus.ACKNOWLEDGED:
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = now
            if update_data.acknowledged_by is not None:
                alert.acknowledged_by = update_data.acknowledged_by
        elif target_status == AlertStatus.RESOLVED:
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = now
            if update_data.resolved_by is not None:
                alert.resolved_by = update_data.resolved_by
    else:
        # If status is not changing, allow operator audit updates if applicable
        if update_data.acknowledged_by is not None:
            alert.acknowledged_by = update_data.acknowledged_by
        if update_data.resolved_by is not None:
            alert.resolved_by = update_data.resolved_by

    db.commit()
    db.refresh(alert)
    return AlertResponse.model_validate(alert)
