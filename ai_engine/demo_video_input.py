"""Standalone test and demonstration program for IBVAP Module 1 (Video Input).

Allows developers to test either:
1. Laptop Webcam
2. Local Video File (MP4, etc.)

Consumes frames strictly via the unified VideoSource class without duplicating
any OpenCV VideoCapture logic.
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

from ai_engine.video_input import (
    SourceType,
    VideoSource,
    VideoSourceError,
    VideoSourceNotFoundError,
    VideoSourceOpenError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("demo_video_input")


def find_default_video(videos_dir: Path) -> Optional[Path]:
    """Find a suitable sample video file in the videos directory."""
    if not videos_dir.exists():
        return None
    for ext in ("*.mp4", "*.avi", "*.mov", "*.mkv"):
        matches = list(videos_dir.glob(ext))
        if matches:
            # Prefer test.mp4 if present
            for m in matches:
                if m.name.lower() == "test.mp4":
                    return m
            return matches[0]
    return None


def draw_hud(
    frame: np.ndarray,
    source_type: str,
    source_name: str,
    width: int,
    height: int,
    current_fps: float,
    stream_fps: float,
    frame_idx: int,
    total_frames: Optional[int],
) -> np.ndarray:
    """Render a clean information HUD overlay onto the displayed frame."""
    canvas = frame.copy()
    h, w = canvas.shape[:2]

    # Semi-transparent top banner
    banner_height = 42 if h < 300 else 60
    overlay = canvas.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_height), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.75, canvas, 0.25, 0, canvas)

    # Accent indicator bar (IBVAP Green)
    cv2.rectangle(canvas, (0, 0), (w, 3), (0, 200, 100), -1)

    # Scale fonts based on frame dimensions
    font_scale = 0.38 if w < 400 else 0.52
    thickness = 1

    # Line 1: Source & Resolution
    line1 = f"IBVAP [M1] | Source: {source_type.upper()} ({source_name}) | Res: {width}x{height}"

    # Line 2: FPS & Frame Count
    if total_frames:
        line2 = f"Frame: {frame_idx}/{total_frames} | FPS: {current_fps:.1f} (Stream: {stream_fps:.1f}) | Press 'Q' to exit"
    else:
        line2 = f"Frames Read: {frame_idx} | FPS: {current_fps:.1f} | Press 'Q' to exit"

    y1 = 18 if banner_height <= 42 else 22
    y2 = 34 if banner_height <= 42 else 46

    cv2.putText(canvas, line1, (10, y1), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
    cv2.putText(canvas, line2, (10, y2), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 230, 255), thickness, cv2.LINE_AA)

    return canvas


def run_video_stream(
    source_type: str,
    source_target: str,
    max_frames: Optional[int] = None,
    headless: bool = False,
) -> int:
    """Stream and display frames using the unified VideoSource interface."""
    logger.info("Initializing VideoSource: type=%s, target=%s", source_type, source_target)

    try:
        source = VideoSource(source_type=source_type, source=source_target)
        source.open()
    except VideoSourceNotFoundError as err:
        logger.error("Video file not found: %s", err)
        return 1
    except VideoSourceOpenError as err:
        logger.error("Failed to open video source: %s", err)
        return 1
    except Exception as err:
        logger.error("Unexpected initialization error: %s", err)
        return 1

    metadata = source.get_metadata()
    logger.info(
        "Source successfully opened: %s (%dx%d @ %.2f FPS, total frames: %s)",
        metadata["source_type"],
        metadata["width"],
        metadata["height"],
        metadata["fps"],
        metadata["frame_count"] if metadata["frame_count"] is not None else "live",
    )

    window_name = f"IBVAP Video Input - Module 1 ({source.source_type.upper()})"
    if not headless:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    # Frame timing calculation
    fps = source.fps
    if fps > 0:
        delay_ms = max(1, int(1000.0 / fps))
    else:
        delay_ms = 1

    frame_count = 0
    start_time = time.time()
    last_frame_time = start_time
    calc_fps = fps if fps > 0 else 0.0

    try:
        while True:
            ret, frame = source.read()
            if not ret or frame is None:
                if source.source_type == SourceType.VIDEO.value:
                    logger.info("End of video file reached cleanly.")
                else:
                    logger.info("Stream ended or frame read terminated.")
                break

            frame_count += 1
            now = time.time()
            dt = now - last_frame_time
            last_frame_time = now
            if dt > 0:
                instant_fps = 1.0 / dt
                calc_fps = 0.9 * calc_fps + 0.1 * instant_fps if calc_fps > 0 else instant_fps

            if not headless:
                display_frame = draw_hud(
                    frame=frame,
                    source_type=source.source_type,
                    source_name=Path(str(source.source)).name if source.source_type == "video" else str(source.source),
                    width=source.width,
                    height=source.height,
                    current_fps=calc_fps,
                    stream_fps=source.fps,
                    frame_idx=source.current_frame_index,
                    total_frames=source.frame_count,
                )

                cv2.imshow(window_name, display_frame)

                # Wait for key press or delay based on stream FPS
                key = cv2.waitKey(delay_ms) & 0xFF
                if key in (ord('q'), ord('Q'), 27):  # 'q', 'Q', or ESC
                    logger.info("User requested exit ('Q' or ESC pressed).")
                    break

            if max_frames is not None and frame_count >= max_frames:
                logger.info("Reached target frame limit of %d frames.", max_frames)
                break

    finally:
        total_time = time.time() - start_time
        avg_fps = frame_count / total_time if total_time > 0 else 0.0
        logger.info(
            "Session Summary: %d frames processed in %.2fs (Avg FPS: %.2f)",
            frame_count,
            total_time,
            avg_fps,
        )

        source.release()
        if not headless:
            cv2.destroyAllWindows()
            # On some Windows OpenCV builds, a brief waitKey ensures the window closes cleanly
            cv2.waitKey(1)
        logger.info("Resources released cleanly.")

    return 0


def interactive_menu() -> Tuple[str, str]:
    """Display interactive CLI menu to prompt user for source choice."""
    print("\n" + "=" * 62)
    print("  IBVAP Module 1 — Unified Video Input Demonstration")
    print("=" * 62)
    print("  Choose video source:")
    print("    [1] Laptop Webcam (Default device 0)")
    print("    [2] Local Video File (MP4, AVI, etc.)")
    print("=" * 62)

    try:
        choice = input("Enter choice [1/2] (default: 1): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")
        sys.exit(0)

    if choice == "2":
        default_video = find_default_video(PROJECT_ROOT / "videos")
        default_str = str(default_video.relative_to(PROJECT_ROOT)) if default_video else "videos/test.mp4"

        try:
            path_input = input(f"Enter video file path (default: {default_str}): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            sys.exit(0)

        video_path = path_input if path_input else default_str
        return SourceType.VIDEO.value, video_path

    # Default to webcam
    try:
        cam_input = input("Enter webcam device index (default: 0): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")
        sys.exit(0)

    cam_idx = cam_input if cam_input else "0"
    return SourceType.WEBCAM.value, cam_idx


def main() -> None:
    """Main CLI entrypoint for Module 1 demo."""
    parser = argparse.ArgumentParser(
        description="IBVAP Module 1 - Unified Video Input Demonstration",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--source-type",
        choices=["webcam", "video", "rtsp"],
        help="Type of video source to open",
    )
    parser.add_argument(
        "--source",
        help="Camera device index (for webcam) or video file path (for video)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Maximum frames to display before automatic exit",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless mode without opening GUI window (for tests)",
    )

    args = parser.parse_args()

    if args.source_type:
        source_type = args.source_type
        if source_type == "webcam":
            source_target = args.source if args.source is not None else "0"
        elif source_type == "video":
            if args.source:
                source_target = args.source
            else:
                default_video = find_default_video(PROJECT_ROOT / "videos")
                source_target = str(default_video) if default_video else "videos/test.mp4"
        else:
            source_target = args.source or ""
    else:
        source_type, source_target = interactive_menu()

    exit_code = run_video_stream(
        source_type=source_type,
        source_target=source_target,
        max_frames=args.max_frames,
        headless=args.headless,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
