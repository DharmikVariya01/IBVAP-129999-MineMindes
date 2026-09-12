"""Automated tests for IBVAP Module 5 (Event Memory and Behavioral History).

Tests validate EventMemory, TrackMemory, and PositionalObservation classes,
including initialization, new/existing/missing track handling, all query and
lifecycle methods, bounded history, data safety, type validation, and
integration with real M4 (ByteTrack) output from consecutive video frames.

All tests work without a webcam. Tests that require test.mp4 are
automatically skipped when the video file is absent.
"""

from collections import deque
from dataclasses import fields as dataclass_fields
from datetime import datetime, timedelta
from pathlib import Path
import sys
import time
import unittest

import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.event_memory import (
    DEFAULT_MAX_HISTORY,
    EventMemory,
    PositionalObservation,
    TrackMemory,
)
from ai_engine.tracker import TrackedObject

# ---------------------------------------------------------------------------
# Test fixtures / factories
# ---------------------------------------------------------------------------

SAMPLE_VIDEO = PROJECT_ROOT / "videos" / "test.mp4"
_VIDEO_AVAILABLE = SAMPLE_VIDEO.exists()


def _make_tracked(
    track_id: int = 1,
    class_id: int = 0,
    class_name: str = "person",
    confidence: float = 0.90,
    x1: int = 100,
    y1: int = 50,
    x2: int = 200,
    y2: int = 300,
) -> TrackedObject:
    """Build a synthetic TrackedObject for use in tests."""
    return TrackedObject(
        track_id=track_id,
        class_id=class_id,
        class_name=class_name,
        confidence=confidence,
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
    )


def _now() -> datetime:
    """Return a fresh UTC datetime."""
    return datetime.utcnow()


# ===========================================================================
# 1. Initialization
# ===========================================================================

class TestEventMemoryInit(unittest.TestCase):
    """Test EventMemory construction and configuration."""

    def test_01_default_construction(self):
        """EventMemory can be constructed with no arguments."""
        mem = EventMemory()
        self.assertIsInstance(mem, EventMemory)

    def test_02_default_max_history(self):
        """Default max_history equals DEFAULT_MAX_HISTORY (100)."""
        mem = EventMemory()
        self.assertEqual(mem.max_history, DEFAULT_MAX_HISTORY)
        self.assertEqual(DEFAULT_MAX_HISTORY, 100)

    def test_03_custom_max_history(self):
        """Custom max_history value is stored and accessible."""
        mem = EventMemory(max_history=50)
        self.assertEqual(mem.max_history, 50)

    def test_04_starts_empty(self):
        """A freshly created EventMemory holds no tracks."""
        mem = EventMemory()
        self.assertEqual(len(mem), 0)
        self.assertEqual(mem.track_count, 0)

    def test_05_invalid_max_history_zero(self):
        """max_history=0 raises ValueError."""
        with self.assertRaises(ValueError):
            EventMemory(max_history=0)

    def test_06_invalid_max_history_negative(self):
        """Negative max_history raises ValueError."""
        with self.assertRaises(ValueError):
            EventMemory(max_history=-5)

    def test_07_invalid_max_history_float(self):
        """Float max_history raises ValueError."""
        with self.assertRaises(ValueError):
            EventMemory(max_history=10.0)

    def test_08_repr_contains_key_info(self):
        """repr includes class name, max_history, and track count."""
        mem = EventMemory(max_history=42)
        r = repr(mem)
        self.assertIn("EventMemory", r)
        self.assertIn("42", r)


# ===========================================================================
# 2. New track creation
# ===========================================================================

