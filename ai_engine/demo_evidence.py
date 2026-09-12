"""Standalone demonstration for IBVAP Module 11 (Evidence Capture).

Demonstrates:
1. End-to-end integration downstream of Module 10 (AlertEngine).
2. Generating valid M10 security Alerts (Fence Breach and Loitering).
3. Frame acquisition (from test video or high-fidelity synthetic surveillance feed).
4. Evidence capture via EvidenceCapture engine into verified JPG image files.
5. Inspection and printing of immutable EvidenceRecord dataclass.
6. Verification of saved image integrity (cv2.imread, resolution match, non-zero size).
7. Collision avoidance demonstration (repeated capture creates distinct files without overwrite).

Usage:
    python -m ai_engine.demo_evidence
    python run_evidence_demo.py
    python run_evidence_demo.py --output-dir evidence/demo
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from typing import Optional

import cv2
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.alerts import (
    Alert,
    AlertEngine,
    AlertSeverity,
    AlertStatus,
    AlertType,
)
from ai_engine.evidence import (
    EvidenceCapture,
    EvidenceRecord,
)
from ai_engine.fence_breach import (
    BreachEventType,
    FenceBreachEvent,
    FenceState,
)
from ai_engine.loitering import LoiteringEvent


def create_synthetic_surveillance_frame(
    width: int = 1280,
    height: int = 720,
    camera_id: str = "CAM_BORDER_01",
    timestamp_str: Optional[str] = None,
) -> np.ndarray:
    """Generate a realistic mock surveillance camera BGR frame."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)

    # Simulated terrain: dark gravel ground and night horizon
    cv2.rectangle(frame, (0, int(height * 0.4)), (width, height), (35, 45, 40), -1)
    cv2.rectangle(frame, (0, 0), (width, int(height * 0.4)), (20, 20, 25), -1)

    # Simulated virtual perimeter fence line (dashed cyan)
    fence_y = int(height * 0.55)
    for x in range(0, width, 40):
        cv2.line(frame, (x, fence_y), (x + 20, fence_y), (255, 200, 0), 2)

    # Simulated suspect bounding box & target marker
    target_box = (520, 320, 640, 560)
    cv2.rectangle(
        frame,
        (target_box[0], target_box[1]),
        (target_box[2], target_box[3]),
        (0, 0, 255),
        2,
    )
    cv2.putText(
        frame,
        "TRACK #42 [SUSPECT]",
        (target_box[0], target_box[1] - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 0, 255),
        2,
    )

    # Camera OSD (On-Screen Display) header
    ts = timestamp_str or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    osd_text = f"IBVAP LIVE | {camera_id} | {ts} | 1080p BGR"
    cv2.putText(
        frame,
        osd_text,
        (25, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2,
    )

    return frame


def acquire_frame(video_path: str = "videos/test.mp4") -> np.ndarray:
    """Acquire a video frame from test.mp4 if available, otherwise generate synthetic frame."""
    vp = Path(video_path)
    if vp.exists():
        cap = cv2.VideoCapture(str(vp))
        if cap.isOpened():
            ret, frame = cap.read()
            cap.release()
            if ret and frame is not None and frame.size > 0:
                return frame

    # Fallback to high quality synthetic frame
    return create_synthetic_surveillance_frame()


def run_demo(output_dir: str = "evidence") -> None:
    """Execute the Module 11 Evidence Capture demonstration."""
    print("\n" + "=" * 76)
    print("  IBVAP MODULE 11: EVIDENCE CAPTURE ENGINE DEMO")
    print("=" * 76)

    # 1. Initialize M10 AlertEngine
    print("\n[STEP 1] Initializing M10 AlertEngine...")
    alert_engine = AlertEngine(default_camera_id="CAM_NORTH_01")
    print("  - AlertEngine ready (Camera: CAM_NORTH_01)")

    # 2. Ingest security events into M10 to obtain real Alert objects
    print("\n[STEP 2] Generating security alerts from M8 and M9 events...")
    fence_event = FenceBreachEvent(
        track_id=42,
        event_type=BreachEventType.FENCE_BREACH,
        previous_state=FenceState.OUTSIDE,
        current_state=FenceState.INSIDE,
        frame_id=150,
        timestamp=time.time(),
        center=(580.0, 440.0),
        fence_id="FENCE_SECTOR_4",
        zone_id="ZONE_RESTRICTED_NORTH",
        breach_count=1,
        metadata={"zone_name": "Sector 4 North Wall", "zone_type": "RESTRICTED"},
    )
    alert_fence = alert_engine.process_fence_breach(fence_event)
    assert alert_fence is not None, "Failed to create M10 Fence Breach alert"
    print(f"  - Generated Alert 1: [{alert_fence.alert_id}] {alert_fence.severity.value} | {alert_fence.message}")

    loitering_event = LoiteringEvent(
        track_id=87,
        event_type="LOITERING",
        duration_seconds=45.0,
        spatial_displacement=12.5,
        spatial_radius=50.0,
        threshold_seconds=30.0,
        anchor_center=(300.0, 250.0),
        current_center=(305.0, 252.0),
        frame_id=1200,
        timestamp=time.time(),
        zone_id="ZONE_SENSITIVE_EAST",
        zone_name="East Transformer Substation",
        zone_type="SENSITIVE",
        loitering_count=1,
    )
    alert_loiter = alert_engine.process_loitering(loitering_event)
    assert alert_loiter is not None, "Failed to create M10 Loitering alert"
    print(f"  - Generated Alert 2: [{alert_loiter.alert_id}] {alert_loiter.severity.value} | {alert_loiter.message}")

    # 3. Acquire frame
    print("\n[STEP 3] Acquiring video surveillance frame...")
    frame = acquire_frame()
    h, w = frame.shape[:2]
    print(f"  - Source frame resolution: {w}x{h}, 3 channels (BGR)")

    # 4. Initialize M11 EvidenceCapture
    print(f"\n[STEP 4] Initializing EvidenceCapture (Output: {output_dir})...")
    evidence_capture = EvidenceCapture(output_dir=output_dir, jpeg_quality=95)
    print(f"  - Evidence directory resolved: {evidence_capture.output_dir}")
    print(f"  - JPEG Quality: {evidence_capture.jpeg_quality}")

    # 5. Capture Evidence for Alert 1
    print("\n[STEP 5] Capturing evidence frame for Alert 1 (FENCE_BREACH)...")
    rec1 = evidence_capture.capture(alert_fence, frame)
    print("  - Evidence Record 1 created:")
    for k, v in rec1.to_dict().items():
        print(f"      {k:18s}: {v}")

    # 6. Verify Saved Image Integrity
    print("\n[STEP 6] Verifying file on disk and decoding via cv2.imread()...")
    saved_path = Path(rec1.file_path)
    assert saved_path.exists(), "File missing on disk"
    file_size_kb = saved_path.stat().st_size / 1024.0
    print(f"  - File exists: True ({file_size_kb:.2f} KB)")

    decoded_img = cv2.imread(rec1.file_path)
    assert decoded_img is not None, "Failed to decode saved JPEG"
    assert decoded_img.shape == frame.shape, f"Dimension mismatch: {decoded_img.shape} vs {frame.shape}"
    print(f"  - Image decoded successfully: shape {decoded_img.shape} matches original frame {frame.shape}")

    # 7. Capture Evidence for Alert 2
    print("\n[STEP 7] Capturing evidence frame for Alert 2 (LOITERING)...")
    rec2 = evidence_capture.capture(alert_loiter, frame)
    print(f"  - Evidence Record 2: ID={rec2.evidence_id}, File={rec2.filename}")
    assert Path(rec2.file_path).exists()

    # 8. Demonstrate Collision-Free Repeated Capture
    print("\n[STEP 8] Demonstrating collision avoidance on repeated capture of Alert 1...")
    rec3 = evidence_capture.capture(alert_fence, frame)
    print(f"  - Re-capture Record: ID={rec3.evidence_id}, File={rec3.filename}")
    print(f"  - Different evidence ID: {rec3.evidence_id != rec1.evidence_id}")
    print(f"  - Different file path  : {rec3.file_path != rec1.file_path}")
    assert Path(rec1.file_path).exists()
    assert Path(rec3.file_path).exists()
    print("  - Both distinct evidence files safely co-exist on disk without overwrite!")

    # 9. Summary
    print("\n" + "=" * 76)
    print("  IBVAP MODULE 11: SUMMARY OF CAPTURED EVIDENCE")
    print("=" * 76)
    all_evidence = evidence_capture.list_evidence()
    print(f"  Total records captured: {len(all_evidence)}")
    print("  " + "-" * 72)
    for rec in all_evidence:
        size_kb = Path(rec.file_path).stat().st_size / 1024.0
        print(
            f"  [{rec.evidence_id}] {rec.alert_type:12s} | "
            f"Track #{rec.track_id:2d} | "
            f"{rec.width}x{rec.height} | "
            f"{size_kb:6.1f} KB | {rec.filename}"
        )
    print("=" * 76 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="IBVAP Module 11 Evidence Capture Demo")
    parser.add_argument(
        "--output-dir",
        default="evidence",
        help="Directory to store captured evidence JPEG images (default: 'evidence')",
    )
    args = parser.parse_args()
    run_demo(output_dir=args.output_dir)


if __name__ == "__main__":
    main()
