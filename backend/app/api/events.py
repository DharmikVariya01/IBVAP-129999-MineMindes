"""Event REST API endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.event import Event
from app.models.track import Track
from app.schemas.event import EventResponse

router = APIRouter(prefix="/events", tags=["Events"])


@router.get(
    "/{track_id}",
    response_model=List[EventResponse],
    status_code=status.HTTP_200_OK,
    summary="Get chronological events for a track",
    description="Retrieve chronological detection events for a given track. Returns 404 if track does not exist, or empty list if no events.",
)
def get_track_events(
    track_id: int,
    db: Session = Depends(get_db),
) -> List[EventResponse]:
    """Retrieve chronological pipeline events associated with the requested track."""
    # First verify track existence
    track = db.scalar(select(Track).where(Track.track_id == track_id))
    if track is None:
        track = db.scalar(select(Track).where(Track.id == track_id))

    if track is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Track '{track_id}' not found.",
        )

    stmt = (
        select(Event)
        .where(Event.track_id == track.id)
        .order_by(Event.timestamp.asc(), Event.id.asc())
    )
    events = db.scalars(stmt).all()
    return [EventResponse.model_validate(e) for e in events]
