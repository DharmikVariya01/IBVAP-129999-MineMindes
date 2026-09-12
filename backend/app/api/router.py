"""Centralized API router for IBVAP backend.

Serves as the root router for all versioned API endpoints.
Future modules (M16+) will register domain-specific sub-routers here:
- /cameras (M16)
- /alerts (M17)
- /tracks (M18)
- /events (M19)
- /evidence (M20)
- /statistics (M21)
"""

from fastapi import APIRouter

api_router = APIRouter(prefix="/api/v1")

# Sub-routers for future modules will be included here as they are developed:
# from app.api.endpoints import cameras, alerts, tracks, events, evidence, statistics
# api_router.include_router(cameras.router, prefix="/cameras", tags=["Cameras"])
# api_router.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
# api_router.include_router(tracks.router, prefix="/tracks", tags=["Tracks"])
# api_router.include_router(events.router, prefix="/events", tags=["Events"])
# api_router.include_router(evidence.router, prefix="/evidence", tags=["Evidence"])
# api_router.include_router(statistics.router, prefix="/statistics", tags=["Statistics"])
