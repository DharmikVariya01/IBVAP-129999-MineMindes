"""Pipeline Runtime Coordinator Service for IBVAP (Module 25).

Provides high-level orchestration binding together:
1. Video Ingestion & AI Pipeline (Modules 1–12)
2. Database Event & Track Persistence (Modules 13, 14 & 25)
3. Real-Time WebSocket Delivery & Backpressure (Module 17)
4. Operational Camera Status Propagation (Modules 19, 21, 24)

Maintains clean component independence:
- The AI Engine does not import or know about PostgreSQL.
- Networking code does not touch detection algorithms.
- Operational camera state transitions (ONLINE, OFFLINE, ERROR) are uniformly
  propagated to the database, WebSocket broadcast, and frontend consumers.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Any, Callable, Dict, Generator, Optional, Union

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_engine.pipeline import AIPipeline, PipelineResult
from ai_engine.video_input import VideoSource
from app.models.camera import Camera
from app.models.enums import CameraStatus
from app.services.pipeline_persistence import PipelinePersistenceError, PipelinePersistenceService
from app.services.websocket_adapter import PipelineWebSocketAdapter

logger = logging.getLogger("ibvap.pipeline_runtime")


class PipelineRuntime:
    """End-to-End Runtime Coordinator for a Surveillance Camera Stream."""

    def __init__(
        self,
        camera_id: str,
        pipeline: Optional[AIPipeline] = None,
        ws_adapter: Optional[PipelineWebSocketAdapter] = None,
        persistence_service: Optional[PipelinePersistenceService] = None,
        auto_persist: bool = True,
        camera_name: Optional[str] = None,
        location: Optional[str] = None,
        fps: float = 15.0,
    ) -> None:
        """Initialize pipeline runtime coordinator for a specific camera.

        Args:
            camera_id: Unique string camera identifier (e.g. 'CAM_01').
            pipeline: Optional AIPipeline instance. Initialized with defaults if None.
            ws_adapter: Optional PipelineWebSocketAdapter. Initialized with defaults if None.
            persistence_service: Optional persistence service. Initialized with defaults if None.
            auto_persist: Whether to automatically persist results into PostgreSQL.
            camera_name: Optional human-readable camera name.
            location: Optional operational sector / location description.
            fps: Target processing frames-per-second metric for statistics.
        """
        self.camera_id: str = str(camera_id)
        self.camera_name: str = camera_name or f"Camera {self.camera_id}"
        self.location: str = location or "Perimeter Sector"
        self.fps: float = float(fps)
        self.auto_persist: bool = bool(auto_persist)

        # Core Components
        self.pipeline: AIPipeline = pipeline if pipeline is not None else AIPipeline(camera_id=self.camera_id)
        self.ws_adapter: PipelineWebSocketAdapter = (
            ws_adapter if ws_adapter is not None else PipelineWebSocketAdapter(camera_id=self.camera_id)
        )
        self.persistence_service: Optional[PipelinePersistenceService] = (
            persistence_service if persistence_service is not None else PipelinePersistenceService()
        )

        # Operational State
        self._status: CameraStatus = CameraStatus.OFFLINE
        self._frame_count: int = 0
        self._last_processed_time: float = 0.0

    @property
    def status(self) -> CameraStatus:
        """Return the current operational status of the camera."""
        return self._status

    @property
    def frame_count(self) -> int:
        """Return the total number of frames processed by this runtime instance."""
        return self._frame_count

    # -----------------------------------------------------------------------
    # Camera Status Management
    # -----------------------------------------------------------------------

    async def set_camera_status(
        self,
        status: Union[CameraStatus, str],
        details: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> None:
        """Transition camera operational status, update DB, and broadcast over WebSocket.

        Supported states:
        - ONLINE: Camera source is actively connected and generating frames.
        - OFFLINE: Camera source is disconnected or halted.
        - ERROR: Camera encountered an operational or decoding fault.
        """
        status_enum = CameraStatus(status) if isinstance(status, str) else status
        self._status = status_enum

        # 1. Update Database Record if persistence is enabled
        if self.auto_persist and self.persistence_service:
            try:
                session = db if db is not None else self.persistence_service.get_session()
                manage_session = db is None
                try:
                    stmt = select(Camera).where(Camera.camera_id == self.camera_id)
                    cam = session.scalar(stmt)
                    if cam is not None:
                        cam.status = status_enum
                        cam.updated_at = datetime.now(timezone.utc)
                        if manage_session:
                            session.commit()
                        else:
                            session.flush()
                finally:
                    if manage_session:
                        session.close()
            except Exception as exc:
                logger.warning(
                    "Could not persist camera status %s to database: %s",
                    status_enum.value,
                    exc,
                )

        # 2. Broadcast status update over WebSocket
        await self.ws_adapter.publish_camera_status(
            status=status_enum.value,
            details=details,
        )
        logger.info(
            "Camera %s status changed to %s (details: %s)",
            self.camera_id,
            status_enum.value,
            details or "None",
        )

    async def start(self, db: Optional[Session] = None) -> None:
        """Mark camera stream as active and ONLINE."""
        await self.set_camera_status(CameraStatus.ONLINE, details="Camera stream active", db=db)

    async def stop(self, db: Optional[Session] = None) -> None:
        """Mark camera stream as OFFLINE."""
        await self.set_camera_status(CameraStatus.OFFLINE, details="Camera stream stopped", db=db)

    async def set_error(self, details: str, db: Optional[Session] = None) -> None:
        """Mark camera stream as in ERROR state with diagnostic details."""
        await self.set_camera_status(CameraStatus.ERROR, details=details, db=db)

    # -----------------------------------------------------------------------
    # Frame Processing Execution
    # -----------------------------------------------------------------------

    async def process_frame(
        self,
        frame: np.ndarray,
        frame_id: Optional[int] = None,
        timestamp: Optional[Union[float, datetime]] = None,
        include_frame_ws: bool = True,
        db: Optional[Session] = None,
    ) -> PipelineResult:
        """Execute complete AI Pipeline, database persistence, and WebSocket broadcasting for a frame.

        Args:
            frame: Input BGR NumPy image.
            frame_id: Optional sequence frame number.
            timestamp: Optional wall-clock timestamp.
            include_frame_ws: Whether to broadcast the video frame to WebSocket subscribers.
            db: Optional database Session for transaction control.

        Returns:
            PipelineResult containing all detections, events, alerts, and evidence.
        """
        start_t = time.time()

        # 1. Execute AI Pipeline (M1–M11)
        result: PipelineResult = self.pipeline.process_frame(
            frame=frame,
            frame_id=frame_id,
            timestamp=timestamp,
        )
        self._frame_count += 1

        # 2. Persist to PostgreSQL if auto_persist is active
        if self.auto_persist and self.persistence_service:
            cam_info = {
                "name": self.camera_name,
                "location": self.location,
                "status": self.status,
            }
            self.persistence_service.persist_pipeline_result(
                result=result,
                camera_id=self.camera_id,
                db=db,
                camera_info=cam_info,
            )

        # 3. Publish to WebSocket Layer (M17)
        elapsed = time.time() - start_t
        current_fps = (1.0 / elapsed) if elapsed > 0 else self.fps
        await self.ws_adapter.publish_pipeline_result(
            result=result,
            include_frame=include_frame_ws,
            fps=round(current_fps, 1),
        )

        self._last_processed_time = time.time()
        return result

    # -----------------------------------------------------------------------
    # Video Ingestion Runner
    # -----------------------------------------------------------------------

    async def run_video_source(
        self,
        source: Optional[VideoSource] = None,
        max_frames: Optional[int] = None,
        include_frames_ws: bool = True,
        db: Optional[Session] = None,
    ) -> int:
        """Run controlled video processing from an M1 VideoSource instance.

        Args:
            source: VideoSource instance. Defaults to self.pipeline.video_source.
            max_frames: Optional maximum frames to process before terminating.
            include_frames_ws: Whether to stream video frames to WebSocket subscribers.
            db: Optional database Session.

        Returns:
            Total frames successfully processed.
        """
        src = source or self.pipeline.video_source
        if src is None:
            raise ValueError("No VideoSource configured for PipelineRuntime.")

        close_after = False
        if not src.is_opened:
            src.open()
            close_after = True

        frames_run = 0
        try:
            await self.start(db=db)

            while True:
                if max_frames is not None and frames_run >= max_frames:
                    break

                ret, frame = src.read()
                if not ret or frame is None:
                    break

                frame_id = src.current_frame_index
                await self.process_frame(
                    frame=frame,
                    frame_id=frame_id,
                    include_frame_ws=include_frames_ws,
                    db=db,
                )
                frames_run += 1

                # Yield control to event loop to allow concurrent async operations
                await asyncio.sleep(0)

            await self.stop(db=db)
            return frames_run

        except Exception as exc:
            await self.set_error(details=str(exc), db=db)
            logger.error("Error during video source processing for camera %s: %s", self.camera_id, exc)
            raise
        finally:
            if close_after:
                src.release()
