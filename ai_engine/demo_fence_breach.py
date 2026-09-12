"""Standalone demonstration for IBVAP Module 8 (Fence Breach Detection).

Runs the full end-to-end video analytics pipeline:
    M1 VideoSource
    -> M2 Preprocessor
    -> M3 YOLO Detector
    -> M4 ByteTrack Tracker
    -> M5 Event Memory
    -> M6 Movement Analyzer
    -> M7 Zone Manager
    -> M8 Fence Breach Detector (this module)

Detects temporal transitions where tracked objects cross a virtual fence
from OUTSIDE to INSIDE.

Usage:
    python -m ai_engine.demo_fence_breach
    python -m ai_engine.demo_fence_breach --headless --max-frames 90
    python run_fence_breach_demo.py --headless --max-frames 120
    python run_fence_breach_demo.py --source video --input videos/test.mp4
"""

import argparse
from collections import defaultdict
from datetime import datetime
import logging
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.detector import YOLODetector
from ai_engine.event_memory import EventMemory
from ai_engine.fence_breach import (
    FenceBreachDetector,
    FenceBreachEvent,
    FenceState,
)
from ai_engine.movement import MovementAnalyzer
from ai_engine.preprocessing import FramePreprocessor
from ai_engine.tracker import ByteTrackTracker, TrackedObject
from ai_engine.video_input import VideoSource, VideoSourceError
from ai_engine.zones import (
    DEFAULT_ZONE_COLORS,
    Zone,
    ZoneManager,
    ZoneResult,
    ZoneType,
)

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("demo_fence_breach")


# ---------------------------------------------------------------------------
# Virtual Fence Setup
# ---------------------------------------------------------------------------

def create_demo_fence_manager(width: int = 1280, height: int = 720) -> ZoneManager:
    """Create a deterministic virtual fence polygon for breach detection.

    Places a virtual perimeter fence across a central sector of the camera view
    so that objects moving through the frame can be evaluated for crossing events.
    """
    zm = ZoneManager(include_boundary=True)

    sx = width / 1280.0
    sy = height / 720.0

    def pt(x: float, y: float) -> Tuple[int, int]:
        return int(round(x * sx)), int(round(y * sy))

    # Virtual Fence: Encloses a strategic tactical sector
    # Points form a closed polygon across coordinates (200, 150) to (1080, 650)
    zm.create_zone(
        zone_id="virtual_fence",
        zone_name="Perimeter Virtual Fence",
        zone_type=ZoneType.FENCE,
        polygon=[pt(200, 150), pt(1080, 150), pt(1080, 650), pt(200, 650)],
        color=(255, 255, 0),  # Cyan
    )

    # Optional Restricted Zone inside the fence
    zm.create_zone(
        zone_id="inner_restricted",
        zone_name="Inner Secure Zone",
        zone_type=ZoneType.RESTRICTED,
        polygon=[pt(400, 250), pt(880, 250), pt(880, 550), pt(400, 550)],
        color=(0, 0, 230),  # Red
    )

    return zm


# ---------------------------------------------------------------------------
# Visual Rendering Helpers
# ---------------------------------------------------------------------------

