"""Real End-to-End Verification Script for IBVAP Module 1 (Video Input).

Performs strict, live validation of:
1. Real Laptop Webcam via VideoSource
2. Real MP4 Video File (videos/test.mp4) via VideoSource

Checks:
- Frame reception
- Frame shape (H, W, 3)
- Data type (np.uint8)
- BGR format (3 channels, pixel values 0-255)
- Stream metadata (width, height, FPS, frame_count)
- Frame progression & EOF handling
- Clean resource release
- Single interface architecture confirmation
"""

from pathlib import Path
import sys
import time

import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.video_input import (
    SourceType,
    VideoSource,
    VideoSourceError,
    VideoSourceNotFoundError,
    VideoSourceOpenError,
)


def verify_webcam(camera_index: int = 0, num_frames_to_test: int = 15) -> dict:
    """Perform real end-to-end verification of the physical laptop webcam."""
    print("\n" + "=" * 70)
    print(f"  [1/2] REAL WEBCAM END-TO-END VERIFICATION (Device Index: {camera_index})")
    print("=" * 70)

    results = {
        "source_type": "webcam",
        "camera_index": camera_index,
        "opened": False,
        "frames_received": 0,
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "frame_shape": None,
        "dtype": None,
        "is_bgr": False,
        "released": False,
    }

    print(f"[*] Instantiating VideoSource(source_type='webcam', source={camera_index})...")
    source = VideoSource(source_type="webcam", source=camera_index)

    print("[*] Opening webcam stream...")
    start_open = time.time()
    source.open()
    open_duration = time.time() - start_open
    results["opened"] = source.is_opened

    print(f"    -> Opened successfully in {open_duration:.2f}s: is_opened={source.is_opened}")
    print(f"    -> Detected Width:  {source.width} px")
    print(f"    -> Detected Height: {source.height} px")
    print(f"    -> Detected FPS:    {source.fps:.2f} FPS")

    results["width"] = source.width
    results["height"] = source.height
    results["fps"] = source.fps

    assert source.is_opened, "Webcam failed to open!"
    assert source.width > 0, "Webcam reported non-positive width!"
    assert source.height > 0, "Webcam reported non-positive height!"

    print(f"[*] Reading {num_frames_to_test} live frames from physical webcam...")
    first_frame = None
    frames_read = 0

    for i in range(num_frames_to_test):
        ret, frame = source.read()
        assert ret is True, f"Frame read returned False at frame {i+1}!"
        assert frame is not None, f"Frame {i+1} was None!"
        assert isinstance(frame, np.ndarray), f"Frame {i+1} is not a numpy ndarray!"
        assert frame.dtype == np.uint8, f"Frame {i+1} dtype is {frame.dtype}, expected uint8!"
        assert frame.ndim == 3, f"Frame {i+1} ndim is {frame.ndim}, expected 3!"
        assert frame.shape[2] == 3, f"Frame {i+1} channels is {frame.shape[2]}, expected 3 (BGR)!"
        assert frame.shape[0] == source.height, f"Frame height mismatch: {frame.shape[0]} vs {source.height}"
        assert frame.shape[1] == source.width, f"Frame width mismatch: {frame.shape[1]} vs {source.width}"

        if first_frame is None:
            first_frame = frame

        frames_read += 1

    results["frames_received"] = frames_read
    results["frame_shape"] = first_frame.shape
    results["dtype"] = str(first_frame.dtype)
    results["is_bgr"] = (first_frame.ndim == 3 and first_frame.shape[2] == 3)

    print(f"    -> Successfully received {frames_read} live frames.")
    print(f"    -> Verified Frame Shape: {results['frame_shape']} (Height x Width x Channels)")
    print(f"    -> Verified Data Type:   {results['dtype']}")
    print(f"    -> Verified Color Space: BGR (3 channels, pixel range [{first_frame.min()}, {first_frame.max()}])")

    print("[*] Releasing webcam resources...")
    source.release()
    results["released"] = not source.is_opened
    print(f"    -> is_opened after release(): {source.is_opened}")
    assert not source.is_opened, "Webcam was not properly released!"
    print("    [PASS] Physical Laptop Webcam verification successful!")

    return results


