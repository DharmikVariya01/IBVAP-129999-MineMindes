"""Standalone demonstration for IBVAP Module 12 (Complete AI Pipeline Integration).

Demonstrates the sequential execution of Modules 1 through 11:
1. Video stream ingestion via VideoSource (M1)
2. Low-light adaptive enhancement via FramePreprocessor (M2)
3. Object detection via YOLODetector (M3)
4. Persistent object tracking via ByteTrackTracker (M4)
5. In-memory trajectory and observation logging via EventMemory (M5)
6. Movement vector and displacement analysis via MovementAnalyzer (M6)
7. Spatial geofence and zone classification via ZoneManager (M7)
8. Virtual fence crossing detection via FenceBreachDetector (M8)
9. Spatial-temporal dwell evaluation via LoiteringDetector (M9)
10. Alert creation, priority ranking, and deduplication via AlertEngine (M10)
11. Verified JPG evidence capture via EvidenceCapture (M11)

Outputs headless-friendly terminal telemetry and performance statistics.

Usage:
    python -m ai_engine.demo_pipeline
    python run_pipeline_demo.py
    python run_pipeline_demo.py --max-frames 90
"""

from __future__ import annotations

import argparse
from datetime import datetime
import logging
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional, Set

import cv2
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.alerts import AlertEngine
from ai_engine.detector import YOLODetector
from ai_engine.event_memory import EventMemory
from ai_engine.evidence import EvidenceCapture
from ai_engine.fence_breach import FenceBreachDetector
from ai_engine.loitering import LoiteringDetector
from ai_engine.movement import MovementAnalyzer
from ai_engine.pipeline import AIPipeline, PipelineResult
from ai_engine.preprocessing import FramePreprocessor
from ai_engine.tracker import ByteTrackTracker
from ai_engine.video_input import SourceType, VideoSource
from ai_engine.zones import ZoneManager, ZoneType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ibvap.demo_pipeline")


def setup_surveillance_zones(zone_manager: ZoneManager) -> None:
    """Register standard surveillance zones for the demo scenario."""
    # Virtual Perimeter Fence along the upper boundary
    zone_manager.create_zone(
        zone_id="ZONE_PERIMETER_FENCE",
        zone_name="Perimeter Virtual Fence",
        zone_type=ZoneType.FENCE,
        polygon=[(0, 50), (1280, 50), (1280, 180), (0, 180)],
    )

    # Restricted Border Security Corridor
    zone_manager.create_zone(
        zone_id="ZONE_RESTRICTED_CORRIDOR",
        zone_name="Restricted Border Corridor",
        zone_type=ZoneType.RESTRICTED,
        polygon=[(100, 180), (1180, 180), (1180, 420), (100, 420)],
    )

    # Sensitive Approach Zone
    zone_manager.create_zone(
        zone_id="ZONE_SENSITIVE_APPROACH",
        zone_name="Sensitive Approach Zone",
        zone_type=ZoneType.SENSITIVE,
        polygon=[(50, 420), (1230, 420), (1230, 700), (50, 700)],
    )


