"""Unit and Integration Tests for Module 7: Virtual Fence & Zone System.

Verifies:
1. Zone creation
2. Zone validation
3. Polygon validation
4. Add zone
5. Remove zone
6. Clear zones
7. Retrieve zones
8. Point inside polygon
9. Point outside polygon
10. Boundary behavior (on vertex, on edge, strictly outside)
11. Normal zone
12. Sensitive zone
13. Restricted zone
14. Virtual fence
15. Multiple zones
16. Overlapping zones
17. Zone priority (RESTRICTED > SENSITIVE > NORMAL)
18. TrackedObject classification (center point cx, cy)
19. Multiple tracked objects
20. Invalid inputs
21. Empty zone manager
22. Immutability/result safety
23. M4 -> M7 integration
"""

from dataclasses import FrozenInstanceError
from pathlib import Path
import pytest
import numpy as np

from ai_engine.tracker import TrackedObject
from ai_engine.zones import (
    DEFAULT_ZONE_COLORS,
    Zone,
    ZoneError,
    ZoneManager,
    ZoneResult,
    ZoneType,
    ZoneValidationError,
)

# Test square polygon: (100, 100) to (200, 200)
SQUARE_POLY = [(100, 100), (200, 100), (200, 200), (100, 200)]
TRIANGLE_POLY = [(300, 300), (400, 300), (350, 400)]


# ---------------------------------------------------------------------------
# 1. Zone Creation
# ---------------------------------------------------------------------------

class TestZoneCreation:
    """Test Zone dataclass instantiation and properties."""

    def test_zone_creation_basic(self):
        zone = Zone(
            zone_id="z1",
            zone_name="Zone 1",
            zone_type=ZoneType.NORMAL,
            polygon=SQUARE_POLY,
        )
        assert zone.zone_id == "z1"
        assert zone.zone_name == "Zone 1"
        assert zone.zone_type == ZoneType.NORMAL
        assert zone.polygon == tuple(SQUARE_POLY)
        assert zone.color == DEFAULT_ZONE_COLORS[ZoneType.NORMAL]

    def test_zone_creation_string_type(self):
        zone = Zone(
            zone_id="z_sens",
            zone_name="Sensitive Area",
            zone_type="sensitive",
            polygon=SQUARE_POLY,
        )
        assert zone.zone_type == ZoneType.SENSITIVE

    def test_zone_creation_custom_color(self):
        zone = Zone(
            zone_id="z_custom",
            zone_name="Custom Color",
            zone_type=ZoneType.RESTRICTED,
            polygon=SQUARE_POLY,
            color=(10, 20, 30),
        )
        assert zone.color == (10, 20, 30)

    def test_zone_priority_property(self):
        z_norm = Zone("z1", "N", ZoneType.NORMAL, SQUARE_POLY)
        z_sens = Zone("z2", "S", ZoneType.SENSITIVE, SQUARE_POLY)
        z_rest = Zone("z3", "R", ZoneType.RESTRICTED, SQUARE_POLY)
        z_fenc = Zone("z4", "F", ZoneType.FENCE, SQUARE_POLY)

        assert z_rest.priority > z_sens.priority
        assert z_sens.priority > z_norm.priority
        assert z_norm.priority > z_fenc.priority


# ---------------------------------------------------------------------------
# 2. Zone Validation
# ---------------------------------------------------------------------------