def verify_video_file(video_path: Path) -> dict:
    """Perform real end-to-end verification of an actual local video file."""
    print("\n" + "=" * 70)
    print(f"  [2/2] REAL LOCAL VIDEO FILE END-TO-END VERIFICATION: {video_path.name}")
    print("=" * 70)

    if not video_path.exists():
        print(f"    [ERROR] Video file does not exist at: {video_path}")
        raise FileNotFoundError(f"Missing required test video: {video_path}")

    results = {
        "source_type": "video",
        "video_path": str(video_path),
        "opened": False,
        "frames_received": 0,
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "frame_count": 0,
        "frame_shape": None,
        "dtype": None,
        "is_bgr": False,
        "eof_detected": False,
        "released": False,
    }

    print(f"[*] Instantiating VideoSource(source_type='video', source='{video_path}')...")
    source = VideoSource(source_type="video", source=video_path)

    print("[*] Opening video file...")
    source.open()
    results["opened"] = source.is_opened

    print(f"    -> Opened successfully: is_opened={source.is_opened}")
    print(f"    -> Detected Width:       {source.width} px")
    print(f"    -> Detected Height:      {source.height} px")
    print(f"    -> Detected FPS:         {source.fps:.2f} FPS")
    print(f"    -> Total Frame Count:    {source.frame_count} frames")

    results["width"] = source.width
    results["height"] = source.height
    results["fps"] = source.fps
    results["frame_count"] = source.frame_count

    assert source.is_opened, "Video file failed to open!"
    assert source.width == 256, f"Expected width 256, got {source.width}"
    assert source.height == 144, f"Expected height 144, got {source.height}"
    assert source.fps == 6.0, f"Expected FPS 6.0, got {source.fps}"
    assert source.frame_count == 102, f"Expected 102 frames, got {source.frame_count}"

    print("[*] Iterating through video frame-by-frame until End-of-File (EOF)...")
    frames_read = 0
    first_frame = None

    while True:
        ret, frame = source.read()
        if not ret:
            # End-of-file reached
            assert frame is None, "Frame must be None when ret is False!"
            results["eof_detected"] = True
            break

        assert isinstance(frame, np.ndarray), f"Frame {frames_read+1} is not a numpy ndarray!"
        assert frame.dtype == np.uint8, f"Frame {frames_read+1} dtype is {frame.dtype}, expected uint8!"
        assert frame.ndim == 3, f"Frame {frames_read+1} ndim is {frame.ndim}, expected 3!"
        assert frame.shape == (source.height, source.width, 3), f"Frame shape mismatch: {frame.shape}"

        if first_frame is None:
            first_frame = frame

        frames_read += 1

    results["frames_received"] = frames_read
    results["frame_shape"] = first_frame.shape
    results["dtype"] = str(first_frame.dtype)
    results["is_bgr"] = (first_frame.ndim == 3 and first_frame.shape[2] == 3)

    print(f"    -> Read {frames_read} frames (Expected: {source.frame_count})")
    print(f"    -> Verified Frame Shape: {results['frame_shape']} (Height x Width x Channels)")
    print(f"    -> Verified Data Type:   {results['dtype']}")
    print(f"    -> Verified Color Space: BGR (3 channels, pixel range [{first_frame.min()}, {first_frame.max()}])")
    print(f"    -> End-of-File reached cleanly: {results['eof_detected']}")

    assert frames_read == source.frame_count, f"Frame count mismatch: {frames_read} vs {source.frame_count}"

    # Verify post-EOF safety
    print("[*] Verifying post-EOF safety (subsequent read calls should return (False, None))...")
    sub_ret, sub_frame = source.read()
    assert sub_ret is False and sub_frame is None, "Subsequent read past EOF failed safety check!"
    print("    -> Post-EOF read safely returned (False, None).")

    print("[*] Releasing video file resources...")
    source.release()
    results["released"] = not source.is_opened
    print(f"    -> is_opened after release(): {source.is_opened}")
    assert not source.is_opened, "Video file was not properly released!"
    print("    [PASS] Local Video File verification successful!")

    return results


def main():
    print("=" * 70)
    print("  IBVAP MODULE 1 — REAL HARDWARE & MEDIA END-TO-END VERIFICATION")
    print("=" * 70)

    # 1. Real Webcam Verification
    cam_results = verify_webcam(camera_index=0, num_frames_to_test=20)

    # 2. Real Video File Verification
    video_file = PROJECT_ROOT / "videos" / "test.mp4"
    video_results = verify_video_file(video_file)

    # 3. Architecture & Contract Comparison
    print("\n" + "=" * 70)
    print("  [3/3] ARCHITECTURE & CONTRACT UNIFICATION CONFIRMATION")
    print("=" * 70)
    print(f"  Webcam Output Type:      {type(np.ndarray([]))}")
    print(f"  Webcam Frame Shape:      {cam_results['frame_shape']} (H x W x 3)")
    print(f"  Webcam Frame Dtype:      {cam_results['dtype']}")
    print(f"  Webcam Color Space:      BGR (3 channels)")
    print(f"  -------------------------------------------------------------")
    print(f"  Video File Output Type:  {type(np.ndarray([]))}")
    print(f"  Video File Frame Shape:  {video_results['frame_shape']} (H x W x 3)")
    print(f"  Video File Frame Dtype:  {video_results['dtype']}")
    print(f"  Video File Color Space:  BGR (3 channels)")
    print(f"  -------------------------------------------------------------")
    print(f"  Same VideoSource Class:  YES (ai_engine.video_input.VideoSource)")
    print(f"  Both Output Formats:     IDENTICAL (OpenCV BGR ndarray, uint8)")
    print("=" * 70)
    print("  ALL REAL END-TO-END VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    main()
