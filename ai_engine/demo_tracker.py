"""Standalone demonstration for IBVAP Module 4 (ByteTrack Persistent Object Tracking).

Consumes frames from Module 1's VideoSource, preprocesses them via Module 2's
FramePreprocessor, runs Module 4's ByteTrackTracker (which internally invokes
the Module 3 YOLO model), and displays annotated frames with tracking bounding
boxes, persistent track IDs, class labels, confidence scores, and a telemetry HUD.
"""

import argparse
import logging
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional

import cv2
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.detector import YOLODetector
from ai_engine.preprocessing import FramePreprocessor
from ai_engine.tracker import ByteTrackTracker, TrackedObject
from ai_engine.video_input import (
    SourceType,
    VideoSource,
    VideoSourceError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("demo_tracker")


# ---------------------------------------------------------------------------
# Color palette for tracked-object annotations
# ---------------------------------------------------------------------------

# BGR colors — distinct for person vs vehicle categories
CATEGORY_COLORS: Dict[str, tuple] = {
    "person": (0, 220, 0),        # Green
    "car": (255, 160, 0),         # Blue-ish
    "motorcycle": (255, 100, 50), # Cyan-ish
    "bus": (200, 100, 255),       # Purple
    "truck": (255, 200, 50),      # Light blue
}

DEFAULT_COLOR = (200, 200, 200)   # Fallback gray


def get_track_color(class_name: str) -> tuple:
    """Return the BGR annotation color for a given class name."""
    return CATEGORY_COLORS.get(class_name, DEFAULT_COLOR)


# ---------------------------------------------------------------------------
# Frame annotation
# ---------------------------------------------------------------------------

def annotate_tracked_frame(
    frame: np.ndarray,
    tracked_objects: List[TrackedObject],
    fps: float,
    source_type: str,
    frame_idx: int,
) -> np.ndarray:
    """Draw tracked bounding boxes with IDs, labels, and a telemetry HUD.

    Args:
        frame: BGR frame to annotate (a copy is made internally).
        tracked_objects: List of TrackedObject results to draw.
        fps: Current FPS estimate for display.
        source_type: Source type string for display.
        frame_idx: Current frame index for display.

    Returns:
        Annotated BGR frame.
    """
    display = frame.copy()
    h, w = display.shape[:2]

    # Draw each tracked object
    for obj in tracked_objects:
        color = get_track_color(obj.class_name)
        thickness = 2

        # Bounding box
        cv2.rectangle(display, (obj.x1, obj.y1), (obj.x2, obj.y2), color, thickness)

        # Label: ID + class + confidence
        label = f"ID:{obj.track_id} {obj.class_name} {obj.confidence:.2f}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.55
        label_thickness = 1

        (lw, lh), baseline = cv2.getTextSize(label, font, font_scale, label_thickness)
        label_y = max(obj.y1 - 6, lh + 4)

        # Label background
        cv2.rectangle(
            display,
            (obj.x1, label_y - lh - 4),
            (obj.x1 + lw + 4, label_y + baseline),
            color,
            -1,
        )
        # Label text (black on colored background)
        cv2.putText(
            display,
            label,
            (obj.x1 + 2, label_y - 2),
            font,
            font_scale,
            (0, 0, 0),
            label_thickness,
            cv2.LINE_AA,
        )

    # HUD banner at top
    banner_h = 36
    overlay = display.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.7, display, 0.3, 0, display)

    # Count by category
    person_count = sum(1 for o in tracked_objects if o.class_name == "person")
    vehicle_count = len(tracked_objects) - person_count
    unique_ids = {o.track_id for o in tracked_objects}

    hud_text = (
        f"IBVAP M4 | Source: {source_type.upper()} | Frame: {frame_idx} | "
        f"FPS: {fps:.1f} | Tracked: {len(tracked_objects)} "
        f"(P:{person_count} V:{vehicle_count}) IDs:{len(unique_ids)}"
    )
    cv2.putText(
        display,
        hud_text,
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (0, 255, 200),
        1,
        cv2.LINE_AA,
    )

    return display


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def find_default_video(videos_dir: Path) -> Optional[Path]:
    """Find a suitable sample video file in the videos directory."""
    if not videos_dir.exists():
        return None
    for ext in ("*.mp4", "*.avi", "*.mov", "*.mkv"):
        matches = list(videos_dir.glob(ext))
        if matches:
            for m in matches:
                if m.name.lower() == "test.mp4":
                    return m
            return matches[0]
    return None


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------