class TestZoneValidation:
    """Test validation of zone parameters."""

    def test_invalid_zone_id(self):
        with pytest.raises(ZoneValidationError, match="zone_id"):
            Zone(zone_id="", zone_name="Valid", zone_type=ZoneType.NORMAL, polygon=SQUARE_POLY)

        with pytest.raises(ZoneValidationError, match="zone_id"):
            Zone(zone_id="   ", zone_name="Valid", zone_type=ZoneType.NORMAL, polygon=SQUARE_POLY)

        with pytest.raises(ZoneValidationError, match="zone_id"):
            Zone(zone_id=123, zone_name="Valid", zone_type=ZoneType.NORMAL, polygon=SQUARE_POLY)  # type: ignore

    def test_invalid_zone_name(self):
        with pytest.raises(ZoneValidationError, match="zone_name"):
            Zone(zone_id="z1", zone_name="", zone_type=ZoneType.NORMAL, polygon=SQUARE_POLY)

        with pytest.raises(ZoneValidationError, match="zone_name"):
            Zone(zone_id="z1", zone_name="   ", zone_type=ZoneType.NORMAL, polygon=SQUARE_POLY)

    def test_invalid_zone_type(self):
        with pytest.raises(ZoneValidationError, match="zone_type"):
            Zone(zone_id="z1", zone_name="Name", zone_type="INVALID_TYPE", polygon=SQUARE_POLY)

        with pytest.raises(ZoneValidationError, match="zone_type"):
            Zone(zone_id="z1", zone_name="Name", zone_type=1234, polygon=SQUARE_POLY)  # type: ignore

    def test_invalid_color(self):
        with pytest.raises(ZoneValidationError, match="color"):
            Zone(zone_id="z1", zone_name="Name", zone_type=ZoneType.NORMAL, polygon=SQUARE_POLY, color=(1, 2))  # type: ignore


# ---------------------------------------------------------------------------
# 3. Polygon Validation
# ---------------------------------------------------------------------------

class TestPolygonValidation:
    """Test validation of polygon coordinates and structures."""

    def test_less_than_3_points(self):
        with pytest.raises(ZoneValidationError, match="at least 3 vertices"):
            Zone("z1", "Test", ZoneType.NORMAL, [(0, 0), (1, 1)])

        with pytest.raises(ZoneValidationError, match="at least 3 vertices"):
            Zone("z1", "Test", ZoneType.NORMAL, [])

    def test_non_sequence_polygon(self):
        with pytest.raises(ZoneValidationError, match="polygon"):
            Zone("z1", "Test", ZoneType.NORMAL, "not_a_polygon")  # type: ignore

    def test_non_2d_vertex(self):
        with pytest.raises(ZoneValidationError, match="2-element"):
            Zone("z1", "Test", ZoneType.NORMAL, [(0, 0, 0), (1, 1, 1), (2, 2, 2)])

    def test_non_numeric_vertex(self):
        with pytest.raises(ZoneValidationError, match="must be numeric"):
            Zone("z1", "Test", ZoneType.NORMAL, [(0, 0), ("a", "b"), (2, 2)])

    def test_nan_or_inf_coordinates(self):
        with pytest.raises(ZoneValidationError, match="finite numbers"):
            Zone("z1", "Test", ZoneType.NORMAL, [(0, 0), (float("nan"), 1.0), (2, 2)])

        with pytest.raises(ZoneValidationError, match="finite numbers"):
            Zone("z1", "Test", ZoneType.NORMAL, [(0, 0), (float("inf"), 1.0), (2, 2)])


# ---------------------------------------------------------------------------
# 4-7. ZoneManager Registration, Removal, Clear, Retrieval
# ---------------------------------------------------------------------------

