"""Standalone demonstration for IBVAP Module 6 (Movement Trail & Direction Detection).

Runs the full M1->M2->M4->M5->M6 pipeline on the test video and displays
per-track movement information including state, direction, and trail overlay.

Usage:
    python -m ai_engine.demo_movement
    python -m ai_engine.demo_movement --headless --max-frames 120
    python ai_engine/demo_movement.py --source video --input videos/test.mp4
    python ai_engine/demo_movement.py --headless --ref-line 0,360,1280,360
"""

import argparse
import logging
from collections import defaultdict
from datetime import datetime
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
from ai_engine.movement import (
    BorderRelation,
    Direction,
    MovementAnalyzer,
    MovementResult,
    MovementState,
    ReferenceLine,
)
from ai_engine.preprocessing import FramePreprocessor
from ai_engine.tracker import ByteTrackTracker
from ai_engine.video_input import VideoSource, VideoSourceError

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("demo_movement")


# ---------------------------------------------------------------------------
# Color palette (one color per track_id, deterministic)
# ---------------------------------------------------------------------------

_PALETTE: List[Tuple[int, int, int]] = [
    (0, 255, 127),    # spring green
    (255, 128, 0),    # orange
    (0, 191, 255),    # deep sky blue
    (255, 0, 128),    # rose
    (255, 255, 0),    # yellow
    (128, 0, 255),    # purple
    (0, 255, 255),    # cyan
    (255, 64, 64),    # salmon
    (64, 255, 64),    # lime
    (255, 200, 0),    # gold
]


def _track_color(track_id: int) -> Tuple[int, int, int]:
    """Return a deterministic BGR color for a track_id."""
    return _PALETTE[track_id % len(_PALETTE)]


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

_STATE_COLOR = {
    MovementState.STATIONARY: (180, 180, 180),
    MovementState.MOVING:     (0, 255, 80),
}

_DIRECTION_ARROW = {
    Direction.LEFT:       "<",
    Direction.RIGHT:      ">",
    Direction.UP:         "^",
    Direction.DOWN:       "v",
    Direction.STATIONARY: ".",
}

_BORDER_COLOR = {
    BorderRelation.TOWARD:  (0, 80, 255),   # blue-red
    BorderRelation.AWAY:    (0, 200, 255),   # amber
    BorderRelation.PARALLEL: (200, 200, 200),
    BorderRelation.UNKNOWN: (120, 120, 120),
}