def run_demo(
    source_type: str,
    source_target: str,
    conf_threshold: float,
    imgsz: int,
    headless: bool = False,
    max_frames: Optional[int] = None,
    skip_preprocessing: bool = False,
) -> None:
    """Run the interactive tracking demonstration."""
    print("=" * 72)
    print("  IBVAP Module 4 — ByteTrack Persistent Object Tracking Demo")
    print("=" * 72)
    print(f"  Source Type       : {source_type}")
    print(f"  Target            : {source_target}")
    print(f"  Confidence        : {conf_threshold}")
    print(f"  Inference Size    : {imgsz}")
    print(f"  Preprocessing     : {'DISABLED' if skip_preprocessing else 'ENABLED'}")
    print(f"  Headless          : {headless}")
    print("=" * 72)

    # Initialize detector (model loaded ONCE)
    print("\n[*] Loading YOLOv8n model...")
    detector = YOLODetector(
        conf_threshold=conf_threshold,
        imgsz=imgsz,
    )
    print(f"    Model loaded: {detector.model_path}")
    print(f"    Device: {detector.device}")
    print(f"    Target classes: {list(detector.target_classes.values())}")

    # Initialize tracker (reuses detector's model — no duplicate loading)
    print("[*] Initializing ByteTrack tracker...")
    tracker = ByteTrackTracker(detector)
    print(f"    Tracker: {tracker.tracker_type}")

    # Initialize preprocessor
    preprocessor = None if skip_preprocessing else FramePreprocessor()

    # Resolve VideoSource parameter
    src_param = (
        int(source_target)
        if source_type == "webcam" and source_target.isdigit()
        else source_target
    )

    try:
        source = VideoSource(source_type=source_type, source=src_param)
        source.open()
    except VideoSourceError as err:
        print(f"\n[!] Failed to open video source: {err}")
        return

    window_name = "IBVAP Module 4 — ByteTrack Tracking"
    frame_count = 0
    total_tracked = 0
    all_track_ids: set = set()
    class_counts: Dict[str, int] = {}
    id_persistence: Dict[int, int] = {}  # track_id → number of frames seen
    t_start = time.perf_counter()
    fps_estimate = 0.0

    try:
        print(
            "\n[*] Starting tracking pipeline. Press 'q' in video window to exit.\n"
        )
        for raw_frame in source:
            frame_count += 1

            # Optional preprocessing (M2)
            if preprocessor is not None:
                processed_frame = preprocessor.process(raw_frame)
            else:
                processed_frame = raw_frame

            # Run tracking (M4 — internally uses M3 model)
            tracked_objects = tracker.update(processed_frame)
            total_tracked += len(tracked_objects)

            # Accumulate statistics
            for obj in tracked_objects:
                class_counts[obj.class_name] = (
                    class_counts.get(obj.class_name, 0) + 1
                )
                all_track_ids.add(obj.track_id)
                id_persistence[obj.track_id] = (
                    id_persistence.get(obj.track_id, 0) + 1
                )

            # FPS estimation
            elapsed = time.perf_counter() - t_start
            if elapsed > 0:
                fps_estimate = frame_count / elapsed

            # Console progress
            if frame_count % 30 == 1 or frame_count <= 5 or headless:
                obj_summary = ", ".join(
                    f"ID:{o.track_id} {o.class_name}:{o.confidence:.2f}"
                    for o in tracked_objects[:5]
                )
                if len(tracked_objects) > 5:
                    obj_summary += f" (+{len(tracked_objects) - 5} more)"
                print(
                    f"Frame {frame_count:04d} | "
                    f"Tracked: {len(tracked_objects):2d} | "
                    f"FPS: {fps_estimate:5.1f} | "
                    f"[{obj_summary}]"
                )

            if not headless:
                display = annotate_tracked_frame(
                    processed_frame,
                    tracked_objects,
                    fps_estimate,
                    source_type,
                    frame_count,
                )
                cv2.imshow(window_name, display)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), ord("Q"), 27):
                    print("\n[*] Quit command detected.")
                    break

            if max_frames and frame_count >= max_frames:
                print(f"\n[*] Reached max frames limit ({max_frames}).")
                break

    except KeyboardInterrupt:
        print("\n[*] Interrupted by user.")
    finally:
        source.release()
        if not headless:
            cv2.destroyAllWindows()

    total_time = time.perf_counter() - t_start
    avg_fps = frame_count / total_time if total_time > 0 else 0.0

    # Identify persistent IDs (seen in 2+ frames)
    persistent_ids = {tid: cnt for tid, cnt in id_persistence.items() if cnt >= 2}

    print("\n" + "=" * 72)
    print("  TRACKING DEMO SUMMARY")
    print("=" * 72)
    print(f"  Total Frames Processed  : {frame_count}")
    print(f"  Total Tracked Objects   : {total_tracked}")
    print(f"  Unique Track IDs        : {len(all_track_ids)}")
    print(f"  Persistent IDs (2+ fr)  : {len(persistent_ids)}")
    print(f"  Average FPS             : {avg_fps:.1f}")
    print(f"  Confidence Threshold    : {conf_threshold}")
    print(f"  Inference Size          : {imgsz}")
    print(f"  Device                  : {detector.device}")

    if class_counts:
        print("  Tracked Classes         :")
        for cls_name, count in sorted(class_counts.items()):
            print(f"    {cls_name:15s} : {count}")
    else:
        print("  Tracked Classes         : (none — no target objects found)")

    if persistent_ids:
        print("  ID Persistence (sample) :")
        for tid, cnt in sorted(persistent_ids.items())[:10]:
            print(f"    Track ID {tid:4d} : seen in {cnt} frames")
    else:
        print("  ID Persistence          : (no IDs persisted across 2+ frames)")

    print("=" * 72)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI entrypoint for running the Module 4 demo."""
    parser = argparse.ArgumentParser(
        description="IBVAP Module 4: ByteTrack Persistent Object Tracking Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source",
        choices=["webcam", "video"],
        default=None,
        help="Input source type: 'webcam' or 'video'. (Auto-detected if omitted)",
    )
    parser.add_argument(
        "--input",
        dest="source_input",
        default=None,
        help="Input target: camera index for webcam (e.g. 0), or file path for video.",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=YOLODetector.DEFAULT_CONF_THRESHOLD,
        help=f"Detection confidence threshold (default: {YOLODetector.DEFAULT_CONF_THRESHOLD})",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=YOLODetector.DEFAULT_IMGSZ,
        help=f"YOLO inference image size (default: {YOLODetector.DEFAULT_IMGSZ})",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless terminal mode without opening an OpenCV GUI window.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Limit number of frames to process.",
    )
    parser.add_argument(
        "--skip-preprocessing",
        action="store_true",
        help="Skip Module 2 CLAHE preprocessing (feed raw frames directly to tracker).",
    )

    args = parser.parse_args()

    # Determine default source
    videos_dir = PROJECT_ROOT / "videos"
    default_vid = find_default_video(videos_dir)

    source_type = args.source
    source_input = args.source_input

    if not source_type:
        if default_vid and default_vid.exists():
            source_type = "video"
            source_input = str(default_vid)
        else:
            source_type = "webcam"
            source_input = "0"
    elif source_type == "video" and not source_input:
        if default_vid and default_vid.exists():
            source_input = str(default_vid)
        else:
            print("[!] Error: --source video selected but no sample video found in videos/.")
            sys.exit(1)
    elif source_type == "webcam" and not source_input:
        source_input = "0"

    run_demo(
        source_type=source_type,
        source_target=source_input,
        conf_threshold=args.conf,
        imgsz=args.imgsz,
        headless=args.headless,
        max_frames=args.max_frames,
        skip_preprocessing=args.skip_preprocessing,
    )


if __name__ == "__main__":
    main()