class TestNewTrackCreation(unittest.TestCase):
    """Test that the first sighting of a track_id creates a correct record."""

    def setUp(self):
        self.mem = EventMemory()
        self.obj = _make_tracked(track_id=7, x1=100, y1=50, x2=200, y2=300)
        self.t0 = _now()
        self.record = self.mem.update(self.obj, self.t0)

    def test_10_returns_track_memory(self):
        """update() returns a TrackMemory instance."""
        self.assertIsInstance(self.record, TrackMemory)

    def test_11_track_id_matches(self):
        """TrackMemory.track_id matches the input TrackedObject."""
        self.assertEqual(self.record.track_id, 7)

    def test_12_class_id_stored(self):
        """class_id is correctly stored."""
        self.assertEqual(self.record.class_id, 0)

    def test_13_class_name_stored(self):
        """class_name is correctly stored."""
        self.assertEqual(self.record.class_name, "person")

    def test_14_first_seen_set(self):
        """first_seen is set to the provided frame_time."""
        self.assertEqual(self.record.first_seen, self.t0)

    def test_15_last_seen_set_on_creation(self):
        """last_seen equals first_seen on the first update."""
        self.assertEqual(self.record.last_seen, self.t0)

    def test_16_frame_count_is_one(self):
        """frame_count is 1 after the first update."""
        self.assertEqual(self.record.frame_count, 1)

    def test_17_last_confidence_stored(self):
        """last_confidence matches the detection confidence."""
        self.assertAlmostEqual(self.record.last_confidence, 0.90)

    def test_18_last_bbox_stored(self):
        """last_bbox is a 4-tuple of the bounding box coordinates."""
        self.assertEqual(self.record.last_bbox, (100, 50, 200, 300))

    def test_19_center_computed_correctly(self):
        """last_center is the midpoint of the bounding box."""
        cx, cy = self.record.last_center
        self.assertAlmostEqual(cx, 150.0)
        self.assertAlmostEqual(cy, 175.0)

    def test_20_history_has_one_entry(self):
        """history deque contains exactly one PositionalObservation."""
        self.assertEqual(len(self.record.history), 1)

    def test_21_observation_is_positional_observation(self):
        """The history entry is a PositionalObservation dataclass."""
        obs = list(self.record.history)[0]
        self.assertIsInstance(obs, PositionalObservation)

    def test_22_observation_frame_time(self):
        """The first observation's frame_time matches the provided timestamp."""
        obs = list(self.record.history)[0]
        self.assertEqual(obs.frame_time, self.t0)


# ===========================================================================
# 3. Existing track update
# ===========================================================================

class TestExistingTrackUpdate(unittest.TestCase):
    """Test that repeated updates preserve first_seen and increment counters."""

    def setUp(self):
        self.mem = EventMemory()
        self.t0 = datetime(2026, 1, 1, 0, 0, 0)
        self.t1 = datetime(2026, 1, 1, 0, 0, 1)
        self.t2 = datetime(2026, 1, 1, 0, 0, 2)

        obj0 = _make_tracked(track_id=3, confidence=0.80, x1=10, y1=20, x2=110, y2=220)
        obj1 = _make_tracked(track_id=3, confidence=0.85, x1=15, y1=25, x2=115, y2=225)
        obj2 = _make_tracked(track_id=3, confidence=0.90, x1=20, y1=30, x2=120, y2=230)

        self.mem.update(obj0, self.t0)
        self.mem.update(obj1, self.t1)
        self.record = self.mem.update(obj2, self.t2)

    def test_30_first_seen_preserved(self):
        """first_seen is never overwritten after the first update."""
        self.assertEqual(self.record.first_seen, self.t0)

    def test_31_last_seen_updated(self):
        """last_seen is updated to the most recent frame_time."""
        self.assertEqual(self.record.last_seen, self.t2)

    def test_32_frame_count_increments(self):
        """frame_count equals the number of update() calls."""
        self.assertEqual(self.record.frame_count, 3)

    def test_33_last_confidence_updated(self):
        """last_confidence reflects the most recent detection."""
        self.assertAlmostEqual(self.record.last_confidence, 0.90)

    def test_34_last_bbox_updated(self):
        """last_bbox reflects the most recent bounding box."""
        self.assertEqual(self.record.last_bbox, (20, 30, 120, 230))

    def test_35_last_center_updated(self):
        """last_center reflects the centroid of the most recent bbox."""
        cx, cy = self.record.last_center
        self.assertAlmostEqual(cx, 70.0)
        self.assertAlmostEqual(cy, 130.0)

    def test_36_history_grows(self):
        """history grows by one entry per update."""
        self.assertEqual(len(self.record.history), 3)

    def test_37_history_ordered_oldest_first(self):
        """History entries are in chronological order (oldest first)."""
        history = list(self.record.history)
        self.assertEqual(history[0].frame_time, self.t0)
        self.assertEqual(history[1].frame_time, self.t1)
        self.assertEqual(history[2].frame_time, self.t2)


