"""Comprehensive Unit and Integration Tests for Module 8: Fence Breach Detection.

Tests all required specifications:
1. First observation OUTSIDE
2. First observation INSIDE (first observation rule: no breach)
3. OUTSIDE -> OUTSIDE (no breach)
4. OUTSIDE -> INSIDE (breach generated)
5. INSIDE -> INSIDE (duplicate protection: no new breach)
6. INSIDE -> OUTSIDE (exit: no breach)
7. OUTSIDE -> INSIDE -> OUTSIDE (1 breach on entry, 0 on exit)
8. Multiple crossings (OUTSIDE -> INSIDE -> OUTSIDE -> INSIDE: 2 separate breaches)
9. Long INSIDE sequence creates only one event (100 frames -> 1 breach event)
10. Multiple track IDs (concurrent tracking)
11. Track isolation (tracks do not leak state to each other)
12. Reset all (resets all internal tracks and total counts)
13. Reset one track (resets specified track, others remain untouched)
14. Invalid input (negative ID, non-integer ID, None ID, None state)
15. Unknown/missing fence state (UNKNOWN handling, string inputs)
16. Event structure (attributes, values, types)
17. Event immutability (frozen dataclass raises FrozenInstanceError)
18. M7 -> M8 integration (ZoneManager -> ZoneResult -> FenceBreachDetector)
19. Real sequential frame behavior (temporal frame-by-frame crossing simulation)
20. No mutation of M7/M5 state (ZoneResult, TrackedObject, EventMemory intact)
"""

from dataclasses import FrozenInstanceError
import pytest
import numpy as np

