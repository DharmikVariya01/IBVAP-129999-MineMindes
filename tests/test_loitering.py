"""Comprehensive Unit and Integration Tests for Module 9: Loitering Detection.

Tests cover all 25 required criteria:
 1. Initial track observation (first observation rule: NOT_LOITERING, no event)
 2. Below 30 seconds (accumulating duration, no event)
 3. Exactly 30 seconds threshold (triggers LOITERING event)
 4. Above 30 seconds (maintains LOITERING, no duplicate event)
 5. Stationary object (stays at identical coordinate -> LOITERING)
 6. Small tracker jitter noise (within spatial_radius -> LOITERING)
 7. Continuously moving object (moves across scene -> NOT_LOITERING)
 8. Large spatial movement (> spatial_radius -> resets anchor and duration)
 9. Localized prolonged movement (wandering within radius -> LOITERING)
10. Duplicate trigger prevention (stays for 45+ seconds -> exactly 1 event)
11. Re-qualification after leaving area (exits, resets, settles again -> 2nd event)
12. Multiple concurrent track IDs (evaluated simultaneously)
13. Strict track isolation (Track A loitering does not affect Track B)
14. Reset all lifecycle (clears all tracks and counters)
15. Reset one track (resets target track, others unaffected)
16. Stale track cleanup (purges inactive tracks, preserves active ones)
17. Invalid input validation (negative ID, non-int, NaN coords, invalid config)
18. Missing / insufficient history (< min_observations guards against premature trigger)
19. Result structure verification (all fields, types, and values)
20. Dataclass immutability (frozen instances raise FrozenInstanceError on mutation)
21. M5 -> M9 integration (EventMemory and TrackMemory passed directly)
22. M7 zone metadata integration (zone_id, zone_name, zone_type attached)
23. M8 independence (FenceBreachDetector and LoiteringDetector operate independently)
24. Time calculation correctness (datetime, float timestamp, and FPS frame delta)
25. Realistic sequential frame-by-frame simulation
"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
import math
from pathlib import Path
import sys
from typing import List, Tuple

import pytest
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.event_memory import EventMemory, PositionalObservation, TrackMemory
from ai_engine.fence_breach import FenceBreachDetector, FenceState
from ai_engine.loitering import (
    DEFAULT_LOITERING_DURATION,
    DEFAULT_MIN_OBSERVATIONS,
    DEFAULT_SPATIAL_RADIUS,
    LoiteringDetector,
    LoiteringError,
    LoiteringEvent,
    LoiteringResult,
    LoiteringState,
    LoiteringValidationError,
    TrackLoiteringState,
)
from ai_engine.tracker import TrackedObject
from ai_engine.zones import Zone, ZoneManager, ZoneResult, ZoneType


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def detector() -> LoiteringDetector:
    """Fresh instance of LoiteringDetector with default 30.0s threshold."""
    return LoiteringDetector(
        loitering_duration_seconds=30.0,
        spatial_radius=50.0,
        min_observations=5,
    )


def _make_tracked(
    track_id: int = 1,
    center: Tuple[float, float] = (100.0, 100.0),
    w: int = 40,
    h: int = 80,
    conf: float = 0.90,
    class_name: str = "person",
) -> TrackedObject:
    """Helper to create a TrackedObject with specified centroid."""
    cx, cy = center
    x1 = int(round(cx - w / 2))
    y1 = int(round(cy - h / 2))
    x2 = int(round(cx + w / 2))
    y2 = int(round(cy + h / 2))
    return TrackedObject(
        track_id=track_id,
        class_id=0,
        class_name=class_name,
        confidence=conf,
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
    )


# ---------------------------------------------------------------------------
# Test 1: Initial Track Observation
# ---------------------------------------------------------------------------

def test_01_initial_track_observation(detector: LoiteringDetector) -> None:
    """First observation of a track must initialize anchor and NOT be loitering."""
    res = detector.update(track_id=1, center=(200.0, 300.0), timestamp=0.0, frame_id=1)

    assert res.track_id == 1
    assert res.state == LoiteringState.NOT_LOITERING
    assert not res.is_loitering
    assert res.duration_seconds == 0.0
    assert res.spatial_displacement == 0.0
    assert res.anchor_center == (200.0, 300.0)
    assert res.current_center == (200.0, 300.0)
    assert res.observations_count == 1
    assert res.new_event is None
    assert detector.total_loitering_events == 0


# ---------------------------------------------------------------------------
# Test 2: Below 30 Seconds
# ---------------------------------------------------------------------------

def test_02_below_30_seconds(detector: LoiteringDetector) -> None:
    """Track remaining localized below 30.0s must not trigger loitering."""
    # Feed 10 observations across 25.0 seconds
    for step in range(10):
        t = step * 2.5  # up to 22.5s
        res = detector.update(track_id=1, center=(100.0, 100.0), timestamp=t, frame_id=step + 1)
        assert res.state == LoiteringState.NOT_LOITERING
        assert not res.is_loitering
        assert res.new_event is None

    assert detector.get_duration(track_id=1) == pytest.approx(22.5, rel=1e-3)
    assert detector.total_loitering_events == 0


# ---------------------------------------------------------------------------
# Test 3: Exactly 30 Seconds
# ---------------------------------------------------------------------------

def test_03_exactly_30_seconds(detector: LoiteringDetector) -> None:
    """Reaching exactly 30.0s with >= min_observations triggers LOITERING once."""
    for step in range(6):
        t = step * 5.0  # 0, 5, 10, 15, 20, 25
        detector.update(track_id=1, center=(100.0, 100.0), timestamp=t, frame_id=step + 1)

    # Frame at exactly 30.0 seconds
    res = detector.update(track_id=1, center=(102.0, 101.0), timestamp=30.0, frame_id=7)

    assert res.state == LoiteringState.LOITERING
    assert res.is_loitering
    assert res.duration_seconds == pytest.approx(30.0, rel=1e-3)
    assert res.new_event is not None
    assert isinstance(res.new_event, LoiteringEvent)
    assert res.new_event.track_id == 1
    assert res.new_event.event_type == "LOITERING"
    assert res.new_event.threshold_seconds == 30.0
    assert detector.total_loitering_events == 1


# ---------------------------------------------------------------------------
# Test 4: Above 30 Seconds
# ---------------------------------------------------------------------------

def test_04_above_30_seconds_continuation(detector: LoiteringDetector) -> None:
    """Remaining localized beyond 30.0s maintains LOITERING and emits no duplicate event."""
    # Reach 30s
    for step in range(7):
        detector.update(track_id=1, center=(100.0, 100.0), timestamp=step * 5.0, frame_id=step + 1)

    assert detector.is_loitering(track_id=1)
    assert detector.total_loitering_events == 1

    # Next observation at 35s
    res35 = detector.update(track_id=1, center=(101.0, 100.0), timestamp=35.0, frame_id=8)
    assert res35.state == LoiteringState.LOITERING
    assert res35.is_loitering
    assert res35.duration_seconds == pytest.approx(35.0, rel=1e-3)
    assert res35.new_event is None  # Duplicate trigger prevented!

    # Next observation at 45s
    res45 = detector.update(track_id=1, center=(103.0, 102.0), timestamp=45.0, frame_id=9)
    assert res45.state == LoiteringState.LOITERING
    assert res45.is_loitering
    assert res45.duration_seconds == pytest.approx(45.0, rel=1e-3)
    assert res45.new_event is None
    assert detector.total_loitering_events == 1


# ---------------------------------------------------------------------------
# Test 5: Stationary Object
# ---------------------------------------------------------------------------

def test_05_stationary_object(detector: LoiteringDetector) -> None:
    """An object stationary at the exact same point triggers loitering at 30s."""
    pos = (450.0, 220.0)
    for step in range(31):
        t = float(step)
        res = detector.update(track_id=5, center=pos, timestamp=t, frame_id=step + 1)

    assert res.is_loitering
    assert res.spatial_displacement == 0.0
    assert detector.get_state(track_id=5) == LoiteringState.LOITERING


# ---------------------------------------------------------------------------
# Test 6: Small Tracker Jitter Noise
# ---------------------------------------------------------------------------

def test_06_small_tracker_jitter(detector: LoiteringDetector) -> None:
    """Detector centroid noise (e.g. ±3px) within spatial_radius triggers loitering."""
    base_pos = (300.0, 300.0)
    jitter_offsets = [(0, 0), (2, -1), (-2, 3), (1, -2), (3, 1), (-1, -1)]

    for step in range(31):
        dx, dy = jitter_offsets[step % len(jitter_offsets)]
        curr_pos = (base_pos[0] + dx, base_pos[1] + dy)
        res = detector.update(track_id=6, center=curr_pos, timestamp=float(step), frame_id=step + 1)

    assert res.is_loitering
    assert res.spatial_displacement <= 5.0
    assert res.spatial_displacement <= detector.spatial_radius


# ---------------------------------------------------------------------------
# Test 7: Continuously Moving Object
# ---------------------------------------------------------------------------

def test_07_continuously_moving_object(detector: LoiteringDetector) -> None:
    """An object moving steadily across the camera for 60s is NEVER loitering."""
    # Moves 5 pixels per second for 60 seconds (total 300 pixels)
    for step in range(61):
        t = float(step)
        x = 100.0 + step * 5.0
        y = 200.0
        res = detector.update(track_id=7, center=(x, y), timestamp=t, frame_id=step + 1)
        # At no point should it become LOITERING
        assert res.state == LoiteringState.NOT_LOITERING
        assert not res.is_loitering
        assert res.new_event is None

    assert detector.total_loitering_events == 0
    assert not detector.is_loitering(track_id=7)


# ---------------------------------------------------------------------------
# Test 8: Large Spatial Movement Resets Anchor
# ---------------------------------------------------------------------------

def test_08_large_spatial_movement_resets(detector: LoiteringDetector) -> None:
    """Displacement > spatial_radius resets anchor and resets duration to 0."""
    # Stay localized for 20 seconds at (100, 100)
    for step in range(5):
        detector.update(track_id=8, center=(100.0, 100.0), timestamp=step * 5.0, frame_id=step + 1)

    assert detector.get_duration(track_id=8) == pytest.approx(20.0)

    # Sudden move to (300, 100) (displacement 200px > radius 50px) at t=25s
    res = detector.update(track_id=8, center=(300.0, 100.0), timestamp=25.0, frame_id=6)

    assert res.state == LoiteringState.NOT_LOITERING
    assert res.duration_seconds == 0.0
    assert res.anchor_center == (300.0, 100.0)
    assert res.current_center == (300.0, 100.0)
    assert res.observations_count == 1
    assert not res.is_loitering


# ---------------------------------------------------------------------------
# Test 9: Localized Prolonged Movement
# ---------------------------------------------------------------------------

def test_09_localized_prolonged_movement(detector: LoiteringDetector) -> None:
    """Wandering in a small circle (radius 20px < spatial_radius 50px) triggers loitering."""
    center_anchor = (500.0, 500.0)
    for step in range(35):
        t = float(step)
        angle = step * 0.5
        x = center_anchor[0] + 20.0 * math.cos(angle)
        y = center_anchor[1] + 20.0 * math.sin(angle)
        res = detector.update(track_id=9, center=(x, y), timestamp=t, frame_id=step + 1)

    assert res.is_loitering
    assert res.state == LoiteringState.LOITERING
    assert detector.total_loitering_events == 1


# ---------------------------------------------------------------------------
# Test 10: Duplicate Trigger Prevention
# ---------------------------------------------------------------------------

def test_10_duplicate_trigger_prevention(detector: LoiteringDetector) -> None:
    """Remaining in loitering state for 100 frames emits exactly ONE LoiteringEvent."""
    event_count = 0
    for frame in range(1, 101):
        t = frame * 0.5  # total 50.0s
        res = detector.update(track_id=10, center=(250.0, 250.0), timestamp=t, frame_id=frame)
        if res.new_event is not None:
            event_count += 1

    assert event_count == 1
    assert detector.total_loitering_events == 1
    assert detector.is_loitering(track_id=10)


# ---------------------------------------------------------------------------
# Test 11: Re-qualification After Leaving Area
# ---------------------------------------------------------------------------

def test_11_requalification_after_leaving(detector: LoiteringDetector) -> None:
    """Leaving area ends loitering; settling into new area triggers 2nd loitering event."""
    # 1. First loitering episode at (100, 100) for 32 seconds
    for step in range(33):
        res = detector.update(track_id=11, center=(100.0, 100.0), timestamp=float(step), frame_id=step + 1)
    assert res.is_loitering
    assert detector.total_loitering_events == 1

    # 2. Object walks away to (400, 400) at t=33
    res_leave = detector.update(track_id=11, center=(400.0, 400.0), timestamp=33.0, frame_id=34)
    assert res_leave.state == LoiteringState.NOT_LOITERING
    assert not res_leave.is_loitering
    assert res_leave.duration_seconds == 0.0

    # 3. Object settles at (400, 400) from t=33 to t=65 (32 seconds)
    events_in_phase2 = 0
    for step in range(34, 66):
        res2 = detector.update(track_id=11, center=(400.0, 400.0), timestamp=float(step), frame_id=step + 1)
        if res2.new_event is not None:
            events_in_phase2 += 1
            assert res2.new_event.loitering_count == 2

    assert events_in_phase2 == 1
    assert detector.total_loitering_events == 2
    assert detector.is_loitering(track_id=11)


# ---------------------------------------------------------------------------
# Test 12: Multiple Track IDs
# ---------------------------------------------------------------------------

def test_12_multiple_track_ids(detector: LoiteringDetector) -> None:
    """Multiple tracks can be monitored simultaneously."""
    for step in range(35):
        t = float(step)
        # Track 101 stays at (100, 100) -> loiters
        r1 = detector.update(track_id=101, center=(100.0, 100.0), timestamp=t, frame_id=step + 1)
        # Track 102 stays at (800, 400) -> loiters
        r2 = detector.update(track_id=102, center=(800.0, 400.0), timestamp=t, frame_id=step + 1)

    assert r1.is_loitering
    assert r2.is_loitering
    assert detector.tracked_count == 2
    assert detector.active_loitering_count == 2
    assert detector.total_loitering_events == 2


# ---------------------------------------------------------------------------
# Test 13: Track Isolation
# ---------------------------------------------------------------------------

def test_13_track_isolation(detector: LoiteringDetector) -> None:
    """Track A loitering must not leak state to Track B moving."""
    for step in range(35):
        t = float(step)
        # Track A stationary
        detector.update(track_id=1, center=(100.0, 100.0), timestamp=t, frame_id=step + 1)
        # Track B moving across
        detector.update(track_id=2, center=(100.0 + step * 10.0, 300.0), timestamp=t, frame_id=step + 1)

    assert detector.is_loitering(track_id=1)
    assert not detector.is_loitering(track_id=2)
    assert detector.get_state(track_id=1) == LoiteringState.LOITERING
    assert detector.get_state(track_id=2) == LoiteringState.NOT_LOITERING


# ---------------------------------------------------------------------------
# Test 14: Reset All Lifecycle
# ---------------------------------------------------------------------------

def test_14_reset_all_lifecycle(detector: LoiteringDetector) -> None:
    """reset() clears all tracks and event counters."""
    detector.update(track_id=1, center=(100.0, 100.0), timestamp=0.0, frame_id=1)
    detector.update(track_id=2, center=(200.0, 200.0), timestamp=0.0, frame_id=1)
    assert detector.tracked_count == 2

    detector.reset()
    assert detector.tracked_count == 0
    assert detector.active_loitering_count == 0
    assert detector.total_loitering_events == 0
    assert not detector.is_loitering(track_id=1)


# ---------------------------------------------------------------------------
# Test 15: Reset One Track
# ---------------------------------------------------------------------------

def test_15_reset_one_track(detector: LoiteringDetector) -> None:
    """reset_track(id) removes target track without affecting other tracks."""
    for step in range(35):
        t = float(step)
        detector.update(track_id=1, center=(100.0, 100.0), timestamp=t, frame_id=step + 1)
        detector.update(track_id=2, center=(500.0, 500.0), timestamp=t, frame_id=step + 1)

    assert detector.is_loitering(track_id=1)
    assert detector.is_loitering(track_id=2)

    removed = detector.reset_track(track_id=1)
    assert removed
    assert not detector.is_loitering(track_id=1)
    assert detector.is_loitering(track_id=2)  # Track 2 unaffected!
    assert detector.tracked_count == 1

    # Resetting nonexistent track returns False
    assert not detector.reset_track(track_id=999)


# ---------------------------------------------------------------------------
# Test 16: Stale Track Cleanup
# ---------------------------------------------------------------------------

def test_16_stale_track_cleanup(detector: LoiteringDetector) -> None:
    """cleanup_stale_tracks purges inactive tracks."""
    detector.update(track_id=1, center=(100.0, 100.0), timestamp=0.0, frame_id=1)
    detector.update(track_id=2, center=(200.0, 200.0), timestamp=0.0, frame_id=1)
    detector.update(track_id=3, center=(300.0, 300.0), timestamp=0.0, frame_id=1)
    assert detector.tracked_count == 3

    # Only track 2 is active in current frame
    removed = detector.cleanup_stale_tracks(active_track_ids=[2])
    assert set(removed) == {1, 3}
    assert detector.tracked_count == 1
    assert detector.get_track_state(2) is not None


# ---------------------------------------------------------------------------
# Test 17: Invalid Input Validation
# ---------------------------------------------------------------------------

def test_17_invalid_input_validation(detector: LoiteringDetector) -> None:
    """Invalid parameters raise LoiteringValidationError."""
    # Negative track_id
    with pytest.raises(LoiteringValidationError):
        detector.update(track_id=-1, center=(100.0, 100.0))

    # Zero track_id
    with pytest.raises(LoiteringValidationError):
        detector.update(track_id=0, center=(100.0, 100.0))

    # String track_id
    with pytest.raises(LoiteringValidationError):
        detector.update(track_id="1", center=(100.0, 100.0))  # type: ignore

    # Invalid center format
    with pytest.raises(LoiteringValidationError):
        detector.update(track_id=1, center=(100.0,))  # type: ignore

    # NaN coordinates
    with pytest.raises(LoiteringValidationError):
        detector.update(track_id=1, center=(float("nan"), 100.0))

    # Negative duration threshold in constructor
    with pytest.raises(LoiteringValidationError):
        LoiteringDetector(loitering_duration_seconds=-5.0)

    # Zero radius
    with pytest.raises(LoiteringValidationError):
        LoiteringDetector(spatial_radius=0.0)


# ---------------------------------------------------------------------------
# Test 18: Missing / Insufficient History
# ---------------------------------------------------------------------------

def test_18_insufficient_history(detector: LoiteringDetector) -> None:
    """Track reaching 30s with fewer observations than min_observations is guarded."""
    det = LoiteringDetector(loitering_duration_seconds=30.0, min_observations=10)

    # Only 3 observations at t=0, t=15, t=32
    det.update(track_id=1, center=(100.0, 100.0), timestamp=0.0, frame_id=1)
    det.update(track_id=1, center=(100.0, 100.0), timestamp=15.0, frame_id=2)
    res = det.update(track_id=1, center=(100.0, 100.0), timestamp=32.0, frame_id=3)

    # Duration is 32s, but observations_count is 3 < 10
    assert res.state == LoiteringState.NOT_LOITERING
    assert not res.is_loitering
    assert res.new_event is None


# ---------------------------------------------------------------------------
# Test 19: Result Structure Verification
# ---------------------------------------------------------------------------

def test_19_result_structure_verification(detector: LoiteringDetector) -> None:
    """Verify all fields and types of LoiteringResult."""
    res = detector.update(
        track_id=19,
        center=(150.0, 250.0),
        timestamp=1.5,
        frame_id=10,
        zone_id="zone_a",
        zone_name="Zone Alpha",
        zone_type="RESTRICTED",
    )

    assert isinstance(res, LoiteringResult)
    assert res.track_id == 19
    assert isinstance(res.state, LoiteringState)
    assert isinstance(res.is_loitering, bool)
    assert isinstance(res.duration_seconds, float)
    assert isinstance(res.spatial_displacement, float)
    assert isinstance(res.spatial_radius, float)
    assert isinstance(res.threshold_seconds, float)
    assert isinstance(res.anchor_center, tuple)
    assert isinstance(res.current_center, tuple)
    assert isinstance(res.observations_count, int)
    assert isinstance(res.status_reason, str)
    assert res.zone_id == "zone_a"
    assert res.zone_name == "Zone Alpha"
    assert res.zone_type == "RESTRICTED"


# ---------------------------------------------------------------------------
# Test 20: Result Immutability
# ---------------------------------------------------------------------------

def test_20_result_immutability(detector: LoiteringDetector) -> None:
    """LoiteringResult and LoiteringEvent are frozen dataclasses."""
    for step in range(7):
        res = detector.update(track_id=20, center=(100.0, 100.0), timestamp=step * 5.0, frame_id=step + 1)

    # Attempt mutation on LoiteringResult
    with pytest.raises(FrozenInstanceError):
        res.is_loitering = False  # type: ignore

    # Attempt mutation on LoiteringEvent
    assert res.new_event is not None
    with pytest.raises(FrozenInstanceError):
        res.new_event.duration_seconds = 100.0  # type: ignore


# ---------------------------------------------------------------------------
# Test 21: M5 -> M9 Integration
# ---------------------------------------------------------------------------

def test_21_m5_to_m9_integration() -> None:
    """EventMemory and TrackMemory update LoiteringDetector via update_from_memory."""
    memory = EventMemory(max_history=50)
    detector = LoiteringDetector(loitering_duration_seconds=10.0, min_observations=3)

    t0 = datetime(2026, 9, 12, 12, 0, 0)
    for i in range(5):
        t = t0 + timedelta(seconds=i * 3.0)  # 0s, 3s, 6s, 9s, 12s
        obj = _make_tracked(track_id=21, center=(200.0, 200.0))
        memory.update(obj, frame_time=t)
        results = detector.update_from_memory(memory, active_track_ids=[21], frame_id=i + 1, timestamp=t)

    assert len(results) == 1
    assert results[0].is_loitering
    assert results[0].duration_seconds == pytest.approx(12.0)
    assert detector.total_loitering_events == 1


# ---------------------------------------------------------------------------
# Test 22: M7 Zone Metadata Integration
# ---------------------------------------------------------------------------

def test_22_zone_metadata_integration() -> None:
    """Loitering results and events attach M7 zone metadata when provided."""
    zm = ZoneManager()
    zm.create_zone(
        zone_id="restricted_vault",
        zone_name="Cash Vault Area",
        zone_type=ZoneType.RESTRICTED,
        polygon=[(0, 0), (500, 0), (500, 500), (0, 500)],
    )

    detector = LoiteringDetector(loitering_duration_seconds=5.0, min_observations=3)
    t0 = datetime(2026, 9, 12, 10, 0, 0)

    for i in range(4):
        t = t0 + timedelta(seconds=i * 2.0)  # 0s, 2s, 4s, 6s
        obj = _make_tracked(track_id=22, center=(250.0, 250.0))
        zone_results = zm.classify_objects([obj])

        res = detector.update(
            track_id=22,
            center=(250.0, 250.0),
            timestamp=t,
            frame_id=i + 1,
            zone_id=zone_results[0].zone_id,
            zone_name=zone_results[0].zone_name,
            zone_type=zone_results[0].zone_type.value if zone_results[0].zone_type else None,
        )

    assert res.is_loitering
    assert res.zone_id == "restricted_vault"
    assert res.zone_name == "Cash Vault Area"
    assert res.zone_type == "RESTRICTED"
    assert res.new_event is not None
    assert res.new_event.zone_id == "restricted_vault"
    assert res.new_event.zone_name == "Cash Vault Area"


# ---------------------------------------------------------------------------
# Test 23: M8 Independence
# ---------------------------------------------------------------------------

def test_23_m8_independence() -> None:
    """FenceBreachDetector (M8) and LoiteringDetector (M9) operate independently."""
    breach_det = FenceBreachDetector(default_fence_id="main_fence")
    loiter_det = LoiteringDetector(loitering_duration_seconds=10.0, min_observations=3)

    # Object crosses fence at frame 2, then stays inside from frame 2 to 10 (20s)
    # OUTSIDE at frame 1
    b_ev1 = breach_det.update_track(23, False, frame_id=1, timestamp=0.0, center=(50, 50))
    l_res1 = loiter_det.update(23, center=(50.0, 50.0), frame_id=1, timestamp=0.0)
    assert b_ev1 is None
    assert not l_res1.is_loitering

    # INSIDE at frame 2 -> M8 triggers breach event, M9 does NOT loiter yet
    b_ev2 = breach_det.update_track(23, True, frame_id=2, timestamp=2.0, center=(150, 150))
    l_res2 = loiter_det.update(23, center=(150.0, 150.0), frame_id=2, timestamp=2.0)
    assert b_ev2 is not None
    assert b_ev2.previous_state == FenceState.OUTSIDE
    assert b_ev2.current_state == FenceState.INSIDE
    assert not l_res2.is_loitering

    # Continue staying inside until t=15s -> M8 emits NO more breaches, M9 triggers loitering
    for i in range(3, 9):
        t = float(i * 2.0)
        b_ev = breach_det.update_track(23, True, frame_id=i, timestamp=t, center=(150, 150))
        l_res = loiter_det.update(23, center=(150.0, 150.0), frame_id=i, timestamp=t)
        assert b_ev is None  # M8 duplicate protection

    assert l_res.is_loitering  # M9 triggered at t >= 10s
    assert breach_det.total_breaches == 1
    assert loiter_det.total_loitering_events == 1


# ---------------------------------------------------------------------------
# Test 24: Time Calculation Correctness
# ---------------------------------------------------------------------------

def test_24_time_calculation_correctness() -> None:
    """Exact time calculation verified across datetimes, float timestamps, and FPS delta."""
    # Sub-test A: Datetimes
    det_dt = LoiteringDetector(loitering_duration_seconds=30.0)
    t0 = datetime(2026, 9, 12, 14, 0, 0)
    for i in range(7):
        t = t0 + timedelta(seconds=i * 5.0)
        res = det_dt.update(track_id=1, center=(10.0, 10.0), timestamp=t, frame_id=i + 1)
    assert res.is_loitering
    assert res.duration_seconds == pytest.approx(30.0)

    # Sub-test B: Float timestamps
    det_fl = LoiteringDetector(loitering_duration_seconds=30.0)
    for i in range(7):
        t = float(i * 5.0)
        res = det_fl.update(track_id=2, center=(10.0, 10.0), timestamp=t, frame_id=i + 1)
    assert res.is_loitering
    assert res.duration_seconds == pytest.approx(30.0)

    # Sub-test C: FPS frame calculation (e.g. 30 FPS, no timestamp passed)
    det_fps = LoiteringDetector(loitering_duration_seconds=30.0, fps=30.0)
    # 30 seconds at 30 fps = 900 frames
    res_start = det_fps.update(track_id=3, center=(10.0, 10.0), frame_id=0)
    assert res_start.duration_seconds == 0.0

    for f in [100, 300, 600, 899]:
        r = det_fps.update(track_id=3, center=(10.0, 10.0), frame_id=f)
        assert not r.is_loitering

    res_900 = det_fps.update(track_id=3, center=(10.0, 10.0), frame_id=900)
    assert res_900.is_loitering
    assert res_900.duration_seconds == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# Test 25: Realistic Sequential Observations
# ---------------------------------------------------------------------------

def test_25_realistic_sequential_observations() -> None:
    """Simulates realistic sequential video frame stream over 40 seconds."""
    detector = LoiteringDetector(loitering_duration_seconds=30.0, spatial_radius=40.0)

    # Video runs at 10 FPS: 400 frames total (40.0 seconds)
    loitering_onset_frame = None
    for frame in range(1, 401):
        timestamp = frame / 10.0
        # Stationary person with realistic jitter ±1.5px
        cx = 640.0 + 1.5 * math.sin(frame * 0.3)
        cy = 360.0 + 1.2 * math.cos(frame * 0.4)

        res = detector.update(
            track_id=42,
            center=(cx, cy),
            timestamp=timestamp,
            frame_id=frame,
        )

        if res.new_event is not None:
            loitering_onset_frame = frame

    # At 10 FPS, 30 seconds is reached around frame 301
    assert loitering_onset_frame is not None
    assert loitering_onset_frame == 301
    assert detector.is_loitering(track_id=42)
    assert detector.total_loitering_events == 1