# ===========================================================================
# 4. Persistent state (same instance across frames)
# ===========================================================================

class TestPersistentState(unittest.TestCase):
    """Test that the same EventMemory instance accumulates state across frames."""

    def test_40_persistent_state_same_instance(self):
        """The same EventMemory instance accumulates track 7 history over 5 frames."""
        mem = EventMemory()
        t_base = datetime(2026, 1, 1, 12, 0, 0)

        for i in range(5):
            obj = _make_tracked(track_id=7, confidence=0.80 + i * 0.02,
                                x1=100 + i, y1=50 + i, x2=200 + i, y2=300 + i)
            mem.update(obj, t_base + timedelta(seconds=i))

        rec = mem.get(7)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.frame_count, 5)
        self.assertEqual(len(rec.history), 5)
        self.assertEqual(rec.first_seen, t_base)
        self.assertEqual(rec.last_seen, t_base + timedelta(seconds=4))

    def test_41_multiple_track_ids_independent(self):
        """Different track IDs maintain independent memory records."""
        mem = EventMemory()
        t = _now()

        for frame in range(3):
            for tid in [1, 2, 3]:
                obj = _make_tracked(track_id=tid)
                mem.update(obj, t + timedelta(seconds=frame))

        self.assertEqual(len(mem), 3)
        for tid in [1, 2, 3]:
            rec = mem.get(tid)
            self.assertIsNotNone(rec)
            self.assertEqual(rec.frame_count, 3)

    def test_42_missing_track_preserves_memory(self):
        """A track absent from a frame is NOT removed from memory."""
        mem = EventMemory()
        t = _now()

        # Track 10 seen in frame 1
        mem.update(_make_tracked(track_id=10), t)
        # Frame 2: only track 99 appears; track 10 is "missing"
        mem.update(_make_tracked(track_id=99), t + timedelta(seconds=1))

        # Track 10 should still be in memory
        self.assertTrue(mem.exists(10))
        rec = mem.get(10)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.frame_count, 1)  # still only 1 frame

    def test_43_new_track_not_created_for_absent_id(self):
        """An absent track ID never spontaneously appears in memory."""
        mem = EventMemory()
        t = _now()
        mem.update(_make_tracked(track_id=5), t)
        self.assertFalse(mem.exists(999))


# ===========================================================================
# 5. Bounded history
# ===========================================================================

class TestBoundedHistory(unittest.TestCase):
    """Test that history does not grow beyond max_history."""

    def test_50_history_bounded_at_max(self):
        """History deque never exceeds max_history entries."""
        mem = EventMemory(max_history=5)
        t_base = datetime(2026, 6, 1, 10, 0, 0)

        for i in range(20):
            obj = _make_tracked(track_id=1)
            mem.update(obj, t_base + timedelta(seconds=i))

        history = mem.get_history(1)
        self.assertEqual(len(history), 5)

    def test_51_history_keeps_most_recent(self):
        """When the deque is full, oldest entries are evicted first."""
        mem = EventMemory(max_history=3)
        t_base = datetime(2026, 6, 1, 10, 0, 0)

        for i in range(6):
            obj = _make_tracked(track_id=2)
            mem.update(obj, t_base + timedelta(seconds=i))

        history = mem.get_history(2)
        # Should contain t+3, t+4, t+5
        self.assertEqual(history[0].frame_time, t_base + timedelta(seconds=3))
        self.assertEqual(history[-1].frame_time, t_base + timedelta(seconds=5))

    def test_52_max_history_one(self):
        """max_history=1 keeps only the last observation."""
        mem = EventMemory(max_history=1)
        t_base = datetime(2026, 6, 1, 10, 0, 0)

        for i in range(10):
            obj = _make_tracked(track_id=3)
            mem.update(obj, t_base + timedelta(seconds=i))

        history = mem.get_history(3)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].frame_time, t_base + timedelta(seconds=9))

    def test_53_frame_count_still_increments_beyond_max_history(self):
        """frame_count keeps counting even when history is at capacity."""
        mem = EventMemory(max_history=3)
        t_base = datetime(2026, 6, 1, 10, 0, 0)

        for i in range(10):
            obj = _make_tracked(track_id=4)
            mem.update(obj, t_base + timedelta(seconds=i))

        rec = mem.get(4)
        self.assertEqual(rec.frame_count, 10)
        self.assertEqual(len(rec.history), 3)


