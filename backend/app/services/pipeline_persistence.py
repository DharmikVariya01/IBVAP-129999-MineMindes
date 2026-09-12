"""Pipeline Persistence Integration Service for IBVAP (Module 25).

Provides the integration service layer connecting AI analytics pipeline outputs
(PipelineResult from Module 12) with the PostgreSQL database (Modules 13 & 14).

Responsibilities:
- Resolve or safely initialize surveillance Camera records without duplication.
- Upsert persistent Track records (M4/M5), maintaining state and observation counts
  without creating redundant duplicate rows per video frame.
- Persist genuine pipeline Events (M8 FenceBreachEvent, M9 LoiteringEvent) into the Event ORM model.
- Persist security Alerts (M10) into the Alert ORM model with full foreign-key relational linkage.
- Persist Evidence frame metadata (M11) referencing on-disk image paths without storing binaries.
- Execute within atomic, controlled database transactions with rollback on failure.
- Sanitize error messages to strictly avoid leaking database credentials or internal secrets.
- Never fabricate successful persistence when database operations fail.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import get_session_factory, sanitize_error_message
from app.models.alert import Alert
from app.models.camera import Camera
from app.models.enums import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    CameraSourceType,
    CameraStatus,
    EventType,
    TrackStatus,
)
from app.models.event import Event
from app.models.evidence import Evidence
from app.models.track import Track

logger = logging.getLogger("ibvap.pipeline_persistence")


class PipelinePersistenceError(Exception):
    """Raised when pipeline persistence encounters an unrecoverable database error."""
    pass


def _to_utc_datetime(val: Optional[Union[float, int, datetime, str]]) -> datetime:
    """Normalize timestamps to a UTC-aware datetime instance."""
    if val is None:
        return datetime.now(timezone.utc)
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(float(val), tz=timezone.utc)
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)


class PipelinePersistenceService:
    """Service for persisting verified AI Pipeline execution results into PostgreSQL."""

    def __init__(self, session_factory: Optional[Callable[[], Session]] = None) -> None:
        """Initialize persistence service.

        Args:
            session_factory: Optional callable returning a new SQLAlchemy Session.
                             Defaults to app.core.database.get_session_factory.
        """
        self._session_factory = session_factory

    def get_session(self) -> Session:
        """Acquire a database session from the configured or default session factory."""
        if self._session_factory is not None:
            return self._session_factory()
        factory = get_session_factory()
        return factory()

    def persist_pipeline_result(
        self,
        result: Any,
        camera_id: str,
        db: Optional[Session] = None,
        camera_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Persist a single frame's PipelineResult into the database.

        Executes Camera resolution, Track upserting, Event insertion, Alert insertion,
        and Evidence metadata linking within one atomic database transaction.

        Args:
            result: PipelineResult instance from ai_engine.pipeline.
            camera_id: Unique string camera identifier (e.g., 'CAM_01').
            db: Optional existing active database Session. If None, creates a managed session.
            camera_info: Optional camera metadata for initial camera registration or status updates.

        Returns:
            Dictionary summarizing persisted record counts.

        Raises:
            PipelinePersistenceError: If database persistence fails (transaction is rolled back).
        """
        manage_session = db is None
        session: Session = db if db is not None else self.get_session()

        summary: Dict[str, Any] = {
            "camera_id": camera_id,
            "camera_db_id": None,
            "tracks_upserted": 0,
            "events_persisted": 0,
            "alerts_persisted": 0,
            "evidence_persisted": 0,
        }

        try:
            # 1. Camera Resolution & Safe Upsert
            camera = self._resolve_camera(session, camera_id, camera_info)
            summary["camera_db_id"] = camera.id

            # 2. Track Resolution & In-Place Upserting
            track_db_map = self._upsert_tracks(session, camera, result)
            summary["tracks_upserted"] = len(track_db_map)

            # 3. Genuine Event Persistence (Fence Breach & Loitering)
            event_db_map = self._persist_events(session, camera, result, track_db_map)
            summary["events_persisted"] = len(event_db_map)

            # 4. Security Alert Persistence with Relational Linkage
            alert_db_map = self._persist_alerts(session, camera, result, track_db_map, event_db_map)
            summary["alerts_persisted"] = len(alert_db_map)

            # 5. Evidence Frame Metadata Persistence
            evidence_count = self._persist_evidence(session, camera, result, track_db_map, alert_db_map)
            summary["evidence_persisted"] = evidence_count

            if manage_session:
                session.commit()
            else:
                session.flush()

            logger.debug(
                "Pipeline persistence succeeded for camera %s (frame %s): %s",
                camera_id,
                getattr(result, "frame_id", "?"),
                summary,
            )
            return summary

        except Exception as exc:
            if manage_session:
                session.rollback()
            safe_msg = sanitize_error_message(exc)
            logger.error(
                "Pipeline persistence failed for camera %s (frame %s): %s",
                camera_id,
                getattr(result, "frame_id", "?"),
                safe_msg,
            )
            raise PipelinePersistenceError(f"Database persistence failure: {safe_msg}") from exc
        finally:
            if manage_session:
                session.close()

    # -----------------------------------------------------------------------
    # Internal Entity Mappers
    # -----------------------------------------------------------------------

    def _resolve_camera(
        self,
        session: Session,
        camera_id: str,
        camera_info: Optional[Dict[str, Any]] = None,
    ) -> Camera:
        """Find an existing Camera record or safely create one without duplicate rows."""
        stmt = select(Camera).where(Camera.camera_id == camera_id)
        camera = session.scalar(stmt)

        now = datetime.now(timezone.utc)
        cam_info = camera_info or {}

        if camera is None:
            raw_type = cam_info.get("source_type", CameraSourceType.VIDEO)
            if isinstance(raw_type, str):
                try:
                    src_type = CameraSourceType(raw_type.lower())
                except ValueError:
                    src_type = CameraSourceType.VIDEO
            else:
                src_type = raw_type

            raw_status = cam_info.get("status", CameraStatus.ONLINE)
            if isinstance(raw_status, str):
                try:
                    st = CameraStatus(raw_status.upper())
                except ValueError:
                    st = CameraStatus.ONLINE
            else:
                st = raw_status

            camera = Camera(
                camera_id=camera_id,
                name=cam_info.get("name", f"Camera {camera_id}"),
                source_type=src_type,
                source_reference=cam_info.get("source_reference", f"stream://{camera_id}"),
                location=cam_info.get("location", "Perimeter Sector"),
                status=st,
            )
            session.add(camera)
            session.flush()
        else:
            # Update operational status if explicitly specified
            if "status" in cam_info:
                st_val = cam_info["status"]
                camera.status = CameraStatus(st_val.upper()) if isinstance(st_val, str) else st_val
            if "location" in cam_info and cam_info["location"] is not None:
                camera.location = cam_info["location"]
            camera.updated_at = now
            session.flush()

        return camera

    def _upsert_tracks(
        self,
        session: Session,
        camera: Camera,
        result: Any,
    ) -> Dict[int, int]:
        """Upsert detected and tracked objects into the Track table without duplicate rows.

        Returns:
            Dictionary mapping ByteTrack track_id (int) to database Track.id primary key (int).
        """
        tracked_objects = getattr(result, "tracked_objects", []) or []
        track_memories = getattr(result, "track_memories", []) or []
        movement_results = getattr(result, "movement_results", []) or []

        track_mem_by_id = {tm.track_id: tm for tm in track_memories if hasattr(tm, "track_id")}
        movement_by_id = {mr.track_id: mr for mr in movement_results if hasattr(mr, "track_id")}

        frame_dt = _to_utc_datetime(getattr(result, "timestamp", None))
        track_db_map: Dict[int, int] = {}

        for obj in tracked_objects:
            track_num = getattr(obj, "track_id", None)
            if track_num is None:
                continue

            tm = track_mem_by_id.get(track_num)
            mr = movement_by_id.get(track_num)

            first_seen_dt = frame_dt
            if tm and getattr(tm, "first_seen", None):
                first_seen_dt = _to_utc_datetime(tm.first_seen)

            frame_count = tm.frame_count if (tm and hasattr(tm, "frame_count")) else 1
            confidence = float(getattr(obj, "confidence", 0.0) or 0.0)

            # Coordinates
            bbox = getattr(obj, "bbox", None)
            if bbox and len(bbox) == 4:
                x1, y1, x2, y2 = (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
            elif hasattr(obj, "x1") and hasattr(obj, "y1") and hasattr(obj, "x2") and hasattr(obj, "y2"):
                x1, y1, x2, y2 = (int(obj.x1), int(obj.y1), int(obj.x2), int(obj.y2))
            else:
                x1, y1, x2, y2 = (None, None, None, None)

            center = getattr(obj, "center", None)
            if center and len(center) == 2:
                cx, cy = (float(center[0]), float(center[1]))
            elif x1 is not None and y1 is not None and x2 is not None and y2 is not None:
                cx, cy = (float((x1 + x2) / 2.0), float((y1 + y2) / 2.0))
            else:
                cx, cy = (None, None)

            # Build observation metadata
            obs_meta: Dict[str, Any] = {}
            if tm and hasattr(tm, "history"):
                obs_meta["history_count"] = len(tm.history)
            if mr:
                obs_meta["speed"] = float(getattr(mr, "speed", 0.0) or 0.0)
                obs_meta["direction"] = getattr(mr, "direction", None)

            # Query existing track for this camera
            stmt = select(Track).where(Track.camera_id == camera.id, Track.track_id == track_num)
            db_track = session.scalar(stmt)

            if db_track is None:
                class_id = int(getattr(obj, "class_id", 0) or 0)
                class_name = str(getattr(obj, "class_name", "object") or "object")
                db_track = Track(
                    track_id=track_num,
                    camera_id=camera.id,
                    class_id=class_id,
                    class_name=class_name,
                    first_seen=first_seen_dt,
                    last_seen=frame_dt,
                    frame_count=frame_count,
                    last_confidence=confidence,
                    bbox_x1=x1,
                    bbox_y1=y1,
                    bbox_x2=x2,
                    bbox_y2=y2,
                    last_center_x=cx,
                    last_center_y=cy,
                    status=TrackStatus.ACTIVE,
                    observation_metadata=obs_meta,
                )
                session.add(db_track)
                session.flush()
            else:
                # Update existing track record in place
                db_track.last_seen = frame_dt
                db_track.frame_count = frame_count if frame_count > db_track.frame_count else (db_track.frame_count + 1)
                db_track.last_confidence = confidence
                db_track.bbox_x1 = x1 if x1 is not None else db_track.bbox_x1
                db_track.bbox_y1 = y1 if y1 is not None else db_track.bbox_y1
                db_track.bbox_x2 = x2 if x2 is not None else db_track.bbox_x2
                db_track.bbox_y2 = y2 if y2 is not None else db_track.bbox_y2
                db_track.last_center_x = cx if cx is not None else db_track.last_center_x
                db_track.last_center_y = cy if cy is not None else db_track.last_center_y
                db_track.status = TrackStatus.ACTIVE
                if obs_meta:
                    existing = db_track.observation_metadata or {}
                    existing.update(obs_meta)
                    db_track.observation_metadata = existing
                session.flush()

            track_db_map[track_num] = db_track.id

        return track_db_map

    def _persist_events(
        self,
        session: Session,
        camera: Camera,
        result: Any,
        track_db_map: Dict[int, int],
    ) -> Dict[Tuple[int, EventType], int]:
        """Persist only genuine FenceBreachEvent and LoiteringEvent records.

        Returns:
            Dictionary mapping (track_id, EventType) to the database Event.id primary key.
        """
        fence_breaches = getattr(result, "fence_breach_events", []) or []
        loitering_events = getattr(result, "loitering_events", []) or []

        frame_id = getattr(result, "frame_id", None)
        frame_dt = _to_utc_datetime(getattr(result, "timestamp", None))
        event_db_map: Dict[Tuple[int, EventType], int] = {}

        # 1. Fence Breach Events
        for fbe in fence_breaches:
            tr_id = getattr(fbe, "track_id", None)
            if tr_id is None:
                continue

            evt_id = f"EVT-FB-{camera.camera_id}-{tr_id}-{frame_id}"
            existing = session.scalar(select(Event).where(Event.event_id == evt_id))
            if existing is not None:
                event_db_map[(tr_id, EventType.FENCE_BREACH)] = existing.id
                continue

            target_track_pk = track_db_map.get(tr_id)
            if target_track_pk is None:
                db_t = session.scalar(select(Track).where(Track.camera_id == camera.id, Track.track_id == tr_id))
                if db_t:
                    target_track_pk = db_t.id

            prev_st = getattr(fbe, "previous_state", "OUTSIDE")
            curr_st = getattr(fbe, "current_state", "INSIDE")
            details = {
                "previous_state": prev_st.value if hasattr(prev_st, "value") else str(prev_st),
                "current_state": curr_st.value if hasattr(curr_st, "value") else str(curr_st),
                "breach_count": getattr(fbe, "breach_count", 1),
                "center": getattr(fbe, "center", None),
                "fence_id": getattr(fbe, "fence_id", None),
                "metadata": getattr(fbe, "metadata", {}),
            }

            evt = Event(
                event_id=evt_id,
                camera_id=camera.id,
                track_id=target_track_pk,
                zone_id=None,
                event_type=EventType.FENCE_BREACH,
                frame_id=getattr(fbe, "frame_id", frame_id),
                timestamp=frame_dt,
                details=details,
            )
            session.add(evt)
            session.flush()
            event_db_map[(tr_id, EventType.FENCE_BREACH)] = evt.id

        # 2. Loitering Events
        for le in loitering_events:
            tr_id = getattr(le, "track_id", None)
            if tr_id is None:
                continue

            evt_id = f"EVT-LOIT-{camera.camera_id}-{tr_id}-{frame_id}"
            existing = session.scalar(select(Event).where(Event.event_id == evt_id))
            if existing is not None:
                event_db_map[(tr_id, EventType.LOITERING)] = existing.id
                continue

            target_track_pk = track_db_map.get(tr_id)
            if target_track_pk is None:
                db_t = session.scalar(select(Track).where(Track.camera_id == camera.id, Track.track_id == tr_id))
                if db_t:
                    target_track_pk = db_t.id

            details = {
                "duration_seconds": float(getattr(le, "duration_seconds", 0.0) or 0.0),
                "spatial_displacement": float(getattr(le, "spatial_displacement", 0.0) or 0.0),
                "spatial_radius": getattr(le, "spatial_radius", None),
                "threshold_seconds": getattr(le, "threshold_seconds", None),
                "loitering_count": getattr(le, "loitering_count", 1),
                "zone_name": getattr(le, "zone_name", None),
            }

            evt = Event(
                event_id=evt_id,
                camera_id=camera.id,
                track_id=target_track_pk,
                zone_id=None,
                event_type=EventType.LOITERING,
                frame_id=getattr(le, "frame_id", frame_id),
                timestamp=frame_dt,
                details=details,
            )
            session.add(evt)
            session.flush()
            event_db_map[(tr_id, EventType.LOITERING)] = evt.id

        return event_db_map

    def _persist_alerts(
        self,
        session: Session,
        camera: Camera,
        result: Any,
        track_db_map: Dict[int, int],
        event_db_map: Dict[Tuple[int, EventType], int],
    ) -> Dict[str, int]:
        """Persist M10 security alerts with relational foreign-key bindings.

        Returns:
            Dictionary mapping external alert_id (str) to database Alert.id primary key (int).
        """
        alerts = getattr(result, "alerts", []) or []
        alert_db_map: Dict[str, int] = {}
        frame_dt = _to_utc_datetime(getattr(result, "timestamp", None))

        for al in alerts:
            al_id = getattr(al, "alert_id", None)
            if not al_id:
                continue

            existing = session.scalar(select(Alert).where(Alert.alert_id == al_id))
            if existing is not None:
                alert_db_map[al_id] = existing.id
                continue

            tr_id = getattr(al, "track_id", None)
            target_track_pk = track_db_map.get(tr_id) if tr_id is not None else None
            if target_track_pk is None and tr_id is not None:
                db_t = session.scalar(select(Track).where(Track.camera_id == camera.id, Track.track_id == tr_id))
                if db_t:
                    target_track_pk = db_t.id

            # Enum mapping
            raw_type = getattr(al, "alert_type", "FENCE_BREACH")
            al_type_str = raw_type.value if hasattr(raw_type, "value") else str(raw_type)
            db_al_type = AlertType(al_type_str)

            raw_sev = getattr(al, "severity", "HIGH")
            sev_str = raw_sev.value if hasattr(raw_sev, "value") else str(raw_sev)
            db_sev = AlertSeverity(sev_str)

            raw_status = getattr(al, "status", "ACTIVE")
            status_str = raw_status.value if hasattr(raw_status, "value") else str(raw_status)
            db_status = AlertStatus(status_str)

            # Match triggering event foreign key
            evt_type_key = EventType.FENCE_BREACH if db_al_type == AlertType.FENCE_BREACH else EventType.LOITERING
            db_evt_id = event_db_map.get((tr_id, evt_type_key)) if tr_id is not None else None

            al_ts = getattr(al, "timestamp", None)
            al_dt = _to_utc_datetime(al_ts) if al_ts is not None else frame_dt

            metadata: Dict[str, Any] = getattr(al, "metadata", {}) or {}
            if getattr(al, "center", None):
                metadata["center"] = al.center
            if getattr(al, "zone_name", None):
                metadata["zone_name"] = al.zone_name
            if getattr(al, "evidence_reference", None):
                metadata["evidence_reference"] = al.evidence_reference

            db_alert = Alert(
                alert_id=al_id,
                camera_id=camera.id,
                track_id=target_track_pk,
                event_id=db_evt_id,
                zone_id=None,
                alert_type=db_al_type,
                severity=db_sev,
                status=db_status,
                message=str(getattr(al, "message", "Security Alert Detected")),
                alert_timestamp=al_dt,
                alert_metadata=metadata,
            )
            session.add(db_alert)
            session.flush()
            alert_db_map[al_id] = db_alert.id

        return alert_db_map

    def _persist_evidence(
        self,
        session: Session,
        camera: Camera,
        result: Any,
        track_db_map: Dict[int, int],
        alert_db_map: Dict[str, int],
    ) -> int:
        """Persist M11 evidence frame metadata linked to the Alert ORM entity."""
        evidence_records = getattr(result, "evidence_records", []) or []
        persisted_count = 0
        frame_dt = _to_utc_datetime(getattr(result, "timestamp", None))

        for ev in evidence_records:
            ev_id = getattr(ev, "evidence_id", None)
            al_id = getattr(ev, "alert_id", None)
            if not ev_id or not al_id:
                continue

            existing = session.scalar(select(Evidence).where(Evidence.evidence_id == ev_id))
            if existing is not None:
                continue

            db_alert_id = alert_db_map.get(al_id)
            if db_alert_id is None:
                db_a = session.scalar(select(Alert).where(Alert.alert_id == al_id))
                if db_a:
                    db_alert_id = db_a.id

            if db_alert_id is None:
                logger.warning("Skipping evidence %s: Associated alert %s not found in DB.", ev_id, al_id)
                continue

            tr_id = getattr(ev, "track_id", None)
            target_track_pk = track_db_map.get(tr_id) if tr_id is not None else None
            if target_track_pk is None and tr_id is not None:
                db_t = session.scalar(select(Track).where(Track.camera_id == camera.id, Track.track_id == tr_id))
                if db_t:
                    target_track_pk = db_t.id

            dims = getattr(ev, "frame_dimensions", (1920, 1080))
            capture_dt = _to_utc_datetime(getattr(ev, "timestamp", None)) or frame_dt

            db_ev = Evidence(
                evidence_id=ev_id,
                alert_id=db_alert_id,
                camera_id=camera.id,
                track_id=target_track_pk,
                file_path=str(getattr(ev, "file_path", "")),
                filename=str(getattr(ev, "filename", "")),
                frame_width=int(dims[0]),
                frame_height=int(dims[1]),
                capture_timestamp=capture_dt,
                alert_timestamp=capture_dt,
                evidence_metadata=getattr(ev, "metadata", {}) or {},
            )
            session.add(db_ev)
            session.flush()
            persisted_count += 1

        return persisted_count
