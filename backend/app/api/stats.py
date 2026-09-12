"""Statistics REST API endpoints."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.alert import Alert
from app.models.camera import Camera
from app.models.event import Event
from app.models.evidence import Evidence
from app.models.track import Track
from app.schemas.stats import StatsResponse

router = APIRouter(prefix="/stats", tags=["Statistics"])


@router.get(
    "",
    response_model=StatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get platform aggregate statistics",
    description="Retrieve high-level counts and status/severity breakdowns computed strictly via database aggregate queries.",
)
def get_platform_statistics(
    db: Session = Depends(get_db),
) -> StatsResponse:
    """Compute aggregate counts for cameras, tracks, events, alerts, and evidence."""
    # Database aggregate count queries
    total_cameras = db.scalar(select(func.count(Camera.id))) or 0
    total_tracks = db.scalar(select(func.count(Track.id))) or 0
    total_events = db.scalar(select(func.count(Event.id))) or 0
    total_alerts = db.scalar(select(func.count(Alert.id))) or 0
    total_evidence = db.scalar(select(func.count(Evidence.id))) or 0

    # Alerts by status breakdown
    alert_status_rows = db.execute(
        select(Alert.status, func.count(Alert.id)).group_by(Alert.status)
    ).all()
    alerts_by_status = {
        (st.value if hasattr(st, "value") else str(st)): count
        for st, count in alert_status_rows
    }

    # Alerts by severity breakdown
    alert_severity_rows = db.execute(
        select(Alert.severity, func.count(Alert.id)).group_by(Alert.severity)
    ).all()
    alerts_by_severity = {
        (sev.value if hasattr(sev, "value") else str(sev)): count
        for sev, count in alert_severity_rows
    }

    # Cameras by status breakdown
    camera_status_rows = db.execute(
        select(Camera.status, func.count(Camera.id)).group_by(Camera.status)
    ).all()
    cameras_by_status = {
        (st.value if hasattr(st, "value") else str(st)): count
        for st, count in camera_status_rows
    }

    # Tracks by status breakdown
    track_status_rows = db.execute(
        select(Track.status, func.count(Track.id)).group_by(Track.status)
    ).all()
    tracks_by_status = {
        (st.value if hasattr(st, "value") else str(st)): count
        for st, count in track_status_rows
    }

    return StatsResponse(
        cameras=total_cameras,
        tracks=total_tracks,
        events=total_events,
        alerts=total_alerts,
        evidence=total_evidence,
        alerts_by_status=alerts_by_status,
        alerts_by_severity=alerts_by_severity,
        cameras_by_status=cameras_by_status,
        tracks_by_status=tracks_by_status,
    )
