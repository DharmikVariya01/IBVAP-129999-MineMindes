"""Standalone demonstration for IBVAP Module 7 (Virtual Fence & Zone System).

Runs the full pipeline:
    M1 VideoInput -> M2 Preprocessing -> M3 YOLO -> M4 ByteTrack -> M5 EventMemory -> M6 Movement -> M7 ZoneManager
on a test video and demonstrates spatial geofencing and zone classification.

Usage:
    python -m ai_engine.demo_zones
    python -m ai_engine.demo_zones --headless --max-frames 90
    python run_zones_demo.py --headless --max-frames 120
    python run_zones_demo.py --source video --input videos/test.mp4
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
logger = logging.getLogger("demo_zones")


# ---------------------------------------------------------------------------
# Default Demonstration Zones
# ---------------------------------------------------------------------------

def create_default_demo_zones(width: int = 1280, height: int = 720) -> ZoneManager:
    """Create sample spatial zones scaled to the input video dimensions.

    Defines:
    1. RESTRICTED Zone (Red): High-security border corridor
    2. SENSITIVE Zone (Orange): Buffer area (partially overlapping to show priority)
    3. NORMAL Zone (Green): Standard surveillance field
    4. FENCE Zone (Cyan): Virtual perimeter fence enclosing the tactical area
    """
    zm = ZoneManager(include_boundary=True)

    # Scale factors relative to 1280x720 reference
    sx = width / 1280.0
    sy = height / 720.0

    def pt(x: float, y: float) -> Tuple[int, int]:
        return int(round(x * sx)), int(round(y * sy))

    # 1. Restricted Zone (Priority 3)
    zm.create_zone(
        zone_id="restricted_corridor",
        zone_name="Restricted Border Corridor",
        zone_type=ZoneType.RESTRICTED,
        polygon=[pt(100, 200), pt(580, 200), pt(580, 520), pt(100, 520)],
        color=(0, 0, 220),  # Red
    )

    # 2. Sensitive Zone (Priority 2) - overlaps partly with restricted (from x=500)
    zm.create_zone(
        zone_id="sensitive_buffer",
        zone_name="Sensitive Buffer Area",
        zone_type=ZoneType.SENSITIVE,
        polygon=[pt(500, 240), pt(920, 240), pt(920, 600), pt(500, 600)],
        color=(0, 165, 255),  # Orange
    )

    # 3. Normal Zone (Priority 1)
    zm.create_zone(
        zone_id="normal_corridor",
        zone_name="Normal Observation Zone",
        zone_type=ZoneType.NORMAL,
        polygon=[pt(750, 80), pt(1200, 80), pt(1200, 420), pt(750, 420)],
        color=(0, 200, 0),  # Green
    )

    # 4. Virtual Fence Zone (Independent fence tracking)
    zm.create_zone(
        zone_id="virtual_fence",
        zone_name="Virtual Perimeter Fence",
        zone_type=ZoneType.FENCE,
        polygon=[pt(60, 60), pt(1220, 60), pt(1220, 660), pt(60, 660)],
        color=(255, 255, 0),  # Cyan
    )

    return zm


# ---------------------------------------------------------------------------
# Visual Rendering Helpers
# ---------------------------------------------------------------------------

def draw_zones(frame: np.ndarray, zone_manager: ZoneManager, alpha: float = 0.22) -> None:
    """Render zone polygons with semi-transparent fills and crisp borders."""
    overlay = frame.copy()

    for zone in zone_manager.get_zones():
        pts = np.array(zone.polygon, dtype=np.int32).reshape((-1, 1, 2))
        color = zone.color or DEFAULT_ZONE_COLORS.get(zone.zone_type, (255, 255, 255))

        # Fill polygon on overlay
        cv2.fillPoly(overlay, [pts], color)

        # Crisp contour boundary on original frame
        line_type = cv2.LINE_DASHED if zone.zone_type == ZoneType.FENCE else cv2.LINE_AA
        cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2, lineType=cv2.LINE_AA)

        # Zone Label badge
        x_min = int(np.min(pts[:, 0, 0]))
        y_min = int(np.min(pts[:, 0, 1]))
        label = f"{zone.zone_name} [{zone.zone_type.value}]"
        cv2.putText(
            frame,
            label,
            (x_min + 6, max(y_min + 18, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            label,
            (x_min + 6, max(y_min + 18, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )

    # Blend overlay with original frame
    cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, frame)


def draw_tracked_object_zone(
    frame: np.ndarray,
    tracked_obj: TrackedObject,
    zone_result: ZoneResult,
) -> None:
    """Render bounding box, centroid, and zone classification badge for an object."""
    x1, y1, x2, y2 = tracked_obj.x1, tracked_obj.y1, tracked_obj.x2, tracked_obj.y2
    cx, cy = zone_result.center

    # Determine status color
    if zone_result.zone_type == ZoneType.RESTRICTED:
        color = (0, 0, 230)      # Red
    elif zone_result.zone_type == ZoneType.SENSITIVE:
        color = (0, 165, 255)    # Orange
    elif zone_result.zone_type == ZoneType.NORMAL:
        color = (0, 220, 0)      # Green
    elif zone_result.fence_inside:
        color = (255, 255, 0)    # Cyan
    else:
        color = (180, 180, 180)  # Gray (Outside)

    # Bounding Box
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)

    # Centroid dot
    cv2.circle(frame, (cx, cy), 4, (0, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(frame, (cx, cy), 6, (0, 0, 0), 1, cv2.LINE_AA)

    # Status Label
    zone_str = zone_result.zone_type.value if zone_result.zone_type else "OUTSIDE"
    fence_tag = " [FENCE]" if zone_result.fence_inside else ""
    label = f"ID:{zone_result.track_id} {tracked_obj.class_name} | {zone_str}{fence_tag}"

    # Text badge background
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
    badge_y1 = max(y1 - 18, 0)
    badge_y2 = badge_y1 + th + 6
    cv2.rectangle(frame, (x1, badge_y1), (x1 + tw + 8, badge_y2), (20, 20, 20), -1)
    cv2.rectangle(frame, (x1, badge_y1), (x1 + tw + 8, badge_y2), color, 1)

    cv2.putText(
        frame,
        label,
        (x1 + 4, badge_y2 - 3),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        color,
        1,
        cv2.LINE_AA,
    )


def draw_hud(
    frame: np.ndarray,
    frame_idx: int,
    fps: float,
    total_tracks: int,
    zone_counts: Dict[str, int],
    fence_count: int,
) -> None:
    """Draw a heads-up display overlay in the top-left corner."""
    panel_h = 100
    panel_w = 340
    overlay = frame.copy()
    cv2.rectangle(overlay, (8, 8), (8 + panel_w, 8 + panel_h), (15, 15, 15), -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
    cv2.rectangle(frame, (8, 8), (8 + panel_w, 8 + panel_h), (80, 80, 80), 1)

    title = "IBVAP M7: Virtual Fence & Zone System"
    cv2.putText(frame, title, (14, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 255), 1, cv2.LINE_AA)

    lines = [
        f"Frame: {frame_idx:4d} | FPS: {fps:4.1f} | Active Tracks: {total_tracks}",
        f"RESTRICTED: {zone_counts.get(ZoneType.RESTRICTED.value, 0):2d}  | SENSITIVE: {zone_counts.get(ZoneType.SENSITIVE.value, 0):2d}",
        f"NORMAL    : {zone_counts.get(ZoneType.NORMAL.value, 0):2d}  | FENCE IN : {fence_count:2d}",
        f"OUTSIDE   : {zone_counts.get('OUTSIDE', 0):2d}",
    ]

    for i, line in enumerate(lines):
        y = 44 + i * 16
        cv2.putText(frame, line, (14, y), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (220, 220, 220), 1, cv2.LINE_AA)


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
    """Run the Module 7 demonstration pipeline.

    Returns:
        Summary dict containing execution statistics.
    """
    print("=" * 72)
    print("  IBVAP Module 7 - Virtual Fence & Zone System Demonstration")
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

    print("    M1 VideoSource   : ready")
    print("    M2 Preprocessor  : ready")
    print(f"    M3 YOLODetector  : {detector.device}")
    print(f"    M4 ByteTracker   : {tracker.tracker_type}")
    print("    M5 EventMemory   : ready")
    print("    M6 Movement      : ready")

    src_param = int(source_target) if source_type == "webcam" and source_target.isdigit() else source_target

    try:
        source = VideoSource(source_type=source_type, source=src_param)
        source.open()
    except VideoSourceError as err:
        print(f"[!] Failed to open video source: {err}")
        return {}

    w = source.width or 1280
    h = source.height or 720
    zone_manager = create_default_demo_zones(width=w, height=h)
    print(f"    M7 ZoneManager   : ready ({len(zone_manager)} zones configured for {w}x{h})")
    for z in zone_manager.get_zones():
        print(f"       - [{z.zone_type.value:10s}] {z.zone_name} ({len(z.polygon)} vertices)")
    print()

    frame_count = 0
    t_start = time.perf_counter()

    # Metrics
    unique_tracks = set()
    zone_occupancy_total = defaultdict(int)
    fence_inside_total = 0
    total_classifications = 0

    if not headless:
        cv2.namedWindow("IBVAP M7 Zone System", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("IBVAP M7 Zone System", 1280, 720)

    try:
        print("[*] Processing frames...\n")
        for raw_frame in source:
            frame_count += 1
            now = datetime.utcnow()

            # M2 Preprocessing
            processed = preprocessor.process(raw_frame)

            # M4 Tracking
            tracked_objects = tracker.update(processed)

            # M5 Event Memory & M6 Movement
            memory.update_batch(tracked_objects, now)
            movement.analyze_all(memory)

            # M7 Zone Classification
            zone_results = zone_manager.classify_objects(tracked_objects)

            # Aggregates for current frame
            curr_zone_counts = defaultdict(int)
            curr_fence_count = 0

            for zr in zone_results:
                unique_tracks.add(zr.track_id)
                total_classifications += 1

                if zr.zone_type:
                    curr_zone_counts[zr.zone_type.value] += 1
                    zone_occupancy_total[zr.zone_type.value] += 1
                else:
                    curr_zone_counts["OUTSIDE"] += 1
                    zone_occupancy_total["OUTSIDE"] += 1

                if zr.fence_inside:
                    curr_fence_count += 1
                    fence_inside_total += 1

            # Logging
            if frame_count % print_every == 0 or frame_count == 1:
                elapsed = time.perf_counter() - t_start
                fps = frame_count / elapsed if elapsed > 0 else 0.0
                print(
                    f"  [Frame {frame_count:4d}] FPS: {fps:4.1f} | Active Tracks: {len(tracked_objects):2d} | "
                    f"RESTRICTED: {curr_zone_counts[ZoneType.RESTRICTED.value]} | "
                    f"SENSITIVE: {curr_zone_counts[ZoneType.SENSITIVE.value]} | "
                    f"NORMAL: {curr_zone_counts[ZoneType.NORMAL.value]} | "
                    f"FENCE: {curr_fence_count} | "
                    f"OUTSIDE: {curr_zone_counts['OUTSIDE']}"
                )
                for obj, zr in zip(tracked_objects[:3], zone_results[:3]):
                    z_name = zr.zone_name or "Outside Zones"
                    print(
                        f"     -> Track #{zr.track_id} ({obj.class_name}) center={zr.center} "
                        f"-> {z_name} | Fence={zr.fence_inside}"
                    )

            # GUI Rendering
            if not headless:
                display = processed.copy()
                draw_zones(display, zone_manager)
                for obj, zr in zip(tracked_objects, zone_results):
                    draw_tracked_object_zone(display, obj, zr)

                elapsed = time.perf_counter() - t_start
                fps = frame_count / elapsed if elapsed > 0 else 0.0
                draw_hud(display, frame_count, fps, len(tracked_objects), curr_zone_counts, curr_fence_count)

                cv2.imshow("IBVAP M7 Zone System", display)
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
    print("  IBVAP Module 7 - Execution Summary")
    print("=" * 72)
    print(f"  Frames processed        : {frame_count}")
    print(f"  Total duration          : {total_time:.2f} s")
    print(f"  Average FPS             : {avg_fps:.1f}")
    print(f"  Unique tracks observed  : {len(unique_tracks)}")
    print(f"  Total classifications   : {total_classifications}")
    print("  Zone Occupation Totals  :")
    print(f"    - RESTRICTED          : {zone_occupancy_total[ZoneType.RESTRICTED.value]}")
    print(f"    - SENSITIVE           : {zone_occupancy_total[ZoneType.SENSITIVE.value]}")
    print(f"    - NORMAL              : {zone_occupancy_total[ZoneType.NORMAL.value]}")
    print(f"    - OUTSIDE             : {zone_occupancy_total['OUTSIDE']}")
    print(f"  Virtual Fence Hits      : {fence_inside_total}")
    print("=" * 72)

    return {
        "frames": frame_count,
        "duration_sec": total_time,
        "avg_fps": avg_fps,
        "unique_tracks": len(unique_tracks),
        "classifications": total_classifications,
        "zone_occupancy": dict(zone_occupancy_total),
        "fence_inside_total": fence_inside_total,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="IBVAP Module 7: Virtual Fence & Zone System Demo"
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