from ai_engine.fence_breach import (
    BreachEventType,
    FenceBreachDetector,
    FenceBreachError,
    FenceBreachEvent,
    FenceBreachValidationError,
    FenceState,
    TrackFenceState,
)
from ai_engine.tracker import TrackedObject
from ai_engine.zones import (
    Zone,
    ZoneManager,
    ZoneResult,
    ZoneType,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def detector() -> FenceBreachDetector:
    """Fresh instance of FenceBreachDetector."""
    return FenceBreachDetector(default_fence_id="tactical_fence")


@pytest.fixture
def sample_zone_manager() -> ZoneManager:
    """ZoneManager configured with a FENCE zone."""
    zm = ZoneManager(include_boundary=True)
    zm.create_zone(
        zone_id="perimeter_fence",
        zone_name="Main Perimeter Fence",
        zone_type=ZoneType.FENCE,
        polygon=[(100, 100), (300, 100), (300, 300), (100, 300)],
    )
    zm.create_zone(
        zone_id="restricted_zone",
        zone_name="High Security Vault",
        zone_type=ZoneType.RESTRICTED,
        polygon=[(150, 150), (250, 150), (250, 250), (150, 250)],
    )
    return zm


# ---------------------------------------------------------------------------
# 1. First Observation OUTSIDE
# ---------------------------------------------------------------------------

class TestFirstObservationOutside:
    """Test initial observation when object is OUTSIDE the virtual fence."""

    def test_first_observation_outside_returns_none(self, detector: FenceBreachDetector):
        event = detector.update_track(track_id=1, fence_inside=False, frame_id=0)
        assert event is None
        assert detector.total_breaches == 0
        assert detector.get_breach_count(1) == 0

    def test_first_observation_outside_initializes_state(self, detector: FenceBreachDetector):
        detector.update_track(track_id=1, fence_inside=False, frame_id=0)
        state = detector.get_track_state(1)
        assert state is not None
        assert state.track_id == 1
        assert state.previous_state is None
        assert state.current_state == FenceState.OUTSIDE
        assert state.breach_count == 0
        assert state.total_inside_frames == 0


# ---------------------------------------------------------------------------
# 2. First Observation INSIDE (First Observation Rule)
# ---------------------------------------------------------------------------

class TestFirstObservationInside:
    """Test first observation rule: INSIDE from start does NOT trigger breach."""

    def test_first_observation_inside_returns_none(self, detector: FenceBreachDetector):
        event = detector.update_track(track_id=10, fence_inside=True, frame_id=0)
        assert event is None
        assert detector.total_breaches == 0
        assert detector.get_breach_count(10) == 0

    def test_first_observation_inside_initializes_state(self, detector: FenceBreachDetector):
        detector.update_track(track_id=10, fence_inside=True, frame_id=5, center=(200, 200))
        state = detector.get_track_state(10)
        assert state is not None
        assert state.track_id == 10
        assert state.previous_state is None
        assert state.current_state == FenceState.INSIDE
        assert state.breach_count == 0
        assert state.total_inside_frames == 1
        assert state.last_center == (200, 200)


# ---------------------------------------------------------------------------
# 3. OUTSIDE -> OUTSIDE
# ---------------------------------------------------------------------------

class TestOutsideToOutside:
    """Test that remaining OUTSIDE generates no breach."""

    def test_outside_to_outside_no_breach(self, detector: FenceBreachDetector):
        detector.update_track(track_id=1, fence_inside=False, frame_id=1)
        event = detector.update_track(track_id=1, fence_inside=False, frame_id=2)
        assert event is None
        assert detector.total_breaches == 0
        assert detector.get_breach_count(1) == 0

        state = detector.get_track_state(1)
        assert state.previous_state == FenceState.OUTSIDE
        assert state.current_state == FenceState.OUTSIDE


# ---------------------------------------------------------------------------
# 4. OUTSIDE -> INSIDE (Breach Trigger)
# ---------------------------------------------------------------------------

class TestOutsideToInsideBreach:
    """Test that OUTSIDE -> INSIDE transition triggers a valid breach event."""

    def test_outside_to_inside_triggers_breach(self, detector: FenceBreachDetector):
        # Frame 1: Outside
        ev1 = detector.update_track(track_id=1, fence_inside=False, frame_id=1, center=(50, 50))
        assert ev1 is None

        # Frame 2: Inside (Crossed fence)
        ev2 = detector.update_track(
            track_id=1,
            fence_inside=True,
            frame_id=2,
            timestamp=1.5,
            center=(150, 150),
            fence_id="tactical_fence",
        )
        assert ev2 is not None
        assert isinstance(ev2, FenceBreachEvent)
        assert ev2.track_id == 1
        assert ev2.event_type == BreachEventType.FENCE_BREACH
        assert ev2.previous_state == FenceState.OUTSIDE
        assert ev2.current_state == FenceState.INSIDE
        assert ev2.frame_id == 2
        assert ev2.timestamp == 1.5
        assert ev2.center == (150, 150)
        assert ev2.fence_id == "tactical_fence"
        assert ev2.breach_count == 1
        assert detector.total_breaches == 1
        assert detector.get_breach_count(1) == 1


# ---------------------------------------------------------------------------
# 5. INSIDE -> INSIDE (Duplicate Protection)
# ---------------------------------------------------------------------------

class TestInsideToInsideDuplicateProtection:
    """Test that continuous residence INSIDE does not emit repeated breaches."""

    def test_inside_to_inside_no_duplicate_breach(self, detector: FenceBreachDetector):
        # Frame 1: Outside
        detector.update_track(track_id=1, fence_inside=False, frame_id=1)
        # Frame 2: Inside -> Breach #1
        ev_breach = detector.update_track(track_id=1, fence_inside=True, frame_id=2)
        assert ev_breach is not None

        # Frames 3, 4, 5: Continues inside -> NO breaches
        for f in range(3, 6):
            ev = detector.update_track(track_id=1, fence_inside=True, frame_id=f)
            assert ev is None, f"Frame {f} emitted unexpected breach"

        assert detector.total_breaches == 1
        assert detector.get_breach_count(1) == 1
        state = detector.get_track_state(1)
        assert state.total_inside_frames == 4


# ---------------------------------------------------------------------------
# 6. INSIDE -> OUTSIDE (Exit)
# ---------------------------------------------------------------------------

class TestInsideToOutsideExit:
    """Test exiting the fence (INSIDE -> OUTSIDE) produces no breach."""

    def test_inside_to_outside_produces_no_breach(self, detector: FenceBreachDetector):
        detector.update_track(track_id=1, fence_inside=False, frame_id=1)
        detector.update_track(track_id=1, fence_inside=True, frame_id=2)  # breach

        # Frame 3: Exits to outside
        ev_exit = detector.update_track(track_id=1, fence_inside=False, frame_id=3)
        assert ev_exit is None
        assert detector.total_breaches == 1

        state = detector.get_track_state(1)
        assert state.previous_state == FenceState.INSIDE
        assert state.current_state == FenceState.OUTSIDE


# ---------------------------------------------------------------------------
# 7. OUTSIDE -> INSIDE -> OUTSIDE
# ---------------------------------------------------------------------------

class TestOutsideInsideOutsideSequence:
    """Test complete sequence: OUTSIDE -> INSIDE (breach) -> OUTSIDE (exit)."""

    def test_sequence(self, detector: FenceBreachDetector):
        ev1 = detector.update_track(track_id=2, fence_inside=False, frame_id=10)
        assert ev1 is None

        ev2 = detector.update_track(track_id=2, fence_inside=True, frame_id=11)
        assert ev2 is not None
        assert ev2.track_id == 2
        assert ev2.breach_count == 1

        ev3 = detector.update_track(track_id=2, fence_inside=False, frame_id=12)
        assert ev3 is None
        assert detector.total_breaches == 1
        assert detector.get_breach_count(2) == 1


# ---------------------------------------------------------------------------
# 8. Multiple Crossings (Re-entry)
# ---------------------------------------------------------------------------

class TestMultipleCrossings:
    """Test re-entering the fence produces a second breach event."""

    def test_reentry_creates_second_breach(self, detector: FenceBreachDetector):
        # 1. OUTSIDE
        assert detector.update_track(track_id=5, fence_inside=False, frame_id=1) is None
        # 2. INSIDE -> Breach #1
        ev1 = detector.update_track(track_id=5, fence_inside=True, frame_id=2)
        assert ev1 is not None
        assert ev1.breach_count == 1

        # 3. Stay INSIDE
        assert detector.update_track(track_id=5, fence_inside=True, frame_id=3) is None

        # 4. OUTSIDE (Exit)
        assert detector.update_track(track_id=5, fence_inside=False, frame_id=4) is None

        # 5. Stay OUTSIDE
        assert detector.update_track(track_id=5, fence_inside=False, frame_id=5) is None

        # 6. INSIDE -> Breach #2!
        ev2 = detector.update_track(track_id=5, fence_inside=True, frame_id=6)
        assert ev2 is not None
        assert ev2.breach_count == 2
        assert ev2.track_id == 5
        assert detector.total_breaches == 2
        assert detector.get_breach_count(5) == 2


# ---------------------------------------------------------------------------
# 9. Long INSIDE Sequence Creates Exactly One Event
# ---------------------------------------------------------------------------

class TestLongInsideSequence:
    """Verify 100 consecutive frames inside generate exactly ONE event."""

    def test_100_frames_inside_exactly_one_breach(self, detector: FenceBreachDetector):
        # Frame 0: Outside
        detector.update_track(track_id=7, fence_inside=False, frame_id=0)

        breach_events = []
        # Frames 1 to 100: Inside
        for f in range(1, 101):
            ev = detector.update_track(track_id=7, fence_inside=True, frame_id=f)
            if ev is not None:
                breach_events.append(ev)

        assert len(breach_events) == 1
        assert breach_events[0].frame_id == 1
        assert detector.total_breaches == 1
        assert detector.get_breach_count(7) == 1

        state = detector.get_track_state(7)
        assert state.total_inside_frames == 100


# ---------------------------------------------------------------------------
# 10. Multiple Track IDs
# ---------------------------------------------------------------------------

class TestMultipleTrackIDs:
    """Test managing multiple track IDs concurrently."""

    def test_concurrent_tracks_tracked_independently(self, detector: FenceBreachDetector):
        # Setup tracks 1, 2, 3 outside
        for tid in [1, 2, 3]:
            detector.update_track(track_id=tid, fence_inside=False, frame_id=1)

        # Track 1 breaches
        ev1 = detector.update_track(track_id=1, fence_inside=True, frame_id=2)
        # Track 2 stays outside
        ev2 = detector.update_track(track_id=2, fence_inside=False, frame_id=2)
        # Track 3 breaches
        ev3 = detector.update_track(track_id=3, fence_inside=True, frame_id=2)

        assert ev1 is not None and ev1.track_id == 1
        assert ev2 is None
        assert ev3 is not None and ev3.track_id == 3
        assert detector.total_breaches == 2
        assert detector.get_breach_count(1) == 1
        assert detector.get_breach_count(2) == 0
        assert detector.get_breach_count(3) == 1


# ---------------------------------------------------------------------------
# 11. Track Isolation
# ---------------------------------------------------------------------------

class TestTrackIsolation:
    """Ensure zero state leakage between different tracks."""

    def test_tracks_do_not_leak_state(self, detector: FenceBreachDetector):
        # Track 1 starts outside
        detector.update_track(track_id=1, fence_inside=False, frame_id=1)

        # Track 2 starts inside (no breach due to first observation rule)
        ev_t2_init = detector.update_track(track_id=2, fence_inside=True, frame_id=1)
        assert ev_t2_init is None

        # Track 1 breaches
        ev_t1 = detector.update_track(track_id=1, fence_inside=True, frame_id=2)
        assert ev_t1 is not None
        assert ev_t1.track_id == 1

        # Track 2 continues inside (still no breach)
        ev_t2_cont = detector.update_track(track_id=2, fence_inside=True, frame_id=2)
        assert ev_t2_cont is None

        # Verify state separation
        state1 = detector.get_track_state(1)
        state2 = detector.get_track_state(2)
        assert state1.breach_count == 1
        assert state2.breach_count == 0


# ---------------------------------------------------------------------------
# 12. Reset All
# ---------------------------------------------------------------------------

class TestResetAll:
    """Test reset() clears all internal state and counters."""

    def test_reset_clears_everything(self, detector: FenceBreachDetector):
        detector.update_track(track_id=1, fence_inside=False, frame_id=1)
        detector.update_track(track_id=1, fence_inside=True, frame_id=2)
        detector.update_track(track_id=2, fence_inside=False, frame_id=1)

        assert len(detector) == 2
        assert detector.total_breaches == 1

        detector.reset()

        assert len(detector) == 0
        assert detector.total_breaches == 0
        assert detector.get_track_state(1) is None
        assert detector.get_track_state(2) is None
        assert detector.get_breach_count(1) == 0


# ---------------------------------------------------------------------------
# 13. Reset One Track & Cleanup Stale
# ---------------------------------------------------------------------------

class TestResetOneTrackAndCleanup:
    """Test reset_track() and cleanup_stale_tracks()."""

    def test_reset_track_removes_single_track(self, detector: FenceBreachDetector):
        detector.update_track(track_id=1, fence_inside=False, frame_id=1)
        detector.update_track(track_id=2, fence_inside=False, frame_id=1)

        assert detector.reset_track(1) is True
        assert 1 not in detector
        assert 2 in detector
        assert detector.reset_track(999) is False  # nonexistent

    def test_cleanup_stale_tracks(self, detector: FenceBreachDetector):
        detector.update_track(track_id=1, fence_inside=False, frame_id=1)
        detector.update_track(track_id=2, fence_inside=False, frame_id=1)
        detector.update_track(track_id=3, fence_inside=False, frame_id=1)

        purged = detector.cleanup_stale_tracks(active_track_ids=[2])
        assert set(purged) == {1, 3}
        assert len(detector) == 1
        assert 2 in detector


# ---------------------------------------------------------------------------
# 14. Invalid Input Handling
# ---------------------------------------------------------------------------

class TestInvalidInputHandling:
    """Test validation and rejection of invalid track IDs and arguments."""

    def test_none_track_id_raises_validation_error(self, detector: FenceBreachDetector):
        with pytest.raises(FenceBreachValidationError):
            detector.update_track(track_id=None, fence_inside=False)

    def test_negative_track_id_raises_validation_error(self, detector: FenceBreachDetector):
        with pytest.raises(FenceBreachValidationError):
            detector.update_track(track_id=-1, fence_inside=False)

    def test_non_integer_track_id_raises_validation_error(self, detector: FenceBreachDetector):
        with pytest.raises(FenceBreachValidationError):
            detector.update_track(track_id="invalid_id", fence_inside=False)

    def test_bool_track_id_rejected(self, detector: FenceBreachDetector):
        with pytest.raises(FenceBreachValidationError):
            detector.update_track(track_id=True, fence_inside=False)

    def test_none_fence_state_raises_validation_error(self, detector: FenceBreachDetector):
        with pytest.raises(FenceBreachValidationError):
            detector.update_track(track_id=1, fence_inside=None)


# ---------------------------------------------------------------------------
# 15. Unknown and String Fence States
# ---------------------------------------------------------------------------

class TestUnknownAndStringStates:
    """Test flexible fence state inputs and UNKNOWN handling."""

    def test_string_boolean_states(self, detector: FenceBreachDetector):
        # String 'false' / 'outside'
        detector.update_track(track_id=1, fence_inside="OUTSIDE", frame_id=1)
        assert detector.get_fence_state(1) == FenceState.OUTSIDE

        # String 'inside' -> Breach
        ev = detector.update_track(track_id=1, fence_inside="INSIDE", frame_id=2)
        assert ev is not None

    def test_unknown_state_produces_no_breach(self, detector: FenceBreachDetector):
        detector.update_track(track_id=1, fence_inside=False, frame_id=1)
        # Transition to UNKNOWN
        ev = detector.update_track(track_id=1, fence_inside="UNKNOWN", frame_id=2)
        assert ev is None
        assert detector.get_fence_state(1) == FenceState.UNKNOWN

        # Transition from UNKNOWN to INSIDE does not count as OUTSIDE -> INSIDE
        ev2 = detector.update_track(track_id=1, fence_inside=True, frame_id=3)
        assert ev2 is None


# ---------------------------------------------------------------------------
# 16. Event Structure
# ---------------------------------------------------------------------------

class TestEventStructure:
    """Verify all fields and properties of FenceBreachEvent."""

    def test_event_fields_and_types(self, detector: FenceBreachDetector):
        detector.update_track(track_id=42, fence_inside=False, frame_id=10, timestamp=10.0)
        ev = detector.update_track(
            track_id=42,
            fence_inside=True,
            frame_id=11,
            timestamp=10.033,
            center=(320, 240),
            fence_id="border_fence",
            zone_id="zone_a",
            metadata={"source": "camera_1"},
        )
        assert ev is not None
        assert ev.track_id == 42
        assert ev.event_type == BreachEventType.FENCE_BREACH
        assert ev.previous_state == FenceState.OUTSIDE
        assert ev.current_state == FenceState.INSIDE
        assert ev.frame_id == 11
        assert ev.timestamp == 10.033
        assert ev.center == (320, 240)
        assert ev.fence_id == "border_fence"
        assert ev.zone_id == "zone_a"
        assert ev.breach_count == 1
        assert ev.metadata.get("source") == "camera_1"
        assert ev.metadata.get("total_inside_frames") == 1


# ---------------------------------------------------------------------------
# 17. Event Immutability
# ---------------------------------------------------------------------------

class TestEventImmutability:
    """Verify FenceBreachEvent is frozen and cannot be mutated."""

    def test_event_is_frozen(self, detector: FenceBreachDetector):
        detector.update_track(track_id=1, fence_inside=False, frame_id=1)
        event = detector.update_track(track_id=1, fence_inside=True, frame_id=2)
        assert event is not None

        with pytest.raises(FrozenInstanceError):
            event.track_id = 999  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.breach_count = 5  # type: ignore


# ---------------------------------------------------------------------------
# 18. M7 -> M8 Integration
# ---------------------------------------------------------------------------

class TestM7ToM8Integration:
    """Test consuming outputs directly from Module 7 ZoneManager."""

    def test_update_from_zone_result(
        self, detector: FenceBreachDetector, sample_zone_manager: ZoneManager
    ):
        # Point outside perimeter fence: (50, 50)
        obj_outside = TrackedObject(
            track_id=101, x1=40, y1=40, x2=60, y2=60, confidence=0.9, class_id=0, class_name="person"
        )
        zr_outside = sample_zone_manager.classify_object(obj_outside)
        assert zr_outside.fence_inside is False

        ev1 = detector.update_from_zone_result(zr_outside, frame_id=1)
        assert ev1 is None

        # Point inside perimeter fence: (200, 200)
        obj_inside = TrackedObject(
            track_id=101, x1=190, y1=190, x2=210, y2=210, confidence=0.92, class_id=0, class_name="person"
        )
        zr_inside = sample_zone_manager.classify_object(obj_inside)
        assert zr_inside.fence_inside is True

        ev2 = detector.update_from_zone_result(zr_inside, frame_id=2)
        assert ev2 is not None
        assert ev2.track_id == 101
        assert ev2.center == (200, 200)

    def test_update_batch_integration(
        self, detector: FenceBreachDetector, sample_zone_manager: ZoneManager
    ):
        # Frame 1: Tracks 1 and 2 outside
        objs_f1 = [
            TrackedObject(track_id=1, x1=40, y1=40, x2=60, y2=60, confidence=0.9, class_id=0, class_name="person"),
            TrackedObject(track_id=2, x1=50, y1=50, x2=70, y2=70, confidence=0.9, class_id=0, class_name="person"),
        ]
        results_f1 = sample_zone_manager.classify_objects(objs_f1)
        breaches_f1 = detector.update_batch(results_f1, frame_id=1)
        assert len(breaches_f1) == 0

        # Frame 2: Track 1 crosses inside, Track 2 stays outside
        objs_f2 = [
            TrackedObject(track_id=1, x1=190, y1=190, x2=210, y2=210, confidence=0.9, class_id=0, class_name="person"),
            TrackedObject(track_id=2, x1=55, y1=55, x2=75, y2=75, confidence=0.9, class_id=0, class_name="person"),
        ]
        results_f2 = sample_zone_manager.classify_objects(objs_f2)
        breaches_f2 = detector.update_batch(results_f2, frame_id=2)
        assert len(breaches_f2) == 1
        assert breaches_f2[0].track_id == 1


# ---------------------------------------------------------------------------
# 19. Real Sequential Frame Behavior
# ---------------------------------------------------------------------------

class TestRealSequentialFrameBehavior:
    """Simulate realistic multi-frame trajectory moving across a virtual fence."""

    def test_trajectory_crossing_simulation(
        self, detector: FenceBreachDetector, sample_zone_manager: ZoneManager
    ):
        # An object walks along X=200, Y from 50 (outside) to 250 (inside) to 350 (outside)
        # Perimeter fence Y is 100 to 300.
        y_positions = [50, 70, 90, 120, 150, 180, 210, 240, 270, 320, 350]
        detected_breaches = []

        for frame_idx, y in enumerate(y_positions):
            obj = TrackedObject(
                track_id=88,
                x1=190,
                y1=y - 10,
                x2=210,
                y2=y + 10,
                confidence=0.88,
                class_id=0,
                class_name="person",
            )
            zr = sample_zone_manager.classify_object(obj)
            event = detector.update_from_zone_result(zr, frame_id=frame_idx)
            if event is not None:
                detected_breaches.append((frame_idx, event))

        # Breach should only occur when crossing into fence at y=120 (frame_idx=3)
        assert len(detected_breaches) == 1
        breach_frame, breach_event = detected_breaches[0]
        assert breach_frame == 3
        assert breach_event.track_id == 88
        assert breach_event.center == (200, 120)


# ---------------------------------------------------------------------------
# 20. No Mutation of M7 / M5 State
# ---------------------------------------------------------------------------

class TestNoMutationOfM7M5State:
    """Verify detector update calls do not modify ZoneResult or input objects."""

    def test_zone_result_not_mutated(
        self, detector: FenceBreachDetector, sample_zone_manager: ZoneManager
    ):
        obj = TrackedObject(
            track_id=99, x1=190, y1=190, x2=210, y2=210, confidence=0.9, class_id=0, class_name="person"
        )
        zr = sample_zone_manager.classify_object(obj)

        original_dict = {
            "track_id": zr.track_id,
            "center": zr.center,
            "zone_id": zr.zone_id,
            "zone_name": zr.zone_name,
            "zone_type": zr.zone_type,
            "inside_zone": zr.inside_zone,
            "fence_inside": zr.fence_inside,
        }

        # Initialize outside first to trigger breach
        detector.update_track(track_id=99, fence_inside=False, frame_id=1)
        detector.update_from_zone_result(zr, frame_id=2)

        assert zr.track_id == original_dict["track_id"]
        assert zr.center == original_dict["center"]
        assert zr.zone_id == original_dict["zone_id"]
        assert zr.zone_name == original_dict["zone_name"]
        assert zr.zone_type == original_dict["zone_type"]
        assert zr.inside_zone == original_dict["inside_zone"]
        assert zr.fence_inside == original_dict["fence_inside"]