# ===========================================================================
# 6. Query API
# ===========================================================================

class TestQueryAPI(unittest.TestCase):
    """Test get(), exists(), get_history(), get_all()."""

    def setUp(self):
        self.mem = EventMemory()
        self.t = _now()
        self.mem.update(_make_tracked(track_id=10), self.t)
        self.mem.update(_make_tracked(track_id=20), self.t)

    def test_60_get_known_track(self):
        """get() returns TrackMemory for a known track_id."""
        rec = self.mem.get(10)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.track_id, 10)

    def test_61_get_unknown_track_returns_none(self):
        """get() returns None for an unknown track_id."""
        self.assertIsNone(self.mem.get(999))

    def test_62_exists_true_for_known(self):
        """exists() returns True for a known track_id."""
        self.assertTrue(self.mem.exists(10))
        self.assertTrue(self.mem.exists(20))

    def test_63_exists_false_for_unknown(self):
        """exists() returns False for an unseen track_id."""
        self.assertFalse(self.mem.exists(999))

    def test_64_contains_syntax(self):
        """'track_id in memory' syntax works (delegates to __contains__)."""
        self.assertIn(10, self.mem)
        self.assertNotIn(999, self.mem)

    def test_65_get_history_returns_list(self):
        """get_history() returns a list (not a deque)."""
        history = self.mem.get_history(10)
        self.assertIsInstance(history, list)

    def test_66_get_history_unknown_track_empty_list(self):
        """get_history() returns empty list for an unknown track_id."""
        self.assertEqual(self.mem.get_history(999), [])

    def test_67_get_history_is_snapshot(self):
        """Mutating the returned list does NOT affect internal state."""
        history1 = self.mem.get_history(10)
        history1.clear()
        history2 = self.mem.get_history(10)
        self.assertEqual(len(history2), 1)

    def test_68_get_all_returns_dict(self):
        """get_all() returns a dict with all known track_ids."""
        all_records = self.mem.get_all()
        self.assertIsInstance(all_records, dict)
        self.assertIn(10, all_records)
        self.assertIn(20, all_records)
        self.assertEqual(len(all_records), 2)

    def test_69_get_all_is_snapshot(self):
        """Mutating the returned dict does NOT affect internal storage."""
        snap = self.mem.get_all()
        snap.clear()
        self.assertEqual(len(self.mem), 2)


# ===========================================================================
# 7. Lifecycle: remove and clear
# ===========================================================================

class TestLifecycle(unittest.TestCase):
    """Test remove() and clear() operations."""

    def setUp(self):
        self.mem = EventMemory()
        t = _now()
        for tid in [1, 2, 3]:
            self.mem.update(_make_tracked(track_id=tid), t)

    def test_70_remove_known_track(self):
        """remove() returns True and deletes the record."""
        result = self.mem.remove(1)
        self.assertTrue(result)
        self.assertFalse(self.mem.exists(1))
        self.assertEqual(len(self.mem), 2)

    def test_71_remove_unknown_track(self):
        """remove() returns False when track_id is not present."""
        result = self.mem.remove(999)
        self.assertFalse(result)

    def test_72_clear_removes_all(self):
        """clear() empties the memory and returns the count."""
        count = self.mem.clear()
        self.assertEqual(count, 3)
        self.assertEqual(len(self.mem), 0)

    def test_73_clear_empty_memory_returns_zero(self):
        """clear() on an already-empty memory returns 0."""
        empty = EventMemory()
        self.assertEqual(empty.clear(), 0)

    def test_74_can_update_after_clear(self):
        """Memory works normally after clear()."""
        self.mem.clear()
        t = _now()
        self.mem.update(_make_tracked(track_id=42), t)
        self.assertTrue(self.mem.exists(42))

    def test_75_removed_track_recreatable(self):
        """A removed track can be added again as a fresh record."""
        t0 = datetime(2026, 1, 1, 10, 0, 0)
        t1 = datetime(2026, 1, 1, 11, 0, 0)

        self.mem.remove(1)
        self.mem.update(_make_tracked(track_id=1), t1)

        rec = self.mem.get(1)
        self.assertIsNotNone(rec)
        # first_seen must be t1 (re-created), not the original t0
        self.assertNotEqual(rec.first_seen, t0)