class TestZoneManagerCRUD:
    """Test ZoneManager registration, retrieval, and removal."""

    def test_add_and_retrieve_zone(self):
        zm = ZoneManager()
        z1 = Zone("z1", "Zone 1", ZoneType.NORMAL, SQUARE_POLY)
        zm.add_zone(z1)

        assert len(zm) == 1
        assert "z1" in zm
        assert zm.get_zone("z1") == z1
        assert zm.get_zone("nonexistent") is None

    def test_create_zone_convenience(self):
        zm = ZoneManager()
        z = zm.create_zone("z1", "Zone 1", ZoneType.RESTRICTED, SQUARE_POLY)
        assert z.zone_id == "z1"
        assert len(zm) == 1
        assert zm.get_zone("z1") == z

    def test_reject_duplicate_zone_id(self):
        zm = ZoneManager()
        z1 = Zone("z1", "Zone 1", ZoneType.NORMAL, SQUARE_POLY)
        z2 = Zone("z1", "Duplicate ID", ZoneType.SENSITIVE, SQUARE_POLY)
        zm.add_zone(z1)

        with pytest.raises(ZoneValidationError, match="already registered"):
            zm.add_zone(z2)

    def test_remove_zone(self):
        zm = ZoneManager()
        z1 = Zone("z1", "Zone 1", ZoneType.NORMAL, SQUARE_POLY)
        zm.add_zone(z1)

        assert zm.remove_zone("z1") is True
        assert len(zm) == 0
        assert "z1" not in zm
        assert zm.remove_zone("z1") is False

    def test_clear_zones(self):
        zm = ZoneManager()
        zm.add_zone(Zone("z1", "Z1", ZoneType.NORMAL, SQUARE_POLY))
        zm.add_zone(Zone("z2", "Z2", ZoneType.SENSITIVE, TRIANGLE_POLY))
        assert len(zm) == 2

        zm.clear_zones()
        assert len(zm) == 0
        assert zm.get_zones() == []

    def test_get_zones_filtered_by_type(self):
        zm = ZoneManager()
        z1 = Zone("z1", "Z1", ZoneType.NORMAL, SQUARE_POLY)
        z2 = Zone("z2", "Z2", ZoneType.RESTRICTED, TRIANGLE_POLY)
        z3 = Zone("z3", "Z3", ZoneType.RESTRICTED, [(0, 0), (10, 0), (5, 10)])

        zm.add_zone(z1)
        zm.add_zone(z2)
        zm.add_zone(z3)

        assert len(zm.get_zones()) == 3
        restricted = zm.get_zones(ZoneType.RESTRICTED)
        assert len(restricted) == 2
        assert z1 not in restricted
        assert zm.get_zones(ZoneType.FENCE) == []


# ---------------------------------------------------------------------------
# 8-10. Point-in-Polygon & Boundary Behavior
# ---------------------------------------------------------------------------

class TestPointInPolygonAndBoundary:
    """Test geometric containment and boundary handling."""

    def test_point_clearly_inside(self):
        zone = Zone("z1", "Square", ZoneType.NORMAL, SQUARE_POLY)
        # Inside square (100, 100) to (200, 200)
        assert zone.contains_point((150, 150)) is True
        assert zone.contains_point((101, 101)) is True
        assert zone.contains_point((199, 199)) is True

    def test_point_clearly_outside(self):
        zone = Zone("z1", "Square", ZoneType.NORMAL, SQUARE_POLY)
        assert zone.contains_point((50, 50)) is False
        assert zone.contains_point((250, 250)) is False
        assert zone.contains_point((150, 50)) is False
        assert zone.contains_point((150, 250)) is False

    def test_boundary_behavior_on_vertex(self):
        zone = Zone("z1", "Square", ZoneType.NORMAL, SQUARE_POLY)
        # Vertices of square
        assert zone.contains_point((100, 100), include_boundary=True) is True
        assert zone.contains_point((200, 100), include_boundary=True) is True
        assert zone.contains_point((200, 200), include_boundary=True) is True
        assert zone.contains_point((100, 200), include_boundary=True) is True

        # When boundary is excluded, vertex is not inside
        assert zone.contains_point((100, 100), include_boundary=False) is False

    def test_boundary_behavior_on_edge(self):
        zone = Zone("z1", "Square", ZoneType.NORMAL, SQUARE_POLY)
        # Midpoints of edges
        assert zone.contains_point((150, 100), include_boundary=True) is True
        assert zone.contains_point((200, 150), include_boundary=True) is True
        assert zone.contains_point((150, 200), include_boundary=True) is True
        assert zone.contains_point((100, 150), include_boundary=True) is True

        # When boundary is excluded, edge point is not inside
        assert zone.contains_point((150, 100), include_boundary=False) is False

    def test_invalid_points_return_false(self):
        zone = Zone("z1", "Square", ZoneType.NORMAL, SQUARE_POLY)
        assert zone.contains_point(None) is False  # type: ignore
        assert zone.contains_point((float("nan"), 100)) is False
        assert zone.contains_point((100, float("inf"))) is False


# ---------------------------------------------------------------------------
# 11-14. Zone Types (Normal, Sensitive, Restricted, Fence)
# ---------------------------------------------------------------------------