def draw_result(frame: np.ndarray, result: MovementResult) -> None:
    """Overlay bounding box, labels, and trail for one MovementResult."""
    if not result.trail:
        return

    color = _track_color(result.track_id)
    current_cx, current_cy = result.current_center

    # --- Trail polyline ---
    if len(result.trail) >= 2:
        pts = np.array(result.trail, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(frame, [pts], isClosed=False, color=color, thickness=2)
        # Fade dots along the trail
        for i, (tx, ty) in enumerate(result.trail[:-1]):
            alpha = int(255 * (i + 1) / len(result.trail))
            dot_color = tuple(int(c * alpha // 255) for c in color)
            cv2.circle(frame, (int(tx), int(ty)), 3, dot_color, -1)

    # --- Current center dot ---
    cv2.circle(frame, (int(current_cx), int(current_cy)), 6, color, -1)

    # --- Label ---
    arrow = _DIRECTION_ARROW[result.direction]
    state_abbrev = "MOV" if result.state == MovementState.MOVING else "STA"
    border_abbrev = result.border_relation.value[:3]  # TOW/AWA/PAR/UNK
    label = (
        f"ID:{result.track_id} {state_abbrev} {arrow} "
        f"D:{result.displacement:.0f}px {border_abbrev}"
    )

    label_x = int(current_cx) + 8
    label_y = int(current_cy) - 8
    # Shadow
    cv2.putText(
        frame, label,
        (label_x + 1, label_y + 1),
        cv2.FONT_HERSHEY_SIMPLEX, 0.45,
        (0, 0, 0), 2, cv2.LINE_AA,
    )
    # Foreground
    state_col = _STATE_COLOR[result.state]
    cv2.putText(
        frame, label,
        (label_x, label_y),
        cv2.FONT_HERSHEY_SIMPLEX, 0.45,
        state_col, 1, cv2.LINE_AA,
    )


def draw_reference_line(frame: np.ndarray, ref: ReferenceLine) -> None:
    """Draw the demo reference line on the frame."""
    pt1 = (int(ref.x1), int(ref.y1))
    pt2 = (int(ref.x2), int(ref.y2))
    cv2.line(frame, pt1, pt2, (0, 0, 220), 2, cv2.LINE_AA)
    cv2.putText(
        frame, "REF LINE",
        (pt1[0] + 4, pt1[1] - 6),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5,
        (0, 0, 220), 1, cv2.LINE_AA,
    )


def draw_hud(
    frame: np.ndarray,
    frame_idx: int,
    fps: float,
    track_count: int,
    moving_count: int,
) -> None:
    """Draw a heads-up display overlay in the top-left corner."""
    lines = [
        f"Frame: {frame_idx}",
        f"FPS  : {fps:.1f}",
        f"Tracks: {track_count}  Moving: {moving_count}",
        "M6 Movement Analyzer",
    ]
    y0 = 20
    for i, line in enumerate(lines):
        y = y0 + i * 18
        cv2.putText(frame, line, (8, y + 1), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45, (0, 0, 0), 2, cv2.LINE_AA)
        cv2.putText(frame, line, (8, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45, (220, 220, 220), 1, cv2.LINE_AA)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_default_video(videos_dir: Path) -> Optional[Path]:
    """Find a suitable sample video in the videos directory."""
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


def parse_ref_line(spec: str) -> Optional[ReferenceLine]:
    """Parse 'x1,y1,x2,y2' string into a ReferenceLine or None."""
    if not spec:
        return None
    parts = [s.strip() for s in spec.split(",")]
    if len(parts) != 4:
        raise ValueError(
            f"--ref-line must be 'x1,y1,x2,y2', got: {spec!r}"
        )
    x1, y1, x2, y2 = (float(p) for p in parts)
    ref = ReferenceLine(x1=x1, y1=y1, x2=x2, y2=y2)
    ref.validate()
    return ref


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------

def run_demo(
    source_type: str,
    source_target: str,
    conf_threshold: float,
    imgsz: int,
    headless: bool = True,
    max_frames: Optional[int] = None,
    max_history: int = 100,
    movement_threshold: float = 5.0,
    trail_length: int = 30,
    direction_window: int = 5,
    reference_line: Optional[ReferenceLine] = None,
    print_every: int = 30,
) -> dict:
    """Run the M1->M2->M4->M5->M6 Movement Analyzer demonstration.

    Args:
        source_type: ``"video"`` or ``"webcam"``.
        source_target: File path or camera-index string.
        conf_threshold: YOLO detection confidence threshold.
        imgsz: YOLO inference image size.
        headless: Skip OpenCV window display when True.
        max_frames: Stop after this many frames (None = run to end).
        max_history: EventMemory bounded history size per track.
        movement_threshold: Pixel displacement for MOVING classification.
        trail_length: Maximum trail points to display.
        direction_window: Number of recent frames averaged for direction.
        reference_line: Optional ReferenceLine for toward/away analysis.
        print_every: Print movement state every N frames in headless mode.

    Returns:
        Summary dict with pipeline statistics.
    """
    print("=" * 72)
    print("  IBVAP Module 6 - Movement Trail & Direction Detection Demo")
    print("=" * 72)
    print(f"  Source          : {source_type.upper()} -> {source_target}")
    print(f"  Confidence      : {conf_threshold}")
    print(f"  Inference Size  : {imgsz}")
    print(f"  Max History     : {max_history}")
    print(f"  Mov. Threshold  : {movement_threshold} px")
    print(f"  Trail Length    : {trail_length} pts")
    print(f"  Direction Window: {direction_window} frames")
    print(f"  Reference Line  : {reference_line}")
    print(f"  Headless        : {headless}")
    print("=" * 72)

    # Build pipeline
    print("\n[*] Initializing pipeline...")
    detector = YOLODetector(conf_threshold=conf_threshold, imgsz=imgsz)
    tracker = ByteTrackTracker(detector)
    preprocessor = FramePreprocessor()
    memory = EventMemory(max_history=max_history)
    analyzer = MovementAnalyzer(
        movement_threshold=movement_threshold,
        trail_length=trail_length,
        direction_window=direction_window,
        reference_line=reference_line,
    )

    print("    M1 VideoSource  : ready")
    print("    M2 Preprocessor : ready")
    print(f"    M3 YOLODetector : {detector.device}")
    print(f"    M4 ByteTracker  : {tracker.tracker_type}")
    print(f"    M5 EventMemory  : max_history={memory.max_history}")
    print(f"    M6 Analyzer     : {analyzer}")
    print()

    src_param = (
        int(source_target)
        if source_type == "webcam" and source_target.isdigit()
        else source_target
    )

    try:
        source = VideoSource(source_type=source_type, source=src_param)
        source.open()
    except VideoSourceError as err:
        print(f"[!] Failed to open video source: {err}")
        return {}

    frame_count = 0
    t_start = time.perf_counter()
    direction_change_counts: Dict[int, int] = defaultdict(int)
    last_directions: Dict[int, Direction] = {}

    # Accumulate all results for summary
    all_results_last_frame: List[MovementResult] = []

    if not headless:
        cv2.namedWindow("IBVAP M6 Movement", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("IBVAP M6 Movement", 1280, 720)

    try:
        print("[*] Processing frames...\n")
        for raw_frame in source:
            frame_count += 1
            frame_time = datetime.utcnow()

            # M2 Preprocessing
            processed = preprocessor.process(raw_frame)

            # M4 ByteTrack
            tracked_objects = tracker.update(processed)

            # M5 EventMemory
            memory.update_batch(tracked_objects, frame_time)

            # M6 Movement analysis
            results = analyzer.analyze_all(memory)
            all_results_last_frame = results

            # Track direction changes for statistics
            for r in results:
                prev_dir = last_directions.get(r.track_id)
                if prev_dir is not None and r.direction != prev_dir:
                    if (r.direction != Direction.STATIONARY
                            and prev_dir != Direction.STATIONARY):
                        direction_change_counts[r.track_id] += 1
                last_directions[r.track_id] = r.direction

            # Display
            elapsed = time.perf_counter() - t_start
            fps = frame_count / elapsed if elapsed > 0 else 0.0

            if not headless:
                display = processed.copy()

                # Draw reference line if configured
                if reference_line is not None:
                    draw_reference_line(display, reference_line)

                # Draw each track's result
                for r in results:
                    draw_result(display, r)

                moving_count = sum(
                    1 for r in results if r.state == MovementState.MOVING
                )
                draw_hud(display, frame_count, fps, len(results), moving_count)

                cv2.imshow("IBVAP M6 Movement", display)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):  # q or Esc
                    print("\n[*] Quit requested.")
                    break

            # Headless periodic print
            if headless and (frame_count == 1 or frame_count % print_every == 0):
                moving_count = sum(
                    1 for r in results if r.state == MovementState.MOVING
                )
                print(
                    f"  Frame {frame_count:05d} | FPS:{fps:5.1f} | "
                    f"Tracks:{len(results):3d} | Moving:{moving_count:3d}"
                )
                for r in sorted(results, key=lambda x: x.track_id):
                    arrow = _DIRECTION_ARROW[r.direction]
                    print(
                        f"    ID:{r.track_id:3d}  "
                        f"{r.state.value:11s}  {r.direction.value:12s} {arrow}"
                        f"  disp:{r.displacement:6.1f}px"
                        f"  trail:{len(r.trail):3d}pts"
                        f"  border:{r.border_relation.value}"
                    )
                print()

            if max_frames and frame_count >= max_frames:
                print(f"[*] Reached max-frames limit ({max_frames}).")
                break

    except KeyboardInterrupt:
        print("\n[*] Interrupted by user.")
    finally:
        source.release()
        if not headless:
            cv2.destroyAllWindows()

    elapsed = time.perf_counter() - t_start
    avg_fps = frame_count / elapsed if elapsed > 0 else 0.0
    all_records = memory.get_all()

    # Final report
    print()
    print("=" * 72)
    print("  MOVEMENT ANALYSIS FINAL REPORT")
    print("=" * 72)
    print(f"  Frames processed : {frame_count}")
    print(f"  Average FPS      : {avg_fps:.1f}")
    print(f"  Unique tracks    : {len(all_records)}")
    print()

    if all_results_last_frame:
        print("  Per-track movement summary (last frame):")
        print(
            f"  {'ID':>4}  {'State':11}  {'Direction':12}  "
            f"{'Disp(px)':>8}  {'Trail':>5}  {'Border':8}  DirChanges"
        )
        print("  " + "-" * 68)
        for r in sorted(all_results_last_frame, key=lambda x: x.track_id):
            print(
                f"  {r.track_id:4d}  {r.state.value:11s}  "
                f"{r.direction.value:12s}  "
                f"{r.displacement:8.1f}  "
                f"{len(r.trail):5d}  "
                f"{r.border_relation.value:8s}  "
                f"{direction_change_counts.get(r.track_id, 0)}"
            )
    else:
        print("  (no objects detected in this video segment)")

    print()
    print("  Direction change counts:")
    if direction_change_counts:
        for tid, cnt in sorted(direction_change_counts.items()):
            print(f"    Track {tid:3d}: {cnt} direction changes")
    else:
        print("    (none recorded)")
    print("=" * 72)

    return {
        "frames_processed": frame_count,
        "avg_fps": avg_fps,
        "unique_tracks": len(all_records),
        "direction_changes": dict(direction_change_counts),
        "last_results": all_results_last_frame,
        "memory": memory,
        "analyzer": analyzer,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entrypoint for the Module 6 Movement demo."""
    parser = argparse.ArgumentParser(
        description="IBVAP Module 6: Movement Trail & Direction Detection Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source",
        choices=["webcam", "video"],
        default=None,
        help="Input source type.",
    )
    parser.add_argument(
        "--input",
        dest="source_input",
        default=None,
        help="File path for video, or camera index for webcam.",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=YOLODetector.DEFAULT_CONF_THRESHOLD,
        help="Detection confidence threshold.",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=YOLODetector.DEFAULT_IMGSZ,
        help="YOLO inference image size.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without an OpenCV GUI window.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Stop after this many frames.",
    )
    parser.add_argument(
        "--max-history",
        type=int,
        default=100,
        help="EventMemory max positional observations per track (default: 100).",
    )
    parser.add_argument(
        "--movement-threshold",
        type=float,
        default=5.0,
        help="Pixel displacement threshold for MOVING (default: 5.0).",
    )
    parser.add_argument(
        "--trail-length",
        type=int,
        default=30,
        help="Maximum trail points displayed (default: 30).",
    )
    parser.add_argument(
        "--direction-window",
        type=int,
        default=5,
        help="Recent frames averaged for direction smoothing (default: 5).",
    )
    parser.add_argument(
        "--ref-line",
        type=str,
        default="",
        help=(
            "Demo reference line as 'x1,y1,x2,y2' (pixel coordinates). "
            "Enables toward/away classification.  Example: 0,360,1280,360 "
            "for a horizontal mid-line. Leave empty for UNKNOWN border_relation."
        ),
    )
    parser.add_argument(
        "--print-every",
        type=int,
        default=30,
        help="Print movement state every N frames in headless mode (default: 30).",
    )

    args = parser.parse_args()

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
            print("[!] --source video selected but no video file found.")
            sys.exit(1)
    elif source_type == "webcam" and not source_input:
        source_input = "0"

    # Parse optional reference line (demo-only config)
    reference_line: Optional[ReferenceLine] = None
    if args.ref_line:
        try:
            reference_line = parse_ref_line(args.ref_line)
            print(f"[*] Demo reference line configured: {reference_line}")
        except ValueError as err:
            print(f"[!] Invalid --ref-line: {err}")
            sys.exit(1)

    run_demo(
        source_type=source_type,
        source_target=source_input,
        conf_threshold=args.conf,
        imgsz=args.imgsz,
        headless=args.headless,
        max_frames=args.max_frames,
        max_history=args.max_history,
        movement_threshold=args.movement_threshold,
        trail_length=args.trail_length,
        direction_window=args.direction_window,
        reference_line=reference_line,
        print_every=args.print_every,
    )


if __name__ == "__main__":
    main()