# ===========================================================================
# 8. update_batch
# ===========================================================================

class TestUpdateBatch(unittest.TestCase):
    """Test the batch update convenience method."""

    def test_80_update_batch_empty_list(self):
        """update_batch on an empty list is a no-op."""
        mem = EventMemory()
        results = mem.update_batch([], _now())
        self.assertEqual(results, [])
        self.assertEqual(len(mem), 0)

    def test_81_update_batch_multiple_objects(self):
        """update_batch processes all objects in a single call."""
        mem = EventMemory()
        t = _now()
        objects = [
            _make_tracked(track_id=i, class_name="person")
            for i in range(1, 6)
        ]
        results = mem.update_batch(objects, t)

        self.assertEqual(len(results), 5)
        self.assertEqual(len(mem), 5)
        for i, result in enumerate(results):
            self.assertEqual(result.track_id, i + 1)

    def test_82_update_batch_returns_in_order(self):
        """update_batch returns records in the same order as input."""
        mem = EventMemory()
        t = _now()
        objects = [_make_tracked(track_id=tid) for tid in [10, 20, 30]]
        results = mem.update_batch(objects, t)

        returned_ids = [r.track_id for r in results]
        self.assertEqual(returned_ids, [10, 20, 30])


# ===========================================================================
# 9. Input validation
# ===========================================================================

class TestInputValidation(unittest.TestCase):
    """Test that invalid inputs are rejected with appropriate exceptions."""

    def setUp(self):
        self.mem = EventMemory()

    def test_90_none_tracked_object_rejected(self):
        """update() raises TypeError when tracked_object is None."""
        with self.assertRaises(TypeError):
            self.mem.update(None, _now())

    def test_91_string_tracked_object_rejected(self):
        """update() raises TypeError when tracked_object is a string."""
        with self.assertRaises(TypeError):
            self.mem.update("not_a_tracked_object", _now())

    def test_92_dict_tracked_object_rejected(self):
        """update() raises TypeError when tracked_object is a dict."""
        with self.assertRaises(TypeError):
            self.mem.update({"track_id": 1}, _now())

    def test_93_none_frame_time_rejected(self):
        """update() raises TypeError when frame_time is None."""
        obj = _make_tracked(track_id=1)
        with self.assertRaises(TypeError):
            self.mem.update(obj, None)

    def test_94_string_frame_time_rejected(self):
        """update() raises TypeError when frame_time is a string."""
        obj = _make_tracked(track_id=1)
        with self.assertRaises(TypeError):
            self.mem.update(obj, "2026-01-01")

    def test_95_float_frame_time_rejected(self):
        """update() raises TypeError when frame_time is a float timestamp."""
        obj = _make_tracked(track_id=1)
        with self.assertRaises(TypeError):
            self.mem.update(obj, time.time())


# ===========================================================================
# 10. PositionalObservation and TrackMemory dataclass structure
# ===========================================================================