def draw_fence_overlay(frame: np.ndarray, zone_manager: ZoneManager, alpha: float = 0.20) -> None:
    """Render virtual fence and zones with semi-transparent fill and borders."""
    overlay = frame.copy()

    for zone in zone_manager.get_zones():
        pts = np.array(zone.polygon, dtype=np.int32).reshape((-1, 1, 2))
        color = zone.color or DEFAULT_ZONE_COLORS.get(zone.zone_type, (255, 255, 255))

        # Fill overlay
        cv2.fillPoly(overlay, [pts], color)

        # Draw contour line
        thickness = 3 if zone.zone_type == ZoneType.FENCE else 2
        cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=thickness, lineType=cv2.LINE_AA)

        # Draw label
        x_min = int(np.min(pts[:, 0, 0]))
        y_min = int(np.min(pts[:, 0, 1]))
        tag = f"{zone.zone_name} [{zone.zone_type.value}]"
        cv2.putText(
            frame,
            tag,
            (x_min + 6, max(y_min + 20, 24)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            tag,
            (x_min + 6, max(y_min + 20, 24)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            color,
            1,
            cv2.LINE_AA,
        )

    cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, frame)


def draw_tracked_object(
    frame: np.ndarray,
    tracked_obj: TrackedObject,
    zone_result: ZoneResult,
    fence_state: FenceState,
    breach_count: int,
    recent_breach: bool = False,
) -> None:
    """Render bounding box, centroid, fence state badge, and breach indicators."""
    x1, y1, x2, y2 = tracked_obj.x1, tracked_obj.y1, tracked_obj.x2, tracked_obj.y2
    cx, cy = zone_result.center

    # Color coding: Red flashing if recent breach, Cyan if inside fence, Gray if outside
    if recent_breach:
        box_color = (0, 0, 255)      # Flashing Red
        thickness = 3
    elif fence_state == FenceState.INSIDE:
        box_color = (255, 255, 0)    # Cyan
        thickness = 2
    else:
        box_color = (180, 180, 180)  # Gray
        thickness = 2

    # Draw Bounding Box
    cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, thickness, cv2.LINE_AA)

    # Draw Centroid
    cv2.circle(frame, (cx, cy), 4, (0, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(frame, (cx, cy), 6, (0, 0, 0), 1, cv2.LINE_AA)

    # Status Label
    state_str = fence_state.value
    breach_tag = f" | BREACH x{breach_count}" if breach_count > 0 else ""
    if recent_breach:
        label = f"ID:{tracked_obj.track_id} [**BREACH DETECTED**] {state_str}"
    else:
        label = f"ID:{tracked_obj.track_id} {tracked_obj.class_name} | {state_str}{breach_tag}"

    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
    badge_y1 = max(y1 - 18, 0)
    badge_y2 = badge_y1 + th + 6
    cv2.rectangle(frame, (x1, badge_y1), (x1 + tw + 8, badge_y2), (20, 20, 20), -1)
    cv2.rectangle(frame, (x1, badge_y1), (x1 + tw + 8, badge_y2), box_color, 1)

    text_color = (0, 0, 255) if recent_breach else box_color
    cv2.putText(
        frame,
        label,
        (x1 + 4, badge_y2 - 3),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        text_color,
        1,
        cv2.LINE_AA,
    )


def draw_hud(
    frame: np.ndarray,
    frame_idx: int,
    fps: float,
    active_tracks: int,
    inside_count: int,
    outside_count: int,
    total_breaches: int,
    recent_breach_msg: Optional[str] = None,
) -> None:
    """Draw heads-up telemetry and breach alert banner."""
    panel_h = 110
    panel_w = 400
    overlay = frame.copy()
    cv2.rectangle(overlay, (8, 8), (8 + panel_w, 8 + panel_h), (15, 15, 15), -1)
    cv2.addWeighted(overlay, 0.78, frame, 0.22, 0, frame)
    cv2.rectangle(frame, (8, 8), (8 + panel_w, 8 + panel_h), (80, 80, 80), 1)

    title = "IBVAP M8: Virtual Fence Breach Detection"
    cv2.putText(frame, title, (14, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 255), 1, cv2.LINE_AA)

    lines = [
        f"Frame: {frame_idx:4d} | FPS: {fps:4.1f} | Active Tracks: {active_tracks}",
        f"Fence Status : INSIDE={inside_count:2d} | OUTSIDE={outside_count:2d}",
        f"Total Fence Breaches (OUTSIDE -> INSIDE): {total_breaches}",
    ]

    for i, line in enumerate(lines):
        y = 46 + i * 18
        cv2.putText(frame, line, (14, y), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (220, 220, 220), 1, cv2.LINE_AA)

    # Alert banner if recent breach occurred
    if recent_breach_msg:
        cv2.putText(frame, recent_breach_msg, (14, 102), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 0, 255), 1, cv2.LINE_AA)


# ---------------------------------------------------------------------------
# Demo Runner
# ---------------------------------------------------------------------------

def run_demo(
    source_type: str,
    source_target: str,
    conf_threshold: float,
    imgsz: int,
    headless: bool = True,
    max_frames: Optional[int] = None,
    print_every: int = 30,
) -> dict:
    """Run the Module 8 demonstration pipeline.

    Returns:
        Summary dict containing execution statistics.
    """
    print("=" * 72)
    print("  IBVAP Module 8 - Fence Breach Detection Demonstration")
    print("=" * 72)
    print(f"  Source          : {source_type.upper()} -> {source_target}")
    print(f"  Confidence      : {conf_threshold}")
    print(f"  Inference Size  : {imgsz}")
    print(f"  Headless Mode   : {headless}")
    print(f"  Max Frames      : {max_frames or 'Unlimited'}")
    print("=" * 72)

    # Initialize components
    print("\n[*] Initializing analytics pipeline...")
    detector = YOLODetector(conf_threshold=conf_threshold, imgsz=imgsz)
    tracker = ByteTrackTracker(detector)
    preprocessor = FramePreprocessor()
    memory = EventMemory(max_history=50)
    movement = MovementAnalyzer()
    breach_detector = FenceBreachDetector(default_fence_id="virtual_fence")

    print("    M1 VideoSource       : ready")
    print("    M2 Preprocessor      : ready")
    print(f"    M3 YOLODetector      : {detector.device}")
    print(f"    M4 ByteTracker       : {tracker.tracker_type}")
    print("    M5 EventMemory       : ready")
    print("    M6 Movement          : ready")

    src_param = int(source_target) if source_type == "webcam" and source_target.isdigit() else source_target

    try:
        source = VideoSource(source_type=source_type, source=src_param)
        source.open()
    except VideoSourceError as err:
        print(f"[!] Failed to open video source: {err}")
        return {}

    w = source.width or 1280
    h = source.height or 720
    zone_manager = create_demo_fence_manager(width=w, height=h)
    print(f"    M7 ZoneManager       : ready ({len(zone_manager)} zones configured for {w}x{h})")
    print("    M8 FenceBreachDetect : ready (temporal OUTSIDE -> INSIDE detector)")
    print()

    frame_count = 0
    t_start = time.perf_counter()

    unique_tracks = set()
    all_breach_events: List[FenceBreachEvent] = []
    recent_breaches: Dict[int, int] = {}  # track_id -> frame_detected
    total_inside_frames = 0
    total_outside_frames = 0

    if not headless:
        cv2.namedWindow("IBVAP M8 Fence Breach System", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("IBVAP M8 Fence Breach System", 1280, 720)

    try:
        print("[*] Processing frames...\n")
        for raw_frame in source:
            frame_count += 1
            now = datetime.utcnow()
            timestamp_sec = time.perf_counter() - t_start

            # M2 Preprocessing
            processed = preprocessor.process(raw_frame)

            # M4 Tracking
            tracked_objects = tracker.update(processed)

            # M5 Event Memory & M6 Movement
            memory.update_batch(tracked_objects, now)
            movement.analyze_all(memory)

            # M7 Zone Classification
            zone_results = zone_manager.classify_objects(tracked_objects)

            # M8 Fence Breach Detection
            frame_breaches = breach_detector.update_batch(
                zone_results,
                frame_id=frame_count,
                timestamp=timestamp_sec,
            )

            # Cleanup stale tracks in M8
            active_ids = [obj.track_id for obj in tracked_objects]
            breach_detector.cleanup_stale_tracks(active_ids)

            # Process any breach events detected in this frame
            for breach_ev in frame_breaches:
                all_breach_events.append(breach_ev)
                recent_breaches[breach_ev.track_id] = frame_count
                print(
                    f"  [!] >>> FENCE BREACH DETECTED <<< Frame {frame_count:4d} | "
                    f"Track #{breach_ev.track_id} crossed OUTSIDE -> INSIDE | "
                    f"Center: {breach_ev.center} | Total breaches for track: {breach_ev.breach_count}"
                )

            # Cleanup recent breach alert indicators after 20 frames
            expired = [tid for tid, f in recent_breaches.items() if frame_count - f > 20]
            for tid in expired:
                del recent_breaches[tid]

            # Aggregates for current frame
            inside_in_frame = 0
            outside_in_frame = 0
            for zr in zone_results:
                unique_tracks.add(zr.track_id)
                if zr.fence_inside:
                    inside_in_frame += 1
                    total_inside_frames += 1
                else:
                    outside_in_frame += 1
                    total_outside_frames += 1

            # Logging
            if frame_count % print_every == 0 or frame_count == 1:
                elapsed = time.perf_counter() - t_start
                fps = frame_count / elapsed if elapsed > 0 else 0.0
                print(
                    f"  [Frame {frame_count:4d}] FPS: {fps:4.1f} | Active: {len(tracked_objects):2d} | "
                    f"INSIDE: {inside_in_frame:2d} | OUTSIDE: {outside_in_frame:2d} | "
                    f"Total Breaches: {breach_detector.total_breaches}"
                )

            # GUI Rendering
            if not headless:
                display = processed.copy()
                draw_fence_overlay(display, zone_manager)

                for obj, zr in zip(tracked_objects, zone_results):
                    f_state = breach_detector.get_fence_state(obj.track_id)
                    b_count = breach_detector.get_breach_count(obj.track_id)
                    is_recent = obj.track_id in recent_breaches
                    draw_tracked_object(display, obj, zr, f_state, b_count, recent_breach=is_recent)

                elapsed = time.perf_counter() - t_start
                fps = frame_count / elapsed if elapsed > 0 else 0.0
                alert_text = (
                    f"ALERT: Track #{list(recent_breaches.keys())[0]} BREACHED FENCE!"
                    if recent_breaches
                    else None
                )
                draw_hud(
                    display,
                    frame_count,
                    fps,
                    len(tracked_objects),
                    inside_in_frame,
                    outside_in_frame,
                    breach_detector.total_breaches,
                    recent_breach_msg=alert_text,
                )

                cv2.imshow("IBVAP M8 Fence Breach System", display)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    print("\n[!] User requested termination (ESC/q).")
                    break

            if max_frames is not None and frame_count >= max_frames:
                print(f"\n[*] Reached configured max_frames ({max_frames}).")
                break

    finally:
        source.release()
        if not headless:
            cv2.destroyAllWindows()

    total_time = time.perf_counter() - t_start
    avg_fps = frame_count / total_time if total_time > 0 else 0.0

    print("\n" + "=" * 72)
    print("  IBVAP Module 8 - Execution Summary")
    print("=" * 72)
    print(f"  Frames processed        : {frame_count}")
    print(f"  Total duration          : {total_time:.2f} s")
    print(f"  Average FPS             : {avg_fps:.1f}")
    print(f"  Unique tracks observed  : {len(unique_tracks)}")
    print(f"  Total breach events     : {len(all_breach_events)}")
    print(f"  Inside fence counts     : {total_inside_frames}")
    print(f"  Outside fence counts    : {total_outside_frames}")
    if all_breach_events:
        print("\n  Breach Events Log:")
        for ev in all_breach_events:
            print(
                f"    - Frame {ev.frame_id}: Track #{ev.track_id} "
                f"transitioned {ev.previous_state.value} -> {ev.current_state.value} "
                f"at center {ev.center} (breach count={ev.breach_count})"
            )
    else:
        print("\n  Crossing Status:")
        print("    No OUTSIDE -> INSIDE crossing observed in the selected test segment.")
    print("=" * 72)

    return {
        "frames": frame_count,
        "duration_sec": total_time,
        "avg_fps": avg_fps,
        "unique_tracks": len(unique_tracks),
        "breach_events_count": len(all_breach_events),
        "total_inside_frames": total_inside_frames,
        "total_outside_frames": total_outside_frames,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="IBVAP Module 8: Fence Breach Detection Demo"
    )
    parser.add_argument("--source", choices=["video", "webcam"], default="video", help="Input source type")
    parser.add_argument("--input", default="videos/test.mp4", help="Path to video file or webcam index")
    parser.add_argument("--conf", type=float, default=0.35, help="YOLO confidence threshold")
    parser.add_argument("--imgsz", type=int, default=640, help="YOLO inference resolution")
    parser.add_argument("--headless", action="store_true", default=False, help="Run in headless mode without window")
    parser.add_argument("--max-frames", type=int, default=None, help="Maximum number of frames to process")
    parser.add_argument("--print-every", type=int, default=30, help="Print status every N frames")

    args = parser.parse_args()

    run_demo(
        source_type=args.source,
        source_target=args.input,
        conf_threshold=args.conf,
        imgsz=args.imgsz,
        headless=args.headless,
        max_frames=args.max_frames,
        print_every=args.print_every,
    )


if __name__ == "__main__":
    main()
