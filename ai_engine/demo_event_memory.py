"""Standalone demonstration for IBVAP Module 5 (Event Memory and Behavioral History).

Runs the full M1->M2->M4->M5 pipeline on the test video and prints per-track
behavioral memory accumulated across consecutive frames.

Usage:
    python -m ai_engine.demo_event_memory
    python -m ai_engine.demo_event_memory --headless --max-frames 60
    python ai_engine/demo_event_memory.py --source video --input videos/test.mp4
"""

import argparse
import logging
from datetime import datetime
from pathlib import Path
import sys
import time
from typing import Dict, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.detector import YOLODetector
from ai_engine.event_memory import EventMemory, TrackMemory
from ai_engine.preprocessing import FramePreprocessor
from ai_engine.tracker import ByteTrackTracker
from ai_engine.video_input import VideoSource, VideoSourceError

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("demo_event_memory")


# ---------------------------------------------------------------------------
# Helpers
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


def _fmt_ts(dt: datetime) -> str:
    """Format a datetime for compact terminal display."""
    return dt.strftime("%H:%M:%S.%f")[:-3]


def print_memory_snapshot(memory: EventMemory, frame_idx: int) -> None:
    """Print a compact snapshot of all current EventMemory state."""
    all_records = memory.get_all()
    if not all_records:
        print(f"  Frame {frame_idx:04d}: (no tracks in memory)")
        return

    print(f"  Frame {frame_idx:04d} | Tracks in memory: {len(all_records)}")
    for tid, rec in sorted(all_records.items()):
        cx, cy = rec.last_center
        print(
            f"    ID:{tid:3d}  {rec.class_name:10s}"
            f"  frames:{rec.frame_count:4d}"
            f"  hist:{len(rec.history):3d}"
            f"  center:({cx:6.1f},{cy:6.1f})"
            f"  conf:{rec.last_confidence:.2f}"
            f"  first:{_fmt_ts(rec.first_seen)}"
            f"  last:{_fmt_ts(rec.last_seen)}"
        )


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
    max_history: int = 100,
    print_every: int = 30,
) -> dict:
    """Run the M1->M2->M4->M5 EventMemory demonstration.

    Args:
        source_type: "video" or "webcam".
        source_target: File path or camera index string.
        conf_threshold: YOLO detection confidence threshold.
        imgsz: YOLO inference image size.
        headless: If True, skip OpenCV window display.
        max_frames: Stop after this many frames (None = run to end).
        max_history: EventMemory bounded history size per track.
        print_every: Print memory state every N frames.

    Returns:
        Summary dict with pipeline stats for automated verification.
    """
    print("=" * 72)
    print("  IBVAP Module 5 - Event Memory and Behavioral History Demo")
    print("=" * 72)
    print(f"  Source         : {source_type.upper()} -> {source_target}")
    print(f"  Confidence     : {conf_threshold}")
    print(f"  Inference Size : {imgsz}")
    print(f"  Max History    : {max_history}")
    print(f"  Headless       : {headless}")
    print("=" * 72)

    # Build pipeline
    print("\n[*] Initializing pipeline...")
    detector = YOLODetector(conf_threshold=conf_threshold, imgsz=imgsz)
    tracker = ByteTrackTracker(detector)
    preprocessor = FramePreprocessor()
    memory = EventMemory(max_history=max_history)

    print(f"    M1 VideoSource  : ready")
    print(f"    M2 Preprocessor : ready")
    print(f"    M3 YOLODetector : {detector.device}")
    print(f"    M4 ByteTracker  : {tracker.tracker_type}")
    print(f"    M5 EventMemory  : max_history={memory.max_history}")
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

    try:
        print("[*] Processing frames...\n")
        for raw_frame in source:
            frame_count += 1
            frame_time = datetime.utcnow()

            # M2 preprocessing
            processed_frame = preprocessor.process(raw_frame)

            # M4 ByteTrack tracking
            tracked_objects = tracker.update(processed_frame)

            # M5 EventMemory - feed all tracked objects for this frame
            memory.update_batch(tracked_objects, frame_time)

            # Print memory state periodically
            if frame_count == 1 or frame_count % print_every == 0:
                print_memory_snapshot(memory, frame_count)
                print()

            if max_frames and frame_count >= max_frames:
                print(f"[*] Reached max-frames limit ({max_frames}).")
                break

    except KeyboardInterrupt:
        print("\n[*] Interrupted by user.")
    finally:
        source.release()

    elapsed = time.perf_counter() - t_start
    avg_fps = frame_count / elapsed if elapsed > 0 else 0.0

    # Final detailed report
    all_records = memory.get_all()
    print()
    print("=" * 72)
    print("  EVENT MEMORY FINAL REPORT")
    print("=" * 72)
    print(f"  Frames processed        : {frame_count}")
    print(f"  Average FPS             : {avg_fps:.1f}")
    print(f"  Unique tracks in memory : {len(all_records)}")
    print()

    if all_records:
        print("  Per-track summary:")
        print(
            f"  {'ID':>4}  {'Class':10}  {'Frames':>6}  {'Hist':>4}"
            f"  {'First Seen':12}  {'Last Seen':12}  Center"
        )
        print("  " + "-" * 68)
        for tid, rec in sorted(all_records.items()):
            cx, cy = rec.last_center
            print(
                f"  {tid:4d}  {rec.class_name:10s}  {rec.frame_count:6d}"
                f"  {len(rec.history):4d}"
                f"  {_fmt_ts(rec.first_seen):12s}"
                f"  {_fmt_ts(rec.last_seen):12s}"
                f"  ({cx:.1f},{cy:.1f})"
            )

        # Highlight the most persistent track
        best = max(all_records.values(), key=lambda r: r.frame_count)
        print()
        print("  Most persistent track:")
        print(f"    Track ID   : {best.track_id}")
        print(f"    Class      : {best.class_name}")
        print(f"    Frame count: {best.frame_count}")
        print(f"    First seen : {_fmt_ts(best.first_seen)}")
        print(f"    Last seen  : {_fmt_ts(best.last_seen)}")
        print(f"    Hist len   : {len(best.history)}")
        print(f"    Last center: {best.last_center}")
        print(f"    Last bbox  : {best.last_bbox}")
        print(f"    Last conf  : {best.last_confidence:.3f}")

        # Show sample positional observations from that track
        history = memory.get_history(best.track_id)
        if history:
            print()
            print("  Example positional observations (first 3, last 3):")
            sample = (history[:3] + history[-3:]) if len(history) > 6 else history
            printed = set()
            for obs in sample:
                key = (obs.frame_time, obs.center_x, obs.center_y)
                if key in printed:
                    continue
                printed.add(key)
                print(
                    f"    [{_fmt_ts(obs.frame_time)}]"
                    f"  center=({obs.center_x:.1f},{obs.center_y:.1f})"
                    f"  conf={obs.confidence:.3f}"
                )
    else:
        print("  (no objects detected in this video segment)")

    print("=" * 72)

    return {
        "frames_processed": frame_count,
        "avg_fps": avg_fps,
        "unique_tracks": len(all_records),
        "records": all_records,
        "memory": memory,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entrypoint for the Module 5 EventMemory demo."""
    parser = argparse.ArgumentParser(
        description="IBVAP Module 5: Event Memory and Behavioral History Demo",
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
        "--print-every",
        type=int,
        default=30,
        help="Print memory state every N frames (default: 30).",
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

    run_demo(
        source_type=source_type,
        source_target=source_input,
        conf_threshold=args.conf,
        imgsz=args.imgsz,
        headless=args.headless,
        max_frames=args.max_frames,
        max_history=args.max_history,
        print_every=args.print_every,
    )


if __name__ == "__main__":
    main()