class TestZoneTypesClassification:
    """Test individual classification for each zone type."""

    def test_normal_zone(self):
        zm = ZoneManager()
        zm.create_zone("z_norm", "Normal Zone", ZoneType.NORMAL, SQUARE_POLY)

        best_zone, fence_inside = zm.classify_point((150, 150))
        assert best_zone is not None
        assert best_zone.zone_type == ZoneType.NORMAL
        assert best_zone.zone_id == "z_norm"
        assert fence_inside is False

    def test_sensitive_zone(self):
        zm = ZoneManager()
        zm.create_zone("z_sens", "Sensitive Zone", ZoneType.SENSITIVE, SQUARE_POLY)

        best_zone, fence_inside = zm.classify_point((150, 150))
        assert best_zone is not None
        assert best_zone.zone_type == ZoneType.SENSITIVE
        assert fence_inside is False

    def test_restricted_zone(self):
        zm = ZoneManager()
        zm.create_zone("z_rest", "Restricted Zone", ZoneType.RESTRICTED, SQUARE_POLY)

        best_zone, fence_inside = zm.classify_point((150, 150))
        assert best_zone is not None
        assert best_zone.zone_type == ZoneType.RESTRICTED
        assert fence_inside is False

    def test_virtual_fence_classification(self):
        zm = ZoneManager()
        zm.create_zone("fence_1", "Virtual Border Fence", ZoneType.FENCE, SQUARE_POLY)

        # Point inside fence
        best_zone, fence_inside = zm.classify_point((150, 150))
        assert fence_inside is True
        assert zm.is_inside_fence((150, 150)) is True
        assert best_zone is not None
        assert best_zone.zone_id == "fence_1"

        # Point outside fence
        best_zone_out, fence_inside_out = zm.classify_point((50, 50))
        assert fence_inside_out is False
        assert zm.is_inside_fence((50, 50)) is False
        assert best_zone_out is None


# ---------------------------------------------------------------------------
# 15-17. Multiple Zones, Overlapping Zones, and Zone Priority
# ---------------------------------------------------------------------------

class TestMultipleAndOverlappingZones:
    """Test behavior with multiple disjoint and overlapping zones."""

    def test_multiple_disjoint_zones(self):
        zm = ZoneManager()
        zm.create_zone("z_norm", "Normal", ZoneType.NORMAL, SQUARE_POLY)
        zm.create_zone("z_sens", "Sensitive", ZoneType.SENSITIVE, TRIANGLE_POLY)

        # Point in square
        z_sq, f_sq = zm.classify_point((150, 150))
        assert z_sq is not None
        assert z_sq.zone_id == "z_norm"
        assert f_sq is False

        # Point in triangle (350, 320)
        z_tr, f_tr = zm.classify_point((350, 320))
        assert z_tr is not None
        assert z_tr.zone_id == "z_sens"
        assert f_tr is False

        # Point in neither
        z_none, f_none = zm.classify_point((0, 0))
        assert z_none is None
        assert f_none is False

    def test_overlapping_priority_restricted_over_sensitive(self):
        zm = ZoneManager()
        # Overlapping square: one sensitive, one restricted
        zm.create_zone("sens_1", "Sensitive", ZoneType.SENSITIVE, SQUARE_POLY)
        zm.create_zone("rest_1", "Restricted", ZoneType.RESTRICTED, SQUARE_POLY)

        best_zone, fence_inside = zm.classify_point((150, 150))
        assert best_zone is not None
        assert best_zone.zone_id == "rest_1"
        assert best_zone.zone_type == ZoneType.RESTRICTED

    def test_overlapping_priority_sensitive_over_normal(self):
        zm = ZoneManager()
        zm.create_zone("norm_1", "Normal", ZoneType.NORMAL, SQUARE_POLY)
        zm.create_zone("sens_1", "Sensitive", ZoneType.SENSITIVE, SQUARE_POLY)

        best_zone, fence_inside = zm.classify_point((150, 150))
        assert best_zone is not None
        assert best_zone.zone_id == "sens_1"
        assert best_zone.zone_type == ZoneType.SENSITIVE

    def test_overlapping_priority_restricted_over_all(self):
        zm = ZoneManager()
        zm.create_zone("norm_1", "Normal", ZoneType.NORMAL, SQUARE_POLY)
        zm.create_zone("sens_1", "Sensitive", ZoneType.SENSITIVE, SQUARE_POLY)
        zm.create_zone("rest_1", "Restricted", ZoneType.RESTRICTED, SQUARE_POLY)

        best_zone, fence_inside = zm.classify_point((150, 150))
        assert best_zone is not None
        assert best_zone.zone_id == "rest_1"
        assert best_zone.zone_type == ZoneType.RESTRICTED

    def test_overlapping_fence_and_surveillance_zone(self):
        zm = ZoneManager()
        # A fence and a restricted zone covering the same area
        zm.create_zone("fence_1", "Fence", ZoneType.FENCE, SQUARE_POLY)
        zm.create_zone("rest_1", "Restricted", ZoneType.RESTRICTED, SQUARE_POLY)

        best_zone, fence_inside = zm.classify_point((150, 150))
        assert best_zone is not None
        assert best_zone.zone_id == "rest_1"
        assert best_zone.zone_type == ZoneType.RESTRICTED
        assert fence_inside is True

    def test_deterministic_equal_priority_tie_break(self):
        zm = ZoneManager()
        # Two RESTRICTED zones overlapping
        zm.create_zone("rest_alpha", "Restricted Alpha", ZoneType.RESTRICTED, SQUARE_POLY)
        zm.create_zone("rest_beta", "Restricted Beta", ZoneType.RESTRICTED, SQUARE_POLY)

        best_zone, _ = zm.classify_point((150, 150))
        assert best_zone is not None
        # Registration order preserved
        assert best_zone.zone_id == "rest_alpha"


