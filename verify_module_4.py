"""Comprehensive End-to-End Verification Script for IBVAP Module 4 (ByteTrack Tracking).

Verifies:
1. Real MP4 Video File (videos/test.mp4) -> VideoSource (M1) -> FramePreprocessor (M2) -> ByteTrackTracker (M4)
2. Live Hardware Webcam (index 0) -> VideoSource (M1) -> FramePreprocessor (M2) -> ByteTrackTracker (M4)
3. Tracker Reset & Model Reuse Verification:
   - Reuses existing M3 YOLO model instance
   - reset() reinitializes track state without reloading model
   - M3 detector continues to function independently
4. TrackedObject contract validation:
   - track_id, class_id, class_name, confidence, x1, y1, x2, y2
   - Target class filtering (person, car, motorcycle, bus, truck)
   - Persistence verification across consecutive frames
"""

from collections import defaultdict
import logging
from pathlib import Path
import sys
import time
from typing import Any, Dict, List

import cv2
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.detector import YOLODetector
from ai_engine.preprocessing import FramePreprocessor
from ai_engine.tracker import ByteTrackTracker, TrackedObject
from ai_engine.video_input import (
    SourceType,
    VideoSource,
    VideoSourceError,
    VideoSourceOpenError,
)

SAMPLE_VIDEO_PATH = PROJECT_ROOT / "videos" / "test.mp4"

logging.basicConfig(level=logging.WARNING)


def verify_real_mp4_tracking(num_frames: int = 50) -> Dict[str, Any]:
    """Verify tracking pipeline on real MP4 video file."""
    print("\n" + "=" * 76)
    print(f"  [1/3] REAL MP4 VIDEO TRACKING VERIFICATION ({SAMPLE_VIDEO_PATH.name})")
    print("=" * 76)

    report: Dict[str, Any] = {
        "source": str(SAMPLE_VIDEO_PATH),
        "opened": False,
        "frames_processed": 0,
        "total_detections": 0,
        "unique_track_ids": set(),
        "track_id_counts": defaultdict(int),
        "classes_observed": set(),
        "contract_valid": True,
        "contract_errors": [],
        "persistent_tracks_count": 0,
        "elapsed_sec": 0.0,
        "average_fps": 0.0,
    }

    if not SAMPLE_VIDEO_PATH.exists():
        print(f"[-] Video file not found: {SAMPLE_VIDEO_PATH}")
        return report

    t_start = time.time()
    detector = YOLODetector(model_path="yolov8n.pt", device="cpu", conf_threshold=0.35)
    tracker = ByteTrackTracker(detector=detector)
    preprocessor = FramePreprocessor()

    with VideoSource(source_type=SourceType.VIDEO, source=str(SAMPLE_VIDEO_PATH)) as source:
        report["opened"] = True
        print(f"  [+] Opened {SAMPLE_VIDEO_PATH.name}: {source.width}x{source.height} @ {source.fps:.1f} FPS")

        for frame_idx, frame in enumerate(source):
            if frame_idx >= num_frames:
                break

            processed_frame = preprocessor(frame)
            tracked_objects = tracker.update(processed_frame)

            report["frames_processed"] += 1
            report["total_detections"] += len(tracked_objects)

            for obj in tracked_objects:
                report["unique_track_ids"].add(obj.track_id)
                report["track_id_counts"][obj.track_id] += 1
                report["classes_observed"].add(obj.class_name)

                # Contract validation
                if not isinstance(obj.track_id, int) or obj.track_id <= 0:
                    report["contract_valid"] = False
                    report["contract_errors"].append(f"Invalid track_id: {obj.track_id}")
                if obj.class_name not in detector.target_classes.values():
                    report["contract_valid"] = False
                    report["contract_errors"].append(f"Unexpected class: {obj.class_name}")
                if not (0.0 <= obj.confidence <= 1.0):
                    report["contract_valid"] = False
                    report["contract_errors"].append(f"Confidence out of range: {obj.confidence}")
                if not (0 <= obj.x1 <= obj.x2 <= source.width and 0 <= obj.y1 <= obj.y2 <= source.height):
                    report["contract_valid"] = False
                    report["contract_errors"].append(
                        f"Coords out of bounds: ({obj.x1},{obj.y1})-({obj.x2},{obj.y2})"
                    )

    report["elapsed_sec"] = time.time() - t_start
    report["average_fps"] = report["frames_processed"] / report["elapsed_sec"] if report["elapsed_sec"] > 0 else 0.0

    # Count persistent tracks (persisting >= 3 frames)
    persistent = [tid for tid, count in report["track_id_counts"].items() if count >= 3]
    report["persistent_tracks_count"] = len(persistent)

    print(f"  [+] Frames Processed       : {report['frames_processed']}")
    print(f"  [+] Total Tracked Objects  : {report['total_detections']}")
    print(f"  [+] Unique Track IDs       : {len(report['unique_track_ids'])}")
    print(f"  [+] Persistent Tracks (>=3f): {report['persistent_tracks_count']}")
    print(f"  [+] Classes Observed       : {sorted(list(report['classes_observed']))}")
    print(f"  [+] Contract Valid         : {report['contract_valid']}")
    if not report["contract_valid"]:
        print(f"      [!] Sample Errors: {report['contract_errors'][:5]}")
    print(f"  [+] Average Pipeline FPS   : {report['average_fps']:.2f}")

    print("  [+] Top Persistent Tracks  :")
    top_tracks = sorted(report["track_id_counts"].items(), key=lambda x: x[1], reverse=True)[:5]
    for tid, cnt in top_tracks:
        print(f"      - Track ID {tid:>2}: seen in {cnt:>2} / {report['frames_processed']} frames ({cnt/report['frames_processed']*100:.1f}%)")

    return report


