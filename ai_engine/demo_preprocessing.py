"""Standalone test and demonstration program for IBVAP Module 2 (Low-Light CLAHE Enhancement).

Consumes frames from Module 1's unified VideoSource, feeds them through
FramePreprocessor, and displays the original vs enhanced frames side-by-side
with live telemetry HUD.
"""

import argparse
import logging
from pathlib import Path
import sys
import time
from typing import Optional, Tuple

import cv2
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.preprocessing import (
    FramePreprocessor,
    PreprocessResult,
)
from ai_engine.video_input import (
    SourceType,
    VideoSource,
    VideoSourceError,
    VideoSourceNotFoundError,
    VideoSourceOpenError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("demo_preprocessing")


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


def create_side_by_side_display(
    original_frame: np.ndarray,
    processed_frame: np.ndarray,
    result: PreprocessResult,
    source_type: str,
    fps: float,
    threshold: float,
) -> np.ndarray:
    """Compose a side-by-side comparison visualization with telemetry overlay."""
    h, w = original_frame.shape[:2]

    # Annotate labels onto copies for visualization display
    disp_orig = original_frame.copy()
    disp_proc = processed_frame.copy()

    # Header heights and font scaling
    header_h = 40
    font_scale = 0.5
    thickness = 1

    # Left panel header
    cv2.rectangle(disp_orig, (0, 0), (w, header_h), (25, 25, 25), -1)
    cv2.putText(
        disp_orig,
        "RAW INPUT (BGR)",
        (10, 26),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (220, 220, 220),
        thickness,
        cv2.LINE_AA,
    )

    # Right panel header
    status_color = (0, 200, 255) if result.enhancement_applied else (0, 230, 100)
    status_text = (
        "ENHANCED [CLAHE ON]" if result.enhancement_applied else "PASS-THROUGH [CLAHE OFF]"
    )
    cv2.rectangle(disp_proc, (0, 0), (w, header_h), (25, 25, 25), -1)
    cv2.putText(
        disp_proc,
        status_text,
        (10, 26),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        status_color,
        thickness,
        cv2.LINE_AA,
    )

    # Combine side-by-side horizontally
    combined = np.hstack([disp_orig, disp_proc])
    cw = combined.shape[1]

    # Global bottom telemetry banner
    banner_h = 48
    bottom_banner = np.full((banner_h, cw, 3), 20, dtype=np.uint8)

    telemetry_line1 = (
        f"IBVAP M2 | Source: {source_type.upper()} ({w}x{h}) | FPS: {fps:.1f} | "
        f"Threshold: {threshold:.1f}"
    )
    telemetry_line2 = (
        f"Brightness: {result.brightness:.1f}/255 | "
        f"Low-Light: {'YES' if result.is_low_light else 'NO'} | "
        f"CLAHE Applied: {'YES' if result.enhancement_applied else 'NO'} | "
        f"Press 'Q' to quit"
    )

    cv2.putText(
        bottom_banner,
        telemetry_line1,
        (10, 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (200, 200, 200),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        bottom_banner,
        telemetry_line2,
        (10, 38),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (0, 255, 200),
        1,
        cv2.LINE_AA,
    )

    # Stack combined view with bottom banner
    return np.vstack([combined, bottom_banner])


def run_demo(
    source_type: str,
    source_target: str,
    threshold: float,
    clip_limit: float,
    tile_grid_size: int,
    headless: bool = False,
    max_frames: Optional[int] = None,
) -> None:
    """Run the interactive preprocessing demonstration."""
    print("=" * 72)
    print("  IBVAP Module 2 — Low-Light CLAHE Preprocessing Demo")
    print("=" * 72)
    print(f"  Source Type : {source_type}")
    print(f"  Target      : {source_target}")
    print(f"  Threshold   : {threshold}")
    print(f"  Clip Limit  : {clip_limit}")
    print(f"  Tile Grid   : ({tile_grid_size}, {tile_grid_size})")
    print(f"  Headless    : {headless}")
    print("=" * 72)

    # Instantiate preprocessor
    preprocessor = FramePreprocessor(
        brightness_threshold=threshold,
        clip_limit=clip_limit,
        tile_grid_size=(tile_grid_size, tile_grid_size),
    )

    # Resolve VideoSource parameter
    src_param = int(source_target) if source_type == "webcam" and source_target.isdigit() else source_target

    try:
        source = VideoSource(source_type=source_type, source=src_param)
        source.open()
    except VideoSourceError as err:
        print(f"\n[!] Failed to open video source: {err}")
        return

    window_name = "IBVAP Module 2 — Preprocessing (Raw vs CLAHE)"
    frame_count = 0
    t_start = time.perf_counter()
    fps_estimate = 0.0

    clahe_count = 0
    bypass_count = 0

    try:
        print("\n[*] Starting video processing pipeline. Press 'q' in video window to exit.\n")
        for raw_frame in source:
            frame_count += 1

            # Execute preprocessing pipeline
            result = preprocessor.process_with_info(raw_frame)

            if result.enhancement_applied:
                clahe_count += 1
            else:
                bypass_count += 1

            # Estimate FPS
            elapsed = time.perf_counter() - t_start
            if elapsed > 0:
                fps_estimate = frame_count / elapsed

            # Console progress update
            if frame_count % 30 == 1 or frame_count <= 5 or headless:
                print(
                    f"Frame {frame_count:04d} | Brightness: {result.brightness:5.1f} | "
                    f"LowLight: {'YES' if result.is_low_light else 'NO '} | "
                    f"CLAHE: {'APPLIED ' if result.enhancement_applied else 'BYPASSED'} | "
                    f"FPS: {fps_estimate:4.1f}"
                )

            if not headless:
                display = create_side_by_side_display(
                    original_frame=raw_frame,
                    processed_frame=result.frame,
                    result=result,
                    source_type=source_type,
                    fps=fps_estimate,
                    threshold=threshold,
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
    print("\n" + "=" * 72)
    print("  DEMO SUMMARY")
    print("=" * 72)
    print(f"  Total Frames Processed : {frame_count}")
    print(f"  CLAHE Applied (Dark)   : {clahe_count} ({clahe_count / max(1, frame_count) * 100:.1f}%)")
    print(f"  CLAHE Bypassed (Normal): {bypass_count} ({bypass_count / max(1, frame_count) * 100:.1f}%)")
    print(f"  Average FPS            : {avg_fps:.1f}")
    print("=" * 72)


def main():
    """CLI entrypoint for running the Module 2 demo."""
    parser = argparse.ArgumentParser(
        description="IBVAP Module 2: Low-Light Enhancement with CLAHE Demo",
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
        "--threshold",
        type=float,
        default=FramePreprocessor.DEFAULT_BRIGHTNESS_THRESHOLD,
        help=f"Brightness threshold for low-light detection (default: {FramePreprocessor.DEFAULT_BRIGHTNESS_THRESHOLD})",
    )
    parser.add_argument(
        "--clip-limit",
        type=float,
        default=FramePreprocessor.DEFAULT_CLIP_LIMIT,
        help=f"CLAHE contrast clip limit (default: {FramePreprocessor.DEFAULT_CLIP_LIMIT})",
    )
    parser.add_argument(
        "--tile-grid",
        type=int,
        default=8,
        help="CLAHE tile grid size (default: 8)",
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

    args = parser.parse_args()

    # Determine default source if not provided
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
        threshold=args.threshold,
        clip_limit=args.clip_limit,
        tile_grid_size=args.tile_grid,
        headless=args.headless,
        max_frames=args.max_frames,
    )


if __name__ == "__main__":
    main()