# ---------------------------------------------------------------------------
# 18-19. TrackedObject Classification
# ---------------------------------------------------------------------------

class TestTrackedObjectClassification:
    """Test center calculation and classification of TrackedObjects."""

    def test_tracked_object_center_calculation(self):
        obj = TrackedObject(
            track_id=1,
            class_id=0,
            class_name="person",
            confidence=0.95,
            x1=100,
            y1=100,
            x2=200,
            y2=200,
        )
        cx, cy = ZoneManager.calculate_center(obj)
        assert cx == 150
        assert cy == 150

    def test_classify_object_inside_zone(self):
        zm = ZoneManager()
        zm.create_zone("rest_zone", "Perimeter", ZoneType.RESTRICTED, SQUARE_POLY)

        # Object bbox centered at (150, 150) -> inside square
        obj = TrackedObject(
            track_id=42,
            class_id=0,
            class_name="person",
            confidence=0.9,
            x1=120,
            y1=120,
            x2=180,
            y2=180,
        )

        result = zm.classify_object(obj)
        assert isinstance(result, ZoneResult)
        assert result.track_id == 42
        assert result.center == (150, 150)
        assert result.zone_id == "rest_zone"
        assert result.zone_name == "Perimeter"
        assert result.zone_type == ZoneType.RESTRICTED
        assert result.inside_zone is True
        assert result.fence_inside is False

    def test_classify_object_outside_all_zones(self):
        zm = ZoneManager()
        zm.create_zone("rest_zone", "Perimeter", ZoneType.RESTRICTED, SQUARE_POLY)

        obj = TrackedObject(
            track_id=10,
            class_id=0,
            class_name="person",
            confidence=0.88,
            x1=0,
            y1=0,
            x2=20,
            y2=20,
        )

        result = zm.classify_object(obj)
        assert result.track_id == 10
        assert result.center == (10, 10)
        assert result.zone_id is None
        assert result.zone_name is None
        assert result.zone_type is None
        assert result.inside_zone is False
        assert result.fence_inside is False

    def test_classify_multiple_objects(self):
        zm = ZoneManager()
        zm.create_zone("z_norm", "Normal", ZoneType.NORMAL, SQUARE_POLY)
        zm.create_zone("fence_1", "Fence", ZoneType.FENCE, TRIANGLE_POLY)

        obj1 = TrackedObject(1, 0, "person", 0.9, 140, 140, 160, 160)  # center (150, 150) in square
        obj2 = TrackedObject(2, 2, "car", 0.85, 340, 310, 360, 330)   # center (350, 320) in triangle
        obj3 = TrackedObject(3, 0, "person", 0.7, 0, 0, 10, 10)        # center (5, 5) outside

        results = zm.classify_objects([obj1, obj2, obj3])
        assert len(results) == 3

        # obj1 in normal zone
        assert results[0].track_id == 1
        assert results[0].zone_id == "z_norm"
        assert results[0].zone_type == ZoneType.NORMAL
        assert results[0].inside_zone is True
        assert results[0].fence_inside is False

        # obj2 in fence
        assert results[1].track_id == 2
        assert results[1].zone_id == "fence_1"
        assert results[1].zone_type == ZoneType.FENCE
        assert results[1].fence_inside is True

        # obj3 outside
        assert results[2].track_id == 3
        assert results[2].zone_id is None
        assert results[2].inside_zone is False
        assert results[2].fence_inside is False

    def test_is_object_inside_fence(self):
        zm = ZoneManager()
        zm.create_zone("fence_1", "Border Fence", ZoneType.FENCE, SQUARE_POLY)

        obj_inside = TrackedObject(1, 0, "person", 0.9, 140, 140, 160, 160)
        obj_outside = TrackedObject(2, 0, "person", 0.9, 0, 0, 10, 10)

        assert zm.is_object_inside_fence(obj_inside) is True
        assert zm.is_object_inside_fence(obj_outside) is False