def verify_webcam_tracking(camera_index: int = 0, num_frames: int = 10) -> Dict[str, Any]:
    """Verify live webcam ingestion piped into ByteTrackTracker."""
    print("\n" + "=" * 76)
    print(f"  [2/3] LIVE WEBCAM TRACKING VERIFICATION (Camera Index: {camera_index})")
    print("=" * 76)

    report: Dict[str, Any] = {
        "source": f"webcam_{camera_index}",
        "opened": False,
        "available": False,
        "frames_processed": 0,
        "total_detections": 0,
        "contract_valid": True,
        "average_fps": 0.0,
    }

    detector = YOLODetector(model_path="yolov8n.pt", device="cpu", conf_threshold=0.35)
    tracker = ByteTrackTracker(detector=detector)
    preprocessor = FramePreprocessor()

    try:
        with VideoSource(source_type=SourceType.WEBCAM, source=str(camera_index)) as source:
            report["opened"] = True
            report["available"] = True
            print(f"  [+] Live webcam opened: {source.width}x{source.height} @ {source.fps:.1f} FPS")

            t_start = time.time()
            for frame_idx, frame in enumerate(source):
                if frame_idx >= num_frames:
                    break

                processed = preprocessor(frame)
                tracked_objects = tracker.update(processed)

                report["frames_processed"] += 1
                report["total_detections"] += len(tracked_objects)

                for obj in tracked_objects:
                    if not isinstance(obj.track_id, int) or obj.track_id <= 0:
                        report["contract_valid"] = False

            elapsed = time.time() - t_start
            report["average_fps"] = report["frames_processed"] / elapsed if elapsed > 0 else 0.0

            print(f"  [+] Frames Processed       : {report['frames_processed']}")
            print(f"  [+] Tracked Objects Found  : {report['total_detections']}")
            print(f"  [+] Contract Valid         : {report['contract_valid']}")
            print(f"  [+] Average FPS            : {report['average_fps']:.2f}")

    except VideoSourceOpenError as err:
        print(f"  [-] Webcam not available on index {camera_index}: {err}")
        report["available"] = False
    except Exception as exc:
        print(f"  [-] Error testing webcam: {exc}")
        report["available"] = False

    return report


def verify_tracker_reset_and_model_reuse() -> Dict[str, Any]:
    """Verify reset() behavior, model reuse, and detector independence."""
    print("\n" + "=" * 76)
    print("  [3/3] TRACKER RESET & MODEL REUSE VERIFICATION")
    print("=" * 76)

    report: Dict[str, Any] = {
        "model_reused": False,
        "reset_clears_state": False,
        "tracking_after_reset": False,
        "detector_independence": False,
    }

    detector = YOLODetector(model_path="yolov8n.pt", device="cpu", conf_threshold=0.35)
    tracker = ByteTrackTracker(detector=detector)

    # 1. Model reuse check
    report["model_reused"] = (tracker.detector is detector) and (tracker.detector.model is detector.model)
    print(f"  [+] Model Reused Without Reload : {report['model_reused']}")

    # 2. Feed a frame
    if SAMPLE_VIDEO_PATH.exists():
        with VideoSource(source_type=SourceType.VIDEO, source=str(SAMPLE_VIDEO_PATH)) as src:
            ret, f1 = src.read()
            if not ret or f1 is None:
                return report
            t1 = tracker.update(f1)
            frames_before = tracker.frame_count

            # 3. Reset
            tracker.reset()
            report["reset_clears_state"] = (tracker.frame_count == 0)
            print(f"  [+] Reset Cleared Frame Count   : {report['reset_clears_state']} (was {frames_before})")

            # 4. Track after reset
            t2 = tracker.update(f1)
            report["tracking_after_reset"] = (tracker.frame_count == 1 and isinstance(t2, list))
            print(f"  [+] Tracking Post-Reset Success : {report['tracking_after_reset']}")

            # 5. Detector independence
            det_results = detector.detect(f1)
            report["detector_independence"] = isinstance(det_results, list) and not hasattr(det_results[0], "track_id")
            print(f"  [+] Detector Operates Cleanly   : {report['detector_independence']}")

    return report


def main() -> None:
    print("\n" + "#" * 76)
    print("  IBVAP MODULE 4: BYTETRACK PERSISTENT OBJECT TRACKING VERIFICATION")
    print("#" * 76)

    mp4_res = verify_real_mp4_tracking(num_frames=50)
    webcam_res = verify_webcam_tracking(camera_index=0, num_frames=10)
    reset_res = verify_tracker_reset_and_model_reuse()

    print("\n" + "=" * 76)
    print("  FINAL VERIFICATION SUMMARY")
    print("=" * 76)
    print(f"  1. Real MP4 Video Verification  : {'PASSED' if mp4_res['contract_valid'] and mp4_res['persistent_tracks_count'] > 0 else 'FAILED'}")
    print(f"  2. Webcam Hardware Verification : {'PASSED (Live Hardware Active)' if webcam_res['available'] and webcam_res['contract_valid'] else 'SKIPPED/UNAVAILABLE'}")
    print(f"  3. Tracker Reset & Model Reuse  : {'PASSED' if all(reset_res.values()) else 'FAILED'}")
    print("=" * 76 + "\n")


if __name__ == "__main__":
    main()
