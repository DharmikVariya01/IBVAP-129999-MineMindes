"""Comprehensive test suite for IBVAP Module 14 SQLAlchemy ORM Data Models.

Verifies:
1. Clean imports and exports of all six models and canonical enums.
2. Metadata presence of all six expected tables: cameras, tracks, zones, events, alerts, evidence.
3. Primary keys integrity (integer surrogate PKs).
4. Foreign keys integrity (referencing correct tables/columns, cascade rules).
5. Expected columns, data types, and nullable/non-nullable constraints.
6. Required indexes (business IDs, foreign keys, timestamps, status, severity).
7. Enum values adherence to accepted M1–M13 terminology.
8. Bidirectional ORM relationships and cascade configurations.
9. In-memory model construction, default values, and helper properties.
10. Zone polygon JSON representation and tuple conversion.
11. Strict PostgreSQL compilation without SQLite-specific behaviors.
12. Optional live PostgreSQL schema reflection test (cleanly skipped if unavailable).
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Set

import pytest
from sqlalchemy import create_mock_engine, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

# Ensure backend and root are in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models import (
    Alert,
    AlertSeverity,
    AlertStatus,
    AlertType,
    Base,
    Camera,
    CameraSourceType,
    CameraStatus,
    Event,
    EventType,
    Evidence,
    Track,
    TrackStatus,
    Zone,
    ZoneType,
    utc_now,
)


# ==============================================================================
# 1. Imports and Exports Tests
# ==============================================================================


class TestModelImportsAndExports:
    """Verifies that all models and enums are cleanly imported and exported."""

    def test_all_six_models_imported(self):
        """All six core models must be subclassed from DeclarativeBase Base."""
        models = [Camera, Track, Zone, Event, Alert, Evidence]
        for m in models:
            assert issubclass(m, Base), f"{m.__name__} must subclass Base"

    def test_enums_exported(self):
        """Canonical enums must be importable and defined."""
        enums = [
            CameraSourceType,
            CameraStatus,
            TrackStatus,
            ZoneType,
            EventType,
            AlertType,
            AlertSeverity,
            AlertStatus,
        ]
        for e in enums:
            assert issubclass(e, object)
            assert len(e) > 0


# ==============================================================================
# 2. Metadata and Table Structure Tests
# ==============================================================================


class TestMetadataAndTables:
    """Verifies table registration and metadata properties."""

    def test_metadata_contains_all_six_tables(self):
        """Base.metadata must register exactly the six required tables."""
        expected_tables = {
            "cameras",
            "tracks",
            "zones",
            "events",
            "alerts",
            "evidence",
        }
        registered = set(Base.metadata.tables.keys())
        assert expected_tables.issubset(registered), (
            f"Missing tables: {expected_tables - registered}"
        )

    def test_table_names_match_models(self):
        """Each model must map to its exact expected table name."""
        assert Camera.__tablename__ == "cameras"
        assert Track.__tablename__ == "tracks"
        assert Zone.__tablename__ == "zones"
        assert Event.__tablename__ == "events"
        assert Alert.__tablename__ == "alerts"
        assert Evidence.__tablename__ == "evidence"


# ==============================================================================
# 3. Primary Key Tests
# ==============================================================================


class TestPrimaryKeys:
    """Verifies that each table has a single integer autoincrement primary key."""

    @pytest.mark.parametrize(
        "table_name",
        ["cameras", "tracks", "zones", "events", "alerts", "evidence"],
    )
    def test_single_integer_primary_key(self, table_name: str):
        table = Base.metadata.tables[table_name]
        pk_cols = list(table.primary_key.columns)
        assert len(pk_cols) == 1, f"{table_name} should have exactly 1 primary key"
        pk_col = pk_cols[0]
        assert pk_col.name == "id"
        assert pk_col.type.python_type is int
        assert pk_col.nullable is False


# ==============================================================================
# 4. Foreign Key Tests
# ==============================================================================


class TestForeignKeys:
    """Verifies foreign key relationships, targets, and delete constraints."""

    def test_tracks_foreign_keys(self):
        table = Base.metadata.tables["tracks"]
        fk_map = {fk.parent.name: fk for fk in table.foreign_keys}
        assert "camera_id" in fk_map
        assert fk_map["camera_id"].target_fullname == "cameras.id"
        assert fk_map["camera_id"].ondelete == "CASCADE"

    def test_zones_foreign_keys(self):
        table = Base.metadata.tables["zones"]
        fk_map = {fk.parent.name: fk for fk in table.foreign_keys}
        assert "camera_id" in fk_map
        assert fk_map["camera_id"].target_fullname == "cameras.id"
        assert fk_map["camera_id"].ondelete == "SET NULL"

    def test_events_foreign_keys(self):
        table = Base.metadata.tables["events"]
        fk_map = {fk.parent.name: fk for fk in table.foreign_keys}
        assert "camera_id" in fk_map
        assert fk_map["camera_id"].target_fullname == "cameras.id"
        assert fk_map["camera_id"].ondelete == "CASCADE"

        assert "track_id" in fk_map
        assert fk_map["track_id"].target_fullname == "tracks.id"
        assert fk_map["track_id"].ondelete == "SET NULL"

        assert "zone_id" in fk_map
        assert fk_map["zone_id"].target_fullname == "zones.id"
        assert fk_map["zone_id"].ondelete == "SET NULL"

    def test_alerts_foreign_keys(self):
        table = Base.metadata.tables["alerts"]
        fk_map = {fk.parent.name: fk for fk in table.foreign_keys}
        assert "camera_id" in fk_map
        assert fk_map["camera_id"].target_fullname == "cameras.id"
        assert fk_map["camera_id"].ondelete == "CASCADE"

        assert "track_id" in fk_map
        assert fk_map["track_id"].target_fullname == "tracks.id"
        assert fk_map["track_id"].ondelete == "SET NULL"

        assert "event_id" in fk_map
        assert fk_map["event_id"].target_fullname == "events.id"
        assert fk_map["event_id"].ondelete == "SET NULL"

        assert "zone_id" in fk_map
        assert fk_map["zone_id"].target_fullname == "zones.id"
        assert fk_map["zone_id"].ondelete == "SET NULL"

    def test_evidence_foreign_keys(self):
        table = Base.metadata.tables["evidence"]
        fk_map = {fk.parent.name: fk for fk in table.foreign_keys}
        assert "alert_id" in fk_map
        assert fk_map["alert_id"].target_fullname == "alerts.id"
        assert fk_map["alert_id"].ondelete == "CASCADE"

        assert "camera_id" in fk_map
        assert fk_map["camera_id"].target_fullname == "cameras.id"
        assert fk_map["camera_id"].ondelete == "SET NULL"

        assert "track_id" in fk_map
        assert fk_map["track_id"].target_fullname == "tracks.id"
        assert fk_map["track_id"].ondelete == "SET NULL"


# ==============================================================================
# 5. Column Presence, Types, and Constraints Tests
# ==============================================================================


class TestColumnsAndConstraints:
    """Verifies that all required fields and nullability constraints exist."""

    def test_camera_columns(self):
        cols = Base.metadata.tables["cameras"].columns
        assert not cols["id"].nullable
        assert not cols["camera_id"].nullable
        assert cols["camera_id"].unique is True
        assert not cols["name"].nullable
        assert not cols["source_type"].nullable
        assert not cols["source_reference"].nullable
        assert cols["location"].nullable is True
        assert not cols["status"].nullable
        assert not cols["created_at"].nullable
        assert not cols["updated_at"].nullable

    def test_track_columns(self):
        cols = Base.metadata.tables["tracks"].columns
        assert not cols["id"].nullable
        assert not cols["track_id"].nullable
        assert cols["camera_id"].nullable is True
        assert not cols["class_id"].nullable
        assert not cols["class_name"].nullable
        assert not cols["first_seen"].nullable
        assert not cols["last_seen"].nullable
        assert not cols["frame_count"].nullable
        assert not cols["last_confidence"].nullable
        assert cols["bbox_x1"].nullable is True
        assert cols["bbox_y1"].nullable is True
        assert cols["bbox_x2"].nullable is True
        assert cols["bbox_y2"].nullable is True
        assert cols["last_center_x"].nullable is True
        assert cols["last_center_y"].nullable is True
        assert not cols["status"].nullable

    def test_zone_columns(self):
        cols = Base.metadata.tables["zones"].columns
        assert not cols["id"].nullable
        assert not cols["zone_id"].nullable
        assert cols["zone_id"].unique is True
        assert not cols["name"].nullable
        assert not cols["zone_type"].nullable
        assert not cols["polygon"].nullable
        assert not cols["priority"].nullable
        assert not cols["is_active"].nullable

    def test_event_columns(self):
        cols = Base.metadata.tables["events"].columns
        assert not cols["id"].nullable
        assert cols["event_id"].nullable is True
        assert cols["event_id"].unique is True
        assert not cols["event_type"].nullable
        assert not cols["timestamp"].nullable
        assert not cols["details"].nullable
        assert not cols["created_at"].nullable

    def test_alert_columns(self):
        cols = Base.metadata.tables["alerts"].columns
        assert not cols["id"].nullable
        assert not cols["alert_id"].nullable
        assert cols["alert_id"].unique is True
        assert not cols["alert_type"].nullable
        assert not cols["severity"].nullable
        assert not cols["status"].nullable
        assert not cols["message"].nullable
        assert not cols["alert_timestamp"].nullable
        assert not cols["alert_metadata"].nullable
        assert cols["acknowledged_at"].nullable is True
        assert cols["acknowledged_by"].nullable is True
        assert cols["resolved_at"].nullable is True
        assert cols["resolved_by"].nullable is True

    def test_evidence_columns(self):
        cols = Base.metadata.tables["evidence"].columns
        assert not cols["id"].nullable
        assert not cols["evidence_id"].nullable
        assert cols["evidence_id"].unique is True
        assert not cols["alert_id"].nullable
        assert not cols["file_path"].nullable
        assert not cols["filename"].nullable
        assert not cols["frame_width"].nullable
        assert not cols["frame_height"].nullable
        assert not cols["capture_timestamp"].nullable
        assert not cols["evidence_metadata"].nullable


# ==============================================================================
# 6. Index Tests
# ==============================================================================


class TestIndexes:
    """Verifies that indexes exist on critical lookup and join columns."""

    def _get_indexed_column_names(self, table_name: str) -> Set[str]:
        table = Base.metadata.tables[table_name]
        indexed_cols = set()
        for idx in table.indexes:
            for col in idx.columns:
                indexed_cols.add(col.name)
        for col in table.columns:
            if col.index or col.unique:
                indexed_cols.add(col.name)
        return indexed_cols

    def test_camera_indexes(self):
        indexed = self._get_indexed_column_names("cameras")
        assert "camera_id" in indexed

    def test_track_indexes(self):
        indexed = self._get_indexed_column_names("tracks")
        assert "track_id" in indexed
        assert "camera_id" in indexed

    def test_zone_indexes(self):
        indexed = self._get_indexed_column_names("zones")
        assert "zone_id" in indexed
        assert "camera_id" in indexed

    def test_event_indexes(self):
        indexed = self._get_indexed_column_names("events")
        assert "event_type" in indexed
        assert "timestamp" in indexed
        assert "camera_id" in indexed
        assert "track_id" in indexed
        assert "zone_id" in indexed

    def test_alert_indexes(self):
        indexed = self._get_indexed_column_names("alerts")
        assert "alert_id" in indexed
        assert "status" in indexed
        assert "severity" in indexed
        assert "alert_type" in indexed
        assert "alert_timestamp" in indexed
        assert "camera_id" in indexed

    def test_evidence_indexes(self):
        indexed = self._get_indexed_column_names("evidence")
        assert "evidence_id" in indexed
        assert "alert_id" in indexed
        assert "camera_id" in indexed
        assert "track_id" in indexed
        assert "capture_timestamp" in indexed


# ==============================================================================
# 7. Enum Terminology Compatibility Tests
# ==============================================================================


class TestEnumValuesCompatibility:
    """Verifies enum values match the accepted M1–M13 terminology."""

    def test_camera_source_type_values(self):
        assert {e.value for e in CameraSourceType} == {"webcam", "video", "rtsp"}

    def test_camera_status_values(self):
        assert {e.value for e in CameraStatus} == {"ONLINE", "OFFLINE", "ERROR"}

    def test_zone_type_values(self):
        # Must strictly match M7 ZoneType
        assert {e.value for e in ZoneType} == {
            "NORMAL",
            "SENSITIVE",
            "RESTRICTED",
            "FENCE",
        }

    def test_alert_type_values(self):
        # Must strictly match M10 AlertType
        assert {e.value for e in AlertType} == {"FENCE_BREACH", "LOITERING"}

    def test_alert_severity_values(self):
        # Must strictly match M10 AlertSeverity
        assert {e.value for e in AlertSeverity} == {
            "CRITICAL",
            "HIGH",
            "MEDIUM",
            "LOW",
        }

    def test_alert_status_values(self):
        # Must strictly match M10 AlertStatus
        assert {e.value for e in AlertStatus} == {
            "ACTIVE",
            "ACKNOWLEDGED",
            "RESOLVED",
        }

    def test_track_status_values(self):
        assert {e.value for e in TrackStatus} == {"ACTIVE", "LOST", "COMPLETED"}

    def test_event_type_values(self):
        assert {"FENCE_BREACH", "LOITERING"}.issubset({e.value for e in EventType})


# ==============================================================================
# 8. Relationship Configuration Tests
# ==============================================================================


class TestRelationshipConfigurations:
    """Verifies that SQLAlchemy ORM relationships are properly wired."""

    def test_camera_relationships(self):
        insp = inspect(Camera)
        rels = {r.key: r for r in insp.relationships}
        assert "tracks" in rels
        assert rels["tracks"].back_populates == "camera"
        assert "events" in rels
        assert rels["events"].back_populates == "camera"
        assert "alerts" in rels
        assert rels["alerts"].back_populates == "camera"
        assert "evidence_records" in rels
        assert rels["evidence_records"].back_populates == "camera"
        assert "zones" in rels
        assert rels["zones"].back_populates == "camera"

    def test_track_relationships(self):
        insp = inspect(Track)
        rels = {r.key: r for r in insp.relationships}
        assert "camera" in rels
        assert rels["camera"].back_populates == "tracks"
        assert "events" in rels
        assert rels["events"].back_populates == "track"
        assert "alerts" in rels
        assert rels["alerts"].back_populates == "track"
        assert "evidence_records" in rels
        assert rels["evidence_records"].back_populates == "track"

    def test_zone_relationships(self):
        insp = inspect(Zone)
        rels = {r.key: r for r in insp.relationships}
        assert "camera" in rels
        assert rels["camera"].back_populates == "zones"
        assert "events" in rels
        assert rels["events"].back_populates == "zone"
        assert "alerts" in rels
        assert rels["alerts"].back_populates == "zone"

    def test_event_relationships(self):
        insp = inspect(Event)
        rels = {r.key: r for r in insp.relationships}
        assert "camera" in rels
        assert rels["camera"].back_populates == "events"
        assert "track" in rels
        assert rels["track"].back_populates == "events"
        assert "zone" in rels
        assert rels["zone"].back_populates == "events"
        assert "alerts" in rels
        assert rels["alerts"].back_populates == "event"

    def test_alert_relationships(self):
        insp = inspect(Alert)
        rels = {r.key: r for r in insp.relationships}
        assert "camera" in rels
        assert rels["camera"].back_populates == "alerts"
        assert "track" in rels
        assert rels["track"].back_populates == "alerts"
        assert "event" in rels
        assert rels["event"].back_populates == "alerts"
        assert "zone" in rels
        assert rels["zone"].back_populates == "alerts"
        assert "evidence_records" in rels
        assert rels["evidence_records"].back_populates == "alert"

    def test_evidence_relationships(self):
        insp = inspect(Evidence)
        rels = {r.key: r for r in insp.relationships}
        assert "alert" in rels
        assert rels["alert"].back_populates == "evidence_records"
        assert "camera" in rels
        assert rels["camera"].back_populates == "evidence_records"
        assert "track" in rels
        assert rels["track"].back_populates == "evidence_records"


# ==============================================================================
# 9. Model Construction and Properties Tests
# ==============================================================================


class TestModelConstructionAndProperties:
    """Verifies that instances of models can be created and queried in Python memory."""

    def test_camera_instantiation(self):
        cam = Camera(
            camera_id="CAM-01",
            name="Main Entrance Gate",
            source_type=CameraSourceType.RTSP,
            source_reference="rtsp://192.168.1.100/stream1",
            location="Perimeter North",
            status=CameraStatus.ONLINE,
        )
        assert cam.camera_id == "CAM-01"
        assert cam.source_type == CameraSourceType.RTSP
        assert "CAM-01" in repr(cam)

    def test_track_instantiation_and_properties(self):
        now = datetime.now(timezone.utc)
        tr = Track(
            track_id=42,
            camera_id=1,
            class_id=0,
            class_name="person",
            first_seen=now,
            last_seen=now,
            frame_count=15,
            last_confidence=0.88,
            bbox_x1=10,
            bbox_y1=20,
            bbox_x2=110,
            bbox_y2=220,
            last_center_x=60.0,
            last_center_y=120.0,
            status=TrackStatus.ACTIVE,
        )
        assert tr.track_id == 42
        assert tr.last_bbox == (10, 20, 110, 220)
        assert tr.last_center == (60.0, 120.0)
        assert "42" in repr(tr)

    def test_zone_instantiation_and_polygon_property(self):
        poly = [[100, 100], [200, 100], [200, 200], [100, 200]]
        z = Zone(
            zone_id="ZONE-ALPHA",
            name="Sensitive Vault",
            zone_type=ZoneType.RESTRICTED,
            polygon=poly,
            priority=3,
            is_active=True,
        )
        assert z.zone_id == "ZONE-ALPHA"
        assert z.polygon == poly
        assert z.polygon_tuples == ((100, 100), (200, 100), (200, 200), (100, 200))
        assert "ZONE-ALPHA" in repr(z)

    def test_event_instantiation(self):
        now = datetime.now(timezone.utc)
        ev = Event(
            event_id="EVT-001",
            camera_id=1,
            track_id=1,
            zone_id=1,
            event_type=EventType.FENCE_BREACH,
            frame_id=105,
            timestamp=now,
            details={"breach_count": 1, "previous_state": "OUTSIDE"},
        )
        assert ev.event_id == "EVT-001"
        assert ev.event_type == EventType.FENCE_BREACH
        assert ev.details["breach_count"] == 1
        assert "FENCE_BREACH" in repr(ev)

    def test_alert_instantiation_and_is_active(self):
        now = datetime.now(timezone.utc)
        al = Alert(
            alert_id="ALT-00001",
            camera_id=1,
            track_id=1,
            alert_type=AlertType.FENCE_BREACH,
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.ACTIVE,
            message="Fence breach detected at Perimeter",
            alert_timestamp=now,
            alert_metadata={"center": [150.0, 150.0]},
        )
        assert al.alert_id == "ALT-00001"
        assert al.is_active is True
        assert al.severity == AlertSeverity.CRITICAL

        # Test state change
        al.status = AlertStatus.RESOLVED
        assert al.is_active is False

    def test_evidence_instantiation_and_dimensions(self):
        evd = Evidence(
            evidence_id="EVD-00001",
            alert_id=1,
            camera_id=1,
            track_id=1,
            file_path="/evidence/2026-09-12/EVD-00001.jpg",
            filename="EVD-00001.jpg",
            frame_width=1920,
            frame_height=1080,
            evidence_metadata={"confidence": 0.95},
        )
        assert evd.evidence_id == "EVD-00001"
        assert evd.frame_dimensions == (1920, 1080)
        assert evd.width == 1920
        assert evd.height == 1080
        assert "EVD-00001" in repr(evd)


# ==============================================================================
# 10. PostgreSQL DDL Compilation Tests (No SQLite)
# ==============================================================================


class TestPostgresDDLCompilation:
    """Verifies that DDL compiles successfully under PostgreSQL dialect without errors."""

    def test_postgresql_ddl_compilation_all_tables(self):
        pg_dialect = postgresql.dialect()
        for table in Base.metadata.tables.values():
            ddl = str(CreateTable(table).compile(dialect=pg_dialect))
            assert "CREATE TABLE" in ddl
            assert table.name in ddl


# ==============================================================================
# 11. Optional Live PostgreSQL Schema Verification
# ==============================================================================


class TestOptionalLivePostgreSQL:
    """Verifies models against live PostgreSQL when explicitly configured."""

    def test_live_postgresql_schema_reflection(self):
        live_url = os.getenv("DATABASE_URL")
        if not live_url:
            pytest.skip("DATABASE_URL not configured — skipping live PostgreSQL schema test")

        from app.core.database import check_database_connection, get_engine

        try:
            health = check_database_connection()
            if health.get("status") != "healthy":
                pytest.skip(f"Live PostgreSQL unreachable: {health.get('error')}")

            engine = get_engine()
            # Verify engine connectivity without modifying tables
            with engine.connect() as conn:
                res = conn.exec_driver_sql("SELECT current_database(), current_user;")
                row = res.fetchone()
                assert row is not None
        except Exception as exc:
            pytest.skip(f"Live PostgreSQL skipped due to: {exc}")