# ---------------------------------------------------------------------------
# 20-22. Invalid Inputs, Empty Manager, Immutability
# ---------------------------------------------------------------------------

class TestEdgeCasesAndSafety:
    """Test safety, edge cases, and immutability."""

    def test_empty_zone_manager(self):
        zm = ZoneManager()
        best_zone, fence_inside = zm.classify_point((100, 100))
        assert best_zone is None
        assert fence_inside is False
        assert zm.is_inside_fence((100, 100)) is False

        obj = TrackedObject(1, 0, "person", 0.9, 50, 50, 60, 60)
        res = zm.classify_object(obj)
        assert res.zone_id is None
        assert res.inside_zone is False
        assert res.fence_inside is False

        assert zm.classify_objects([]) == []
        assert zm.classify_objects(None) == []  # type: ignore

    def test_invalid_tracked_object_rejected(self):
        zm = ZoneManager()
        with pytest.raises(ZoneValidationError, match="x1, y1, x2, y2"):
            zm.calculate_center("not_an_object")

        class BadObject:
            x1 = "abc"
            y1 = 10
            x2 = 20
            y2 = 30

        with pytest.raises(ZoneValidationError, match="numeric"):
            zm.calculate_center(BadObject())

    def test_zone_result_immutability(self):
        res = ZoneResult(
            track_id=1,
            center=(100, 100),
            zone_id="z1",
            zone_name="Zone 1",
            zone_type=ZoneType.RESTRICTED,
            inside_zone=True,
            fence_inside=False,
        )
        with pytest.raises(FrozenInstanceError):
            res.zone_id = "z2"  # type: ignore

    def test_zone_immutability(self):
        zone = Zone("z1", "Name", ZoneType.NORMAL, SQUARE_POLY)
        with pytest.raises(FrozenInstanceError):
            zone.zone_id = "z2"  # type: ignore

    def test_manager_add_non_zone_rejected(self):
        zm = ZoneManager()
        with pytest.raises(ZoneValidationError, match="Expected Zone instance"):
            zm.add_zone("not_a_zone")  # type: ignore


# ---------------------------------------------------------------------------
# 23. M4 -> M7 Pipeline Integration
# ---------------------------------------------------------------------------

