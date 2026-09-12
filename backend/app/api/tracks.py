"""Track REST API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.alert import Alert
from app.models.event import Event
from app.models.track import Track
from app.schemas.track import TrackResponse

router = APIRouter(prefix="/tracks", tags=["Tracks"])


@router.get(
    "/{track_id}",
    response_model=TrackResponse,
    status_code=status.HTTP_200_OK,
    summary="Get track details",
    description="Retrieve tracked object information and associated event/alert history counts by ByteTrack track ID or surrogate ID.",
)
def get_track(
    track_id: int,
    db: Session = Depends(get_db),
) -> TrackResponse:
    """Retrieve persistent track record with associated counts."""
    stmt = select(Track).where(Track.track_id == track_id)
    track = db.scalar(stmt)

    if track is None:
        # Fallback to internal surrogate ID
        track = db.scalar(select(Track).where(Track.id == track_id))

    if track is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Track '{track_id}' not found.",
        )

    # Compute associated history counts from M14 foreign key relationships
    events_count = db.scalar(select(func.count(Event.id)).where(Event.track_id == track.id)) or 0
    alerts_count = db.scalar(select(func.count(Alert.id)).where(Alert.track_id == track.id)) or 0

    response = TrackResponse.model_validate(track)
    response.events_count = events_count
    response.alerts_count = alerts_count
    return response