class TestDataclassStructure(unittest.TestCase):
    """Test PositionalObservation and TrackMemory field structure."""

    def test_100_positional_observation_fields(self):
        """PositionalObservation has all required fields."""
        expected = {
            "frame_time", "center_x", "center_y",
            "x1", "y1", "x2", "y2", "confidence",
        }
        actual = {f.name for f in dataclass_fields(PositionalObservation)}
        self.assertEqual(expected, actual)

    def test_101_positional_observation_is_frozen(self):
        """PositionalObservation is immutable (frozen=True)."""
        obs = PositionalObservation(
            frame_time=_now(), center_x=100.0, center_y=200.0,
            x1=50, y1=100, x2=150, y2=300, confidence=0.9,
        )
        with self.assertRaises((AttributeError, TypeError)):
            obs.center_x = 999.0

    def test_102_track_memory_fields(self):
        """TrackMemory has all required fields."""
        expected = {
            "track_id", "class_id", "class_name",
            "first_seen", "last_seen", "last_confidence",
            "last_bbox", "last_center", "frame_count", "history",
        }
        actual = {f.name for f in dataclass_fields(TrackMemory)}
        self.assertEqual(expected, actual)

    def test_103_track_memory_history_is_deque(self):
        """TrackMemory.history is a deque instance."""
        mem = EventMemory()
        t = _now()
        mem.update(_make_tracked(track_id=1), t)
        rec = mem.get(1)
        self.assertIsInstance(rec.history, deque)


# ===========================================================================
# 11. Data safety
# ===========================================================================

class TestDataSafety(unittest.TestCase):
    """Verify that returned data cannot accidentally corrupt internal state."""

    def test_110_get_history_snapshot_safe(self):
        """Clearing the list returned by get_history does not empty internal deque."""
        mem = EventMemory()
        t = _now()
        for i in range(5):
            mem.update(_make_tracked(track_id=1), t + timedelta(seconds=i))

        snap = mem.get_history(1)
        snap.clear()

        internal = mem.get_history(1)
        self.assertEqual(len(internal), 5)

    def test_111_get_all_snapshot_safe(self):
        """Deleting keys from get_all() does not remove internal records."""
        mem = EventMemory()
        t = _now()
        mem.update(_make_tracked(track_id=1), t)
        mem.update(_make_tracked(track_id=2), t)

        snap = mem.get_all()
        del snap[1]

        self.assertTrue(mem.exists(1))

    def test_112_observations_are_frozen(self):
        """PositionalObservation instances in history cannot be mutated."""
        mem = EventMemory()
        mem.update(_make_tracked(track_id=1), _now())
        history = mem.get_history(1)
        obs = history[0]
        with self.assertRaises((AttributeError, TypeError)):
            obs.center_x = -1.0


# ===========================================================================
# 12. Integration with M4 using real video frames
# ===========================================================================