class TestM4M7Integration:
    """Integration tests connecting M4 (ByteTrackTracker) to M7 (ZoneManager)."""

    def test_m4_output_to_m7_classification(self):
        from ai_engine.tracker import TrackedObject

        zm = ZoneManager()
        # Define surveillance zone covering (200, 200) to (500, 500)
        zm.create_zone(
            "restricted_strip",
            "Border Strip",
            ZoneType.RESTRICTED,
            [(200, 200), (500, 200), (500, 500), (200, 500)],
        )
        zm.create_zone(
            "virtual_fence",
            "Outer Fence",
            ZoneType.FENCE,
            [(150, 150), (550, 150), (550, 550), (150, 550)],
        )

        # Simulate M4 tracker output
        m4_tracked_objects = [
            TrackedObject(track_id=1, class_id=0, class_name="person", confidence=0.92, x1=250, y1=250, x2=350, y2=350),
            TrackedObject(track_id=2, class_id=2, class_name="car", confidence=0.88, x1=160, y1=160, x2=180, y2=180),
            TrackedObject(track_id=3, class_id=0, class_name="person", confidence=0.75, x1=20, y1=20, x2=40, y2=40),
        ]

        results = zm.classify_objects(m4_tracked_objects)
        assert len(results) == 3

        # Track 1: center (300, 300) -> inside restricted AND inside fence
        assert results[0].track_id == 1
        assert results[0].center == (300, 300)
        assert results[0].zone_id == "restricted_strip"
        assert results[0].zone_type == ZoneType.RESTRICTED
        assert results[0].inside_zone is True
        assert results[0].fence_inside is True

        # Track 2: center (170, 170) -> inside fence only
        assert results[1].track_id == 2
        assert results[1].center == (170, 170)
        assert results[1].zone_id == "virtual_fence"
        assert results[1].zone_type == ZoneType.FENCE
        assert results[1].inside_zone is True
        assert results[1].fence_inside is True

        # Track 3: center (30, 30) -> outside all
        assert results[2].track_id == 3
        assert results[2].center == (30, 30)
        assert results[2].zone_id is None
        assert results[2].inside_zone is False
        assert results[2].fence_inside is False


# ---------------------------------------------------------------------------
# 24. Real Video Pipeline Integration
# ---------------------------------------------------------------------------

class TestRealVideoIntegration:
    """Test running M1->M2->M3->M4->M5->M6->M7 against the actual test video."""

    def test_pipeline_on_real_video(self):
        from datetime import datetime
        from ai_engine.detector import YOLODetector
        from ai_engine.event_memory import EventMemory
        from ai_engine.movement import MovementAnalyzer
        from ai_engine.preprocessing import FramePreprocessor
        from ai_engine.tracker import ByteTrackTracker
        from ai_engine.video_input import VideoSource

        video_path = Path(__file__).resolve().parent.parent / "videos" / "test.mp4"
        if not video_path.exists():
            pytest.skip(f"Video file not found at {video_path}")

        # Initialize full pipeline
        source = VideoSource(source_type="video", source=str(video_path))
        preprocessor = FramePreprocessor()
        detector = YOLODetector(device="cpu", conf_threshold=0.3)
        tracker = ByteTrackTracker(detector)
        memory = EventMemory(max_history=50)
        movement = MovementAnalyzer()
        zm = ZoneManager()

        # Define zones covering parts of typical 1280x720 video
        zm.create_zone(
            "restricted_center",
            "Restricted Center",
            ZoneType.RESTRICTED,
            [(200, 200), (900, 200), (900, 600), (200, 600)],
        )
        zm.create_zone(
            "perimeter_fence",
            "Outer Perimeter Fence",
            ZoneType.FENCE,
            [(50, 50), (1200, 50), (1200, 700), (50, 700)],
        )

        source.open()
        frame_count = 0
        zone_results_accumulated = []

        try:
            for frame in source:
                frame_count += 1
                now = datetime.utcnow()
                prep = preprocessor.process(frame)
                tracked_objects = tracker.update(prep)
                memory.update_batch(tracked_objects, now)
                movement.analyze_all(memory)

                # M7 classification
                z_results = zm.classify_objects(tracked_objects)
                zone_results_accumulated.extend(z_results)

                # Check result properties for every tracked object
                for r in z_results:
                    assert isinstance(r, ZoneResult)
                    assert isinstance(r.track_id, int)
                    assert isinstance(r.center, tuple)
                    assert len(r.center) == 2
                    assert isinstance(r.inside_zone, bool)
                    assert isinstance(r.fence_inside, bool)
                    if r.zone_id is not None:
                        assert isinstance(r.zone_type, ZoneType)
                        assert isinstance(r.zone_name, str)

                if frame_count >= 15:
                    break
        finally:
            source.release()

        assert frame_count == 15
        # Verify that we tracked objects and produced zone results
        assert len(zone_results_accumulated) > 0
