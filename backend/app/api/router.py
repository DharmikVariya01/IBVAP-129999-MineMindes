"""Centralized API router for IBVAP backend.

Serves as the root router for all versioned API endpoints under /api/v1:
- /cameras (M16)
- /alerts (M16)
- /tracks (M16)
- /events (M16)
- /evidence (M16)
- /stats (M16)
"""

from fastapi import APIRouter

from app.api.alerts import router as alerts_router
from app.api.cameras import router as cameras_router
from app.api.events import router as events_router
from app.api.evidence import router as evidence_router
from app.api.stats import router as stats_router
from app.api.tracks import router as tracks_router
from app.api.websocket import router as websocket_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(cameras_router)
api_router.include_router(alerts_router)
api_router.include_router(tracks_router)
api_router.include_router(events_router)
api_router.include_router(evidence_router)
api_router.include_router(stats_router)
api_router.include_router(websocket_router)