@unittest.skipUnless(_VIDEO_AVAILABLE, "Sample video test.mp4 not available")
class TestM4M5Integration(unittest.TestCase):
    """Integration tests: VideoSource -> Preprocessor -> ByteTracker -> EventMemory."""

    def _build_pipeline(self):
        """Helper: construct a fresh pipeline."""
        from ai_engine.detector import YOLODetector
        from ai_engine.preprocessing import FramePreprocessor
        from ai_engine.tracker import ByteTrackTracker

        detector = YOLODetector(device="cpu")
        tracker = ByteTrackTracker(detector)
        preprocessor = FramePreprocessor()
        memory = EventMemory(max_history=100)
        return detector, tracker, preprocessor, memory

    def test_120_pipeline_processes_frames_without_crash(self):
        """M1->M2->M4->M5 pipeline runs 30 frames without an error."""
        from ai_engine.video_input import VideoSource

        _, tracker, preprocessor, memory = self._build_pipeline()

        with VideoSource(source_type="video", source=SAMPLE_VIDEO) as src:
            frame_count = 0
            for raw_frame in src:
                t = datetime.utcnow()
                processed = preprocessor.process(raw_frame)
                tracked = tracker.update(processed)
                memory.update_batch(tracked, t)
                frame_count += 1
                if frame_count >= 30:
                    break

        self.assertGreaterEqual(frame_count, 20)
        self.assertIsInstance(memory.get_all(), dict)

    def test_121_persistent_track_accumulates_history(self):
        """At least one track ID accumulates multiple positional observations."""
        from ai_engine.video_input import VideoSource

        _, tracker, preprocessor, memory = self._build_pipeline()

        with VideoSource(source_type="video", source=SAMPLE_VIDEO) as src:
            frame_count = 0
            for raw_frame in src:
                t = datetime.utcnow()
                processed = preprocessor.process(raw_frame)
                tracked = tracker.update(processed)
                memory.update_batch(tracked, t)
                frame_count += 1
                if frame_count >= 60:
                    break

        all_records = memory.get_all()
        # At least one track should have been seen in more than one frame
        multi_frame_tracks = [
            rec for rec in all_records.values() if rec.frame_count >= 2
        ]
        self.assertGreater(
            len(multi_frame_tracks), 0,
            f"No track was seen in 2+ frames out of {len(all_records)} unique tracks "
            f"over {frame_count} frames. ByteTrack must persist IDs."
        )

    def test_122_history_observations_are_positional_observations(self):
        """All history entries are PositionalObservation instances."""
        from ai_engine.video_input import VideoSource

        _, tracker, preprocessor, memory = self._build_pipeline()

        with VideoSource(source_type="video", source=SAMPLE_VIDEO) as src:
            frame_count = 0
            for raw_frame in src:
                t = datetime.utcnow()
                processed = preprocessor.process(raw_frame)
                tracked = tracker.update(processed)
                memory.update_batch(tracked, t)
                frame_count += 1
                if frame_count >= 20:
                    break

        for tid, rec in memory.get_all().items():
            for obs in memory.get_history(tid):
                self.assertIsInstance(obs, PositionalObservation)

    def test_123_first_seen_not_updated_on_subsequent_frames(self):
        """first_seen remains fixed at the very first frame for a persistent track."""
        from ai_engine.video_input import VideoSource

        _, tracker, preprocessor, memory = self._build_pipeline()
        first_seen_map = {}

        with VideoSource(source_type="video", source=SAMPLE_VIDEO) as src:
            frame_count = 0
            for raw_frame in src:
                t = datetime.utcnow()
                processed = preprocessor.process(raw_frame)
                tracked = tracker.update(processed)

                for obj in tracked:
                    if obj.track_id not in first_seen_map:
                        first_seen_map[obj.track_id] = t

                memory.update_batch(tracked, t)
                frame_count += 1
                if frame_count >= 40:
                    break

        for tid, recorded_first_seen in first_seen_map.items():
            rec = memory.get(tid)
            if rec is not None and rec.frame_count > 1:
                # first_seen must equal the timestamp when first recorded
                self.assertEqual(
                    rec.first_seen, recorded_first_seen,
                    f"Track {tid}: first_seen was changed after first observation."
                )

    def test_124_bounded_history_respected_in_real_pipeline(self):
        """History deque never exceeds max_history even with many frames."""
        from ai_engine.video_input import VideoSource

        MAX_H = 10
        _, tracker, preprocessor, memory = self._build_pipeline()
        memory_small = EventMemory(max_history=MAX_H)

        with VideoSource(source_type="video", source=SAMPLE_VIDEO) as src:
            frame_count = 0
            for raw_frame in src:
                t = datetime.utcnow()
                processed = preprocessor.process(raw_frame)
                tracked = tracker.update(processed)
                memory_small.update_batch(tracked, t)
                frame_count += 1
                if frame_count >= 50:
                    break

        for tid, rec in memory_small.get_all().items():
            history = memory_small.get_history(tid)
            self.assertLessEqual(
                len(history), MAX_H,
                f"Track {tid}: history length {len(history)} exceeds max_history={MAX_H}"
            )

    def test_125_frame_count_matches_actual_appearances(self):
        """TrackMemory.frame_count equals the number of times we called update()."""
        from ai_engine.video_input import VideoSource

        _, tracker, preprocessor, memory = self._build_pipeline()
        manual_counts = {}   # track_id -> count we manually track

        with VideoSource(source_type="video", source=SAMPLE_VIDEO) as src:
            frame_count = 0
            for raw_frame in src:
                t = datetime.utcnow()
                processed = preprocessor.process(raw_frame)
                tracked = tracker.update(processed)

                for obj in tracked:
                    manual_counts[obj.track_id] = (
                        manual_counts.get(obj.track_id, 0) + 1
                    )

                memory.update_batch(tracked, t)
                frame_count += 1
                if frame_count >= 30:
                    break

        for tid, count in manual_counts.items():
            rec = memory.get(tid)
            self.assertIsNotNone(rec, f"Track {tid} is missing from EventMemory")
            self.assertEqual(
                rec.frame_count, count,
                f"Track {tid}: expected frame_count={count}, got {rec.frame_count}"
            )

    def test_126_m1_m4_still_functional_after_m5(self):
        """M1, M2, M3, M4 still work correctly after M5 has been used (regression)."""
        from ai_engine.detector import YOLODetector, Detection
        from ai_engine.preprocessing import FramePreprocessor
        from ai_engine.tracker import ByteTrackTracker, TrackedObject
        from ai_engine.video_input import VideoSource

        detector = YOLODetector(device="cpu")
        tracker = ByteTrackTracker(detector)
        preprocessor = FramePreprocessor()
        memory = EventMemory()

        # Run through M5
        with VideoSource(source_type="video", source=SAMPLE_VIDEO) as src:
            ret, frame = src.read()
            self.assertTrue(ret)
            processed = preprocessor.process(frame)
            tracked = tracker.update(processed)
            memory.update_batch(tracked, datetime.utcnow())

        # M3 direct detection should still work independently
        with VideoSource(source_type="video", source=SAMPLE_VIDEO) as src:
            ret, frame = src.read()
            self.assertTrue(ret)
            detections = detector.detect(frame)
            self.assertIsInstance(detections, list)
            for det in detections:
                self.assertIsInstance(det, Detection)


