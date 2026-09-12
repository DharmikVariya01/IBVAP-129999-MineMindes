"""Standalone demonstration for IBVAP Module 9 (Loitering Detection).

Runs the full end-to-end video analytics pipeline:
    M1 VideoSource
    -> M2 Preprocessor
    -> M3 YOLO Detector
    -> M4 ByteTrack Tracker
    -> M5 Event Memory
    -> M6 Movement Analyzer
    -> M7 Zone Manager
    -> M8 Fence Breach Detector
    -> M9 Loitering Detector (this module)

Detects prolonged localized presence of tracked objects remaining within a
spatial radius for longer than a configurable duration (default: 30.0s).

Usage:
    python -m ai_engine.demo_loitering
    python -m ai_engine.demo_loitering --headless --max-frames 90
    python run_loitering_demo.py --headless --max-frames 120
    python run_loitering_demo.py --source video --input videos/test.mp4
    python run_loitering_demo.py --threshold 5.0 --headless
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
from ai_engine.fence_breach import FenceBreachDetector, FenceState
from ai_engine.loitering import (
    DEFAULT_LOITERING_DURATION,
    DEFAULT_MIN_OBSERVATIONS,
    DEFAULT_SPATIAL_RADIUS,
    LoiteringDetector,
    LoiteringEvent,
    LoiteringResult,
    LoiteringState,
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
logger = logging.getLogger("demo_loitering")


# ---------------------------------------------------------------------------
# Virtual Fence & Zones Setup
# ---------------------------------------------------------------------------

def create_demo_zone_manager(width: int = 1280, height: int = 720) -> ZoneManager:
    """Create a deterministic virtual fence and surveillance zone configuration."""
    zm = ZoneManager(include_boundary=True)

    sx = width / 1280.0
    sy = height / 720.0

    def pt(x: float, y: float) -> Tuple[int, int]:
        return int(round(x * sx)), int(round(y * sy))

    # Virtual Perimeter Fence
    zm.create_zone(
        zone_id="virtual_fence",
        zone_name="Perimeter Virtual Fence",
        zone_type=ZoneType.FENCE,
        polygon=[pt(200, 150), pt(1080, 150), pt(1080, 650), pt(200, 650)],
        color=(255, 255, 0),  # Cyan
    )

    # Restricted Monitoring Zone
    zm.create_zone(
        zone_id="monitoring_zone",
        zone_name="Secure Dwell Sector",
        zone_type=ZoneType.RESTRICTED,
        polygon=[pt(350, 220), pt(930, 220), pt(930, 580), pt(350, 580)],
        color=(0, 0, 230),  # Red
    )

    return zm


# ---------------------------------------------------------------------------
# Visual Rendering Helpers
# ---------------------------------------------------------------------------

def draw_zones_overlay(frame: np.ndarray, zone_manager: ZoneManager, alpha: float = 0.15) -> None:
    """Render configured zones with semi-transparent fill and perimeter line."""
    overlay = frame.copy()

    for zone in zone_manager.get_zones():
        pts = np.array(zone.polygon, dtype=np.int32).reshape((-1, 1, 2))
        color = zone.color or DEFAULT_ZONE_COLORS.get(zone.zone_type, (255, 255, 255))

        cv2.fillPoly(overlay, [pts], color)
        thickness = 3 if zone.zone_type == ZoneType.FENCE else 2
        cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=thickness, lineType=cv2.LINE_AA)

        x_min = int(np.min(pts[:, 0, 0]))
        y_min = int(np.min(pts[:, 0, 1]))
        tag = f"{zone.zone_name} [{zone.zone_type.value}]"
        cv2.putText(
            frame,
            tag,
            (x_min + 6, max(y_min + 20, 24)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            tag,
            (x_min + 6, max(y_min + 20, 24)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )

    cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, frame)


def draw_loitering_object(
    frame: np.ndarray,
    tracked_obj: TrackedObject,
    loitering_result: LoiteringResult,
    fence_state: FenceState,
    recent_alert: bool = False,
) -> None:
    """Render bounding box, spatial anchor circle, dwell progress bar, and labels."""
    x1, y1, x2, y2 = tracked_obj.x1, tracked_obj.y1, tracked_obj.x2, tracked_obj.y2
    cx = int(round((x1 + x2) / 2.0))
    cy = int(round((y1 + y2) / 2.0))

    is_loitering = loitering_result.is_loitering
    anchor_x = int(round(loitering_result.anchor_center[0]))
    anchor_y = int(round(loitering_result.anchor_center[1]))
    radius = int(round(loitering_result.spatial_radius))
    dwell_sec = loitering_result.duration_seconds
    thresh_sec = loitering_result.threshold_seconds

    # Color scheme: Red if LOITERING, Orange/Amber if accumulating dwell, Cyan/Gray otherwise
    if is_loitering or recent_alert:
        box_color = (0, 0, 255)       # Red
        anchor_color = (0, 0, 255)
        thickness = 3
    elif dwell_sec > 2.0:
        box_color = (0, 165, 255)     # Amber / Orange
        anchor_color = (0, 165, 255)
        thickness = 2
    else:
        box_color = (255, 255, 0) if fence_state == FenceState.INSIDE else (180, 180, 180)
        anchor_color = (120, 120, 120)
        thickness = 2

    # Draw Spatial Anchor localized zone circle
    cv2.circle(frame, (anchor_x, anchor_y), radius, anchor_color, 1, cv2.LINE_AA)
    cv2.circle(frame, (anchor_x, anchor_y), 3, anchor_color, -1, cv2.LINE_AA)

    # Draw line from anchor to current centroid
    cv2.line(frame, (anchor_x, anchor_y), (cx, cy), anchor_color, 1, cv2.LINE_AA)

    # Draw Bounding Box & Centroid
    cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, thickness, cv2.LINE_AA)
    cv2.circle(frame, (cx, cy), 4, (0, 255, 255), -1, cv2.LINE_AA)

    # Badge Label
    pct = min(100.0, (dwell_sec / thresh_sec) * 100.0) if thresh_sec > 0 else 0.0
    if is_loitering:
        badge_text = f"ID:{tracked_obj.track_id} [LOITERING!] {dwell_sec:.1f}s"
    else:
        badge_text = f"ID:{tracked_obj.track_id} {tracked_obj.class_name} | Dwell: {dwell_sec:.1f}s/{thresh_sec:.1f}s ({pct:.0f}%)"

    (tw, th), _ = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.40, 1)
    badge_y1 = max(y1 - 18, 0)
    badge_y2 = badge_y1 + th + 6
    cv2.rectangle(frame, (x1, badge_y1), (x1 + tw + 8, badge_y2), (20, 20, 20), -1)
    cv2.rectangle(frame, (x1, badge_y1), (x1 + tw + 8, badge_y2), box_color, 1)

    cv2.putText(
        frame,
        badge_text,
        (x1 + 4, badge_y2 - 3),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        box_color,
        1,
        cv2.LINE_AA,
    )

    # Dwell progress bar underneath bounding box
    bar_w = x2 - x1
    bar_h = 4
    bar_y = y2 + 4
    if bar_w > 10:
        cv2.rectangle(frame, (x1, bar_y), (x2, bar_y + bar_h), (40, 40, 40), -1)
        fill_w = int(round(bar_w * (pct / 100.0)))
        bar_color = (0, 0, 255) if is_loitering else (0, 200, 255)
        if fill_w > 0:
            cv2.rectangle(frame, (x1, bar_y), (x1 + fill_w, bar_y + bar_h), bar_color, -1)


def draw_hud(
    frame: np.ndarray,
    frame_idx: int,
    fps: float,
    active_tracks: int,
    active_loitering: int,
    total_loiter_events: int,
    threshold_sec: float,
    max_dwell: float,
    alert_msg: Optional[str] = None,
) -> None:
    """Draw heads-up telemetry and loitering alert banner."""
    panel_h = 115
    panel_w = 440
    overlay = frame.copy()
    cv2.rectangle(overlay, (8, 8), (8 + panel_w, 8 + panel_h), (15, 15, 15), -1)
    cv2.addWeighted(overlay, 0.80, frame, 0.20, 0, frame)
    cv2.rectangle(frame, (8, 8), (8 + panel_w, 8 + panel_h), (80, 80, 80), 1)

    title = "IBVAP M9: Loitering Analytics System"
    cv2.putText(frame, title, (14, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 255), 1, cv2.LINE_AA)

    lines = [
        f"Frame: {frame_idx:4d} | FPS: {fps:4.1f} | Active Tracks: {active_tracks}",
        f"Loitering Status : Active={active_loitering:2d} | Threshold={threshold_sec:.1f}s",
        f"Cumulative Events: {total_loiter_events} | Max Dwell: {max_dwell:.1f}s",
    ]

    for i, line in enumerate(lines):
        y = 46 + i * 18
        cv2.putText(frame, line, (14, y), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 220, 220), 1, cv2.LINE_AA)

    if alert_msg:
        cv2.putText(frame, alert_msg, (14, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 255), 1, cv2.LINE_AA)


# ---------------------------------------------------------------------------
# Demo Runner
# ---------------------------------------------------------------------------

def run_demo(
    source_type: str = "video",
    input_path: str = "videos/test.mp4",
    threshold: float = DEFAULT_LOITERING_DURATION,
    radius: float = DEFAULT_SPATIAL_RADIUS,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
    headless: bool = False,
    max_frames: Optional[int] = None,
    print_every: int = 15,
    device: str = "cpu",
) -> None:
    """Execute the full video analytics pipeline with Module 9 Loitering Detection."""
    print("=" * 72)
    print("  IBVAP Video Analytics Pipeline - Module 9: Loitering Detection")
    print("=" * 72)

    src_param = int(input_path) if source_type == "webcam" and input_path.isdigit() else input_path

    try:
        source = VideoSource(source_type=source_type, source=src_param)
        source.open()
    except VideoSourceError as err:
        print(f"\n[ERROR] Failed to open video source: {err}")
        return

    print(f"[*] Video Source Opened: {source_type} ({input_path})")
    print(f"    Resolution: {source.width}x{source.height} | FPS: {source.fps:.1f} | Total Frames: {source.frame_count}")

    # Initialize Modules M2 - M9
    print("[*] Initializing analytics pipeline modules...")
    preprocessor = FramePreprocessor()
    detector = YOLODetector(device=device)
    tracker = ByteTrackTracker(detector=detector)
    memory = EventMemory(max_history=100)
    movement = MovementAnalyzer()

    w = source.width or 1280
    h = source.height or 720
    zone_manager = create_demo_zone_manager(width=w, height=h)
    breach_detector = FenceBreachDetector(default_fence_id="virtual_fence")

    # M9 Loitering Detector
    loitering_detector = LoiteringDetector(
        loitering_duration_seconds=threshold,
        spatial_radius=radius,
        min_observations=min_observations,
        fps=source.fps if source.fps and source.fps > 0 else 6.0,
    )

    print("    M1 VideoSource       : ready")
    print("    M2 Preprocessor      : ready")
    print("    M3 YOLODetector      : ready")
    print("    M4 ByteTrackTracker  : ready")
    print("    M5 EventMemory       : ready")
    print("    M6 MovementAnalyzer  : ready")
    print(f"    M7 ZoneManager       : ready ({len(zone_manager)} zones configured)")
    print("    M8 FenceBreachDetect : ready")
    print(
        f"    M9 LoiteringDetector : ready (threshold={threshold:.1f}s, "
        f"radius={radius:.1f}px, min_obs={min_observations})"
    )
    print()

    frame_count = 0
    t_start = time.perf_counter()

    unique_tracks = set()
    all_loitering_events: List[LoiteringEvent] = []
    recent_alerts: Dict[int, int] = {}  # track_id -> frame_detected
    max_dwell_observed = 0.0

    if not headless:
        cv2.namedWindow("IBVAP M9 Loitering System", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("IBVAP M9 Loitering System", 1280, 720)

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
            breach_detector.update_batch(
                zone_results,
                frame_id=frame_count,
                timestamp=timestamp_sec,
            )

            # M9 Loitering Detection
            active_ids = [obj.track_id for obj in tracked_objects]
            loitering_results = loitering_detector.update_from_memory(
                event_memory=memory,
                active_track_ids=active_ids,
                frame_id=frame_count,
                timestamp=timestamp_sec,
                zone_results=zone_results,
            )

            # Cleanup stale tracks
            breach_detector.cleanup_stale_tracks(active_ids)
            loitering_detector.cleanup_stale_tracks(
                active_ids,
                max_stale_frames=15,
                current_frame=frame_count,
            )

            # Check for newly triggered loitering events
            for res in loitering_results:
                unique_tracks.add(res.track_id)
                if res.duration_seconds > max_dwell_observed:
                    max_dwell_observed = res.duration_seconds

                if res.new_event is not None:
                    all_loitering_events.append(res.new_event)
                    recent_alerts[res.track_id] = frame_count
                    print(
                        f"  [!] >>> LOITERING DETECTED <<< Frame {frame_count:4d} | "
                        f"Track #{res.track_id} localized for {res.duration_seconds:.1f}s "
                        f"(anchor: {res.anchor_center}, disp: {res.spatial_displacement:.1f}px) | "
                        f"Zone: {res.zone_name or 'None'}"
                    )

            # Expire alert indicators after 25 frames
            expired = [tid for tid, f in recent_alerts.items() if frame_count - f > 25]
            for tid in expired:
                del recent_alerts[tid]

            # Logging
            if frame_count % print_every == 0 or frame_count == 1:
                elapsed = time.perf_counter() - t_start
                fps = frame_count / elapsed if elapsed > 0 else 0.0
                active_loiter = loitering_detector.active_loitering_count
                print(
                    f"  [Frame {frame_count:4d}] FPS: {fps:4.1f} | Active: {len(tracked_objects):2d} | "
                    f"Loitering: {active_loiter:2d} | Max Dwell: {max_dwell_observed:4.1f}s | "
                    f"Total Events: {loitering_detector.total_loitering_events}"
                )

            # GUI Rendering
            if not headless:
                display = processed.copy()
                draw_zones_overlay(display, zone_manager)

                # Map results
                res_map = {r.track_id: r for r in loitering_results}
                zr_map = {z.track_id: z for z in zone_results}

                for obj in tracked_objects:
                    l_res = res_map.get(obj.track_id)
                    zr = zr_map.get(obj.track_id)
                    f_state = breach_detector.get_fence_state(obj.track_id)
                    is_alert = obj.track_id in recent_alerts

                    if l_res is not None and zr is not None:
                        draw_loitering_object(display, obj, l_res, f_state, recent_alert=is_alert)

                elapsed = time.perf_counter() - t_start
                fps = frame_count / elapsed if elapsed > 0 else 0.0
                alert_text = (
                    f"ALERT: Track #{list(recent_alerts.keys())[0]} LOITERING DETECTED!"
                    if recent_alerts
                    else None
                )
                draw_hud(
                    display,
                    frame_idx=frame_count,
                    fps=fps,
                    active_tracks=len(tracked_objects),
                    active_loitering=loitering_detector.active_loitering_count,
                    total_loiter_events=loitering_detector.total_loitering_events,
                    threshold_sec=threshold,
                    max_dwell=max_dwell_observed,
                    alert_msg=alert_text,
                )

                cv2.imshow("IBVAP M9 Loitering System", display)
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
    print("  IBVAP Module 9 - Execution Summary")
    print("=" * 72)
    print(f"  Frames processed        : {frame_count}")
    print(f"  Total processing time   : {total_time:.2f} s")
    print(f"  Average FPS             : {avg_fps:.1f}")
    print(f"  Unique tracks observed  : {len(unique_tracks)}")
    print(f"  Loitering threshold     : {threshold:.1f} s")
    print(f"  Spatial radius          : {radius:.1f} px")
    print(f"  Max dwell observed      : {max_dwell_observed:.2f} s")
    print(f"  Total loitering events  : {len(all_loitering_events)}")

    if len(all_loitering_events) == 0:
        if threshold >= 30.0:
            print("\n  [RESULT] No qualifying 30-second loitering event observed in the selected test segment.")
        else:
            print(f"\n  [RESULT] No qualifying {threshold:.1f}-second loitering event observed in the selected test segment.")
    else:
        print("\n  Loitering Events Log:")
        for ev in all_loitering_events:
            print(
                f"    - Frame {ev.frame_id}: Track #{ev.track_id} "
                f"dwell={ev.duration_seconds:.1f}s (threshold={ev.threshold_seconds:.1f}s) "
                f"displacement={ev.spatial_displacement:.1f}px (radius={ev.spatial_radius:.1f}px) "
                f"anchor={ev.anchor_center} | Zone: {ev.zone_name or 'None'}"
            )
    print("=" * 72 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="IBVAP Module 9 Loitering Detection Demo")
    parser.add_argument("--source", choices=["video", "webcam", "rtsp"], default="video")
    parser.add_argument("--input", default="videos/test.mp4")
    parser.add_argument("--threshold", type=float, default=DEFAULT_LOITERING_DURATION, help="Loitering duration threshold in seconds (default: 30.0)")
    parser.add_argument("--radius", type=float, default=DEFAULT_SPATIAL_RADIUS, help="Spatial radius in pixels (default: 50.0)")
    parser.add_argument("--min-obs", type=int, default=DEFAULT_MIN_OBSERVATIONS, help="Minimum observations before loitering event (default: 5)")
    parser.add_argument("--headless", action="store_true", help="Run without graphical window")
    parser.add_argument("--max-frames", type=int, default=None, help="Stop after N frames")
    parser.add_argument("--print-every", type=int, default=15, help="Frame logging interval")
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")

    args = parser.parse_args()

    run_demo(
        source_type=args.source,
        input_path=args.input,
        threshold=args.threshold,
        radius=args.radius,
        min_observations=args.min_obs,
        headless=args.headless,
        max_frames=args.max_frames,
        print_every=args.print_every,
        device=args.device,
    )


if __name__ == "__main__":
    main()