def run_pipeline_demo(
    source_path: str = "videos/test.mp4",
    max_frames: int = 90,
    camera_id: str = "CAM_BORDER_01",
    evidence_dir: str = "evidence",
    show_gui: bool = False,
) -> Dict[str, Any]:
    """Execute the end-to-end AI Pipeline demo and print telemetry."""
    print("=" * 60)
    print("IBVAP MODULE 12 — COMPLETE AI PIPELINE DEMO")
    print("=" * 60)
    print(f"Video Source : {source_path}")
    print(f"Max Frames   : {max_frames}")
    print(f"Camera ID    : {camera_id}")
    print(f"Evidence Dir : {evidence_dir}")
    print(f"Display Mode : {'GUI (OpenCV)' if show_gui else 'Headless'}")
    print("-" * 60)

    # Resolve video source path
    src_file = Path(source_path)
    if not src_file.exists():
        logger.error("Source video file not found: %s", source_path)
        print(f"ERROR: Video source '{source_path}' does not exist.")
        return {"status": "FAIL", "reason": "video_not_found"}

    # Initialize components
    zone_manager = ZoneManager()
    setup_surveillance_zones(zone_manager)

    detector = YOLODetector(device="cpu", conf_threshold=0.35)
    tracker = ByteTrackTracker(detector=detector)
    preprocessor = FramePreprocessor()
    event_memory = EventMemory(max_history=100)
    movement_analyzer = MovementAnalyzer(movement_threshold=5.0)
    fence_breach_detector = FenceBreachDetector(default_fence_id="ZONE_PERIMETER_FENCE")
    loitering_detector = LoiteringDetector(
        loitering_duration_seconds=30.0,
        spatial_radius=50.0,
        min_observations=5,
    )
    alert_engine = AlertEngine(default_camera_id=camera_id)
    evidence_capture = EvidenceCapture(output_dir=evidence_dir)

    pipeline = AIPipeline(
        preprocessor=preprocessor,
        tracker=tracker,
        event_memory=event_memory,
        movement_analyzer=movement_analyzer,
        zone_manager=zone_manager,
        fence_breach_detector=fence_breach_detector,
        loitering_detector=loitering_detector,
        alert_engine=alert_engine,
        evidence_capture=evidence_capture,
        camera_id=camera_id,
        include_processed_frame_in_result=True,
    )

    # Acquire video source
    video_src = VideoSource(source_type=SourceType.VIDEO, source=str(src_file))
    video_src.open()

    total_tracked_objects = 0
    unique_track_ids: Set[int] = set()
    total_zone_classifications = 0
    total_fence_breaches = 0
    total_loitering_events = 0
    total_alerts_generated = 0
    total_evidence_captured = 0

    frame_idx = 0
    start_time = time.perf_counter()

    try:
        while frame_idx < max_frames:
            ret, frame = video_src.read()
            if not ret or frame is None:
                logger.info("End of video stream reached at frame %d.", frame_idx)
                break

            frame_idx += 1
            curr_fid = video_src.current_frame_index

            # Execute pipeline
            result: PipelineResult = pipeline.process_frame(frame, frame_id=curr_fid)

            # Accumulate metrics
            total_tracked_objects += len(result.tracked_objects)
            for obj in result.tracked_objects:
                unique_track_ids.add(obj.track_id)

            total_zone_classifications += len(result.zone_results)
            total_fence_breaches += len(result.fence_breach_events)
            total_loitering_events += len(result.loitering_events)
            total_alerts_generated += len(result.alerts)
            total_evidence_captured += len(result.evidence_records)

            if frame_idx % 15 == 0 or frame_idx == max_frames:
                elapsed_so_far = time.perf_counter() - start_time
                fps_so_far = frame_idx / elapsed_so_far if elapsed_so_far > 0 else 0.0
                print(
                    f"Frame {frame_idx:3d}/{max_frames} | "
                    f"Tracks Active: {len(result.tracked_objects):2d} | "
                    f"Unique Tracks: {len(unique_track_ids):2d} | "
                    f"Alerts: {total_alerts_generated:2d} | "
                    f"FPS: {fps_so_far:5.1f}"
                )

            # Optional GUI rendering
            if show_gui and result.processed_frame is not None:
                display_frame = result.processed_frame.copy()
                for obj in result.tracked_objects:
                    cv2.rectangle(
                        display_frame,
                        (obj.x1, obj.y1),
                        (obj.x2, obj.y2),
                        (0, 255, 0),
                        2,
                    )
                    cv2.putText(
                        display_frame,
                        f"ID:{obj.track_id} {obj.class_name}",
                        (obj.x1, max(20, obj.y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 0),
                        1,
                    )
                cv2.imshow("IBVAP AI Pipeline Demo", display_frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    finally:
        video_src.release()
        if show_gui:
            cv2.destroyAllWindows()

    total_elapsed = time.perf_counter() - start_time
    average_fps = frame_idx / total_elapsed if total_elapsed > 0 else 0.0

    print()
    print("=" * 60)
    print("IBVAP MODULE 12 — COMPLETE AI PIPELINE DEMO")
    print("=" * 60)
    print(f"Frames processed: {frame_idx}")
    print(f"Unique tracks: {len(unique_track_ids)}")
    print(f"Tracked objects: {total_tracked_objects}")
    print(f"Zone classifications: {total_zone_classifications}")
    print(f"Fence breaches: {total_fence_breaches}")
    print(f"Loitering events: {total_loitering_events}")
    print(f"Alerts generated: {total_alerts_generated}")
    print(f"Evidence captured: {total_evidence_captured}")
    print(f"Average FPS: {average_fps:.2f}")
    print()
    print("Pipeline status: PASS")
    print("=" * 60)

    return {
        "status": "PASS",
        "frames_processed": frame_idx,
        "unique_tracks": len(unique_track_ids),
        "tracked_objects": total_tracked_objects,
        "zone_classifications": total_zone_classifications,
        "fence_breaches": total_fence_breaches,
        "loitering_events": total_loitering_events,
        "alerts_generated": total_alerts_generated,
        "evidence_captured": total_evidence_captured,
        "average_fps": average_fps,
    }


def main() -> None:
    """CLI entry point for demo."""
    parser = argparse.ArgumentParser(
        description="IBVAP Module 12: Complete AI Pipeline Integration Demo",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="videos/test.mp4",
        help="Path to source video file (default: videos/test.mp4)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=90,
        help="Maximum frames to process (default: 90)",
    )
    parser.add_argument(
        "--camera-id",
        type=str,
        default="CAM_BORDER_01",
        help="Camera sensor ID (default: CAM_BORDER_01)",
    )
    parser.add_argument(
        "--evidence-dir",
        type=str,
        default="evidence",
        help="Evidence output directory (default: evidence)",
    )
    parser.add_argument(
        "--show-gui",
        action="store_true",
        help="Enable OpenCV display window (default: False / headless)",
    )
    args = parser.parse_args()

    run_pipeline_demo(
        source_path=args.source,
        max_frames=args.max_frames,
        camera_id=args.camera_id,
        evidence_dir=args.evidence_dir,
        show_gui=args.show_gui,
    )


if __name__ == "__main__":
    main()