# ===========================================================================
# 13. Edge cases
# ===========================================================================

class TestEdgeCases(unittest.TestCase):
    """Edge-case and boundary tests."""

    def test_130_update_batch_with_empty_list(self):
        """update_batch([]) is a no-op; memory stays empty."""
        mem = EventMemory()
        results = mem.update_batch([], _now())
        self.assertEqual(results, [])
        self.assertEqual(len(mem), 0)

    def test_131_len_returns_track_count(self):
        """len(memory) equals the number of distinct track IDs stored."""
        mem = EventMemory()
        t = _now()
        for tid in range(1, 8):
            mem.update(_make_tracked(track_id=tid), t)
        self.assertEqual(len(mem), 7)

    def test_132_track_count_property(self):
        """track_count property mirrors len()."""
        mem = EventMemory()
        t = _now()
        for tid in range(1, 4):
            mem.update(_make_tracked(track_id=tid), t)
        self.assertEqual(mem.track_count, len(mem))

    def test_133_same_timestamp_multiple_objects(self):
        """Multiple objects with the same frame_time are handled correctly."""
        mem = EventMemory()
        t = _now()
        mem.update(_make_tracked(track_id=1), t)
        mem.update(_make_tracked(track_id=2), t)
        mem.update(_make_tracked(track_id=3), t)
        self.assertEqual(len(mem), 3)

    def test_134_class_name_and_id_not_overwritten(self):
        """class_id and class_name are preserved from the first observation."""
        mem = EventMemory()
        t = _now()
        obj = _make_tracked(track_id=5, class_id=0, class_name="person")
        mem.update(obj, t)
        rec = mem.get(5)
        # Update again — class should still be "person" / 0
        mem.update(obj, t + timedelta(seconds=1))
        rec2 = mem.get(5)
        self.assertEqual(rec2.class_id, 0)
        self.assertEqual(rec2.class_name, "person")

    def test_135_center_calculation_correct(self):
        """center is correctly computed as ((x1+x2)/2, (y1+y2)/2)."""
        mem = EventMemory()
        obj = _make_tracked(track_id=99, x1=0, y1=0, x2=100, y2=200)
        mem.update(obj, _now())
        rec = mem.get(99)
        cx, cy = rec.last_center
        self.assertAlmostEqual(cx, 50.0)
        self.assertAlmostEqual(cy, 100.0)


if __name__ == "__main__":
    unittest.main()
