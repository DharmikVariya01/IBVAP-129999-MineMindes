"""Detector module for IBVAP AI Engine.

Module 3: YOLOv8n Person & Vehicle Detection.
Loads a pretrained YOLOv8n COCO model once and provides per-frame inference
filtered to person and vehicle classes only.

The detector is source-agnostic — it accepts any BGR uint8 NumPy frame
regardless of origin (webcam, MP4, RTSP).
"""

from dataclasses import dataclass
import logging
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger("ibvap.ai_engine.detector")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class DetectionError(Exception):
    """Base exception for detection errors in IBVAP AI Engine."""
    pass


class InvalidFrameError(DetectionError, ValueError):
    """Raised when an input frame does not conform to the expected BGR image spec."""
    pass


class ModelLoadError(DetectionError):
    """Raised when the YOLO model fails to load."""
    pass


# ---------------------------------------------------------------------------
# Detection result data class
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Detection:
    """A single object detection result.

    All bounding-box coordinates are in absolute pixel values relative to the
    input frame dimensions.

    Attributes:
        class_id: COCO class ID (e.g. 0 for person, 2 for car).
        class_name: Human-readable class label (e.g. 'person', 'car').
        confidence: Detection confidence score in [0.0, 1.0].
        x1: Left edge of the bounding box (pixels).
        y1: Top edge of the bounding box (pixels).
        x2: Right edge of the bounding box (pixels).
        y2: Bottom edge of the bounding box (pixels).
    """
    class_id: int
    class_name: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int


# ---------------------------------------------------------------------------
# COCO target classes for IBVAP
# ---------------------------------------------------------------------------

# Expected COCO class IDs for the object categories required by IBVAP.
# These are verified against the actual model metadata at init time.
DEFAULT_TARGET_CLASSES: Dict[int, str] = {
    0: "person",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


# ---------------------------------------------------------------------------
# YOLODetector
# ---------------------------------------------------------------------------

class YOLODetector:
    """YOLOv8n object detector for person and vehicle detection.

    Loads a pretrained YOLOv8n model once and provides efficient per-frame
    inference. Results are filtered to only the IBVAP target classes
    (person, car, motorcycle, bus, truck).

    Example::

        detector = YOLODetector(conf_threshold=0.4)
        detections = detector.detect(bgr_frame)
        for det in detections:
            print(f"{det.class_name} {det.confidence:.2f}")
    """

    DEFAULT_CONF_THRESHOLD: float = 0.35
    DEFAULT_IMGSZ: int = 640
    DEFAULT_MODEL_PATH: str = "yolov8n.pt"

    def __init__(
        self,
        model_path: str = DEFAULT_MODEL_PATH,
        conf_threshold: float = DEFAULT_CONF_THRESHOLD,
        imgsz: int = DEFAULT_IMGSZ,
        device: Optional[str] = None,
        target_classes: Optional[Dict[int, str]] = None,
    ) -> None:
        """Initialize the YOLOv8n detector.

        Args:
            model_path: Path to the YOLO model weights. Defaults to 'yolov8n.pt'
                which triggers automatic download of pretrained COCO weights if
                not already present.
            conf_threshold: Minimum confidence threshold for detections in [0.0, 1.0].
                Detections below this threshold are discarded.
            imgsz: YOLO inference image size (pixels). Larger values improve
                accuracy at the cost of speed.
            device: Compute device — 'cpu', 'cuda', 'cuda:0', etc.
                If None, auto-detects CUDA availability and falls back to CPU.
            target_classes: Dict mapping COCO class IDs to names for filtering.
                Defaults to person + vehicle classes.

        Raises:
            ValueError: If conf_threshold or imgsz are invalid.
            ModelLoadError: If the YOLO model fails to load.
        """
        # Validate parameters
        if not (0.0 <= conf_threshold <= 1.0):
            raise ValueError(
                f"conf_threshold must be between 0.0 and 1.0, got: {conf_threshold}"
            )
        if imgsz < 32:
            raise ValueError(
                f"imgsz must be at least 32 pixels, got: {imgsz}"
            )

        self._model_path = model_path
        self._conf_threshold = float(conf_threshold)
        self._imgsz = int(imgsz)
        self._target_classes = dict(target_classes or DEFAULT_TARGET_CLASSES)

        # Resolve device
        self._device = self._resolve_device(device)

        # Load model (once)
        self._model = self._load_model()

        # Verify COCO class mapping against actual model metadata
        self._verify_class_mapping()

        logger.info(
            "YOLODetector initialized: model=%s, device=%s, conf=%.2f, imgsz=%d, "
            "target_classes=%s",
            self._model_path,
            self._device,
            self._conf_threshold,
            self._imgsz,
            list(self._target_classes.values()),
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def model(self):
        """Return the underlying YOLO model instance."""
        return self._model

    @property
    def conf_threshold(self) -> float:
        """Return the current confidence threshold."""
        return self._conf_threshold

    @conf_threshold.setter
    def conf_threshold(self, value: float) -> None:
        """Set a new confidence threshold at runtime."""
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"conf_threshold must be in [0.0, 1.0], got: {value}")
        self._conf_threshold = float(value)

    @property
    def imgsz(self) -> int:
        """Return the YOLO inference image size."""
        return self._imgsz

    @property
    def device(self) -> str:
        """Return the compute device being used."""
        return self._device

    @property
    def target_classes(self) -> Dict[int, str]:
        """Return the target class mapping."""
        return dict(self._target_classes)

    @property
    def model_path(self) -> str:
        """Return the model weights path."""
        return self._model_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_device(device: Optional[str]) -> str:
        """Determine the compute device, preferring GPU if available."""
        if device is not None:
            return device.strip().lower()

        try:
            import torch
            if torch.cuda.is_available():
                logger.info("CUDA available — using GPU for inference.")
                return "cuda"
        except ImportError:
            pass

        logger.info("Using CPU for inference.")
        return "cpu"

    def _load_model(self):
        """Load the YOLO model, downloading weights if necessary.

        Returns:
            Loaded YOLO model instance.

        Raises:
            ModelLoadError: If the model fails to load.
        """
        try:
            from ultralytics import YOLO
        except ImportError as err:
            raise ModelLoadError(
                "ultralytics package is not installed. "
                "Install it with: pip install ultralytics"
            ) from err

        try:
            model = YOLO(self._model_path)
            logger.info("YOLO model loaded successfully from: %s", self._model_path)
            return model
        except Exception as err:
            raise ModelLoadError(
                f"Failed to load YOLO model from '{self._model_path}': {err}"
            ) from err

    def _verify_class_mapping(self) -> None:
        """Verify target class IDs against the actual model's COCO names.

        Logs a warning if any expected mapping does not match the model's
        metadata, but does not raise — the mismatch may be intentional.
        """
        if not hasattr(self._model, "names") or self._model.names is None:
            logger.warning(
                "Model does not expose class names metadata — "
                "cannot verify COCO class mapping."
            )
            return

        model_names = self._model.names  # dict: {int: str}
        for cid, expected_name in self._target_classes.items():
            actual_name = model_names.get(cid)
            if actual_name is None:
                logger.warning(
                    "Target class ID %d ('%s') not found in model metadata.",
                    cid,
                    expected_name,
                )
            elif actual_name.lower() != expected_name.lower():
                logger.warning(
                    "Class ID %d: expected '%s' but model reports '%s'. "
                    "Detection filtering may be inaccurate.",
                    cid,
                    expected_name,
                    actual_name,
                )
            else:
                logger.debug("Class ID %d verified: '%s'", cid, actual_name)

    # ------------------------------------------------------------------
    # Frame validation
    # ------------------------------------------------------------------

    def validate_frame(self, frame) -> None:
        """Validate that the input meets the BGR uint8 image contract.

        Args:
            frame: Object to validate.

        Raises:
            InvalidFrameError: If the input is not a valid 3-channel uint8 image.
        """
        if frame is None:
            raise InvalidFrameError("Input frame is None.")

        if not isinstance(frame, np.ndarray):
            raise InvalidFrameError(
                f"Expected numpy.ndarray, got: {type(frame).__name__}"
            )

        if frame.dtype != np.uint8:
            raise InvalidFrameError(
                f"Expected frame dtype uint8, got: {frame.dtype}"
            )

        if frame.ndim != 3:
            raise InvalidFrameError(
                f"Expected 3-dimensional array (H, W, C), got ndim={frame.ndim} "
                f"with shape {frame.shape}"
            )

        if frame.shape[2] != 3:
            raise InvalidFrameError(
                f"Expected 3 channels (BGR), got {frame.shape[2]} channels "
                f"with shape {frame.shape}"
            )

        height, width = frame.shape[:2]
        if height < 1 or width < 1:
            raise InvalidFrameError(
                f"Frame dimensions must be at least 1x1, got: {width}x{height}"
            )

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Run YOLOv8n inference on a BGR frame.

        Args:
            frame: Processed BGR NumPy frame (uint8, H×W×3) from
                FramePreprocessor or VideoSource.

        Returns:
            List of Detection objects for the target classes (person, car,
            motorcycle, bus, truck) whose confidence exceeds the threshold.

        Raises:
            InvalidFrameError: If the frame does not meet input requirements.
            DetectionError: If inference fails.
        """
        self.validate_frame(frame)

        frame_h, frame_w = frame.shape[:2]
        target_ids = set(self._target_classes.keys())

        try:
            results = self._model.predict(
                source=frame,
                conf=self._conf_threshold,
                imgsz=self._imgsz,
                device=self._device,
                classes=list(target_ids),
                verbose=False,
            )
        except Exception as err:
            raise DetectionError(f"YOLO inference failed: {err}") from err

        detections: List[Detection] = []

        if not results or len(results) == 0:
            return detections

        result = results[0]

        if result.boxes is None or len(result.boxes) == 0:
            return detections

        boxes = result.boxes

        for i in range(len(boxes)):
            cls_id = int(boxes.cls[i].item())

            # Double-check class filtering (predict already filters via classes=)
            if cls_id not in target_ids:
                continue

            conf = float(boxes.conf[i].item())

            # Get pixel coordinates (xyxy format)
            xyxy = boxes.xyxy[i]
            x1 = max(0, int(xyxy[0].item()))
            y1 = max(0, int(xyxy[1].item()))
            x2 = min(frame_w, int(xyxy[2].item()))
            y2 = min(frame_h, int(xyxy[3].item()))

            detections.append(Detection(
                class_id=cls_id,
                class_name=self._target_classes.get(cls_id, f"class_{cls_id}"),
                confidence=conf,
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
            ))

        return detections

    def __repr__(self) -> str:
        return (
            f"YOLODetector(model='{self._model_path}', device='{self._device}', "
            f"conf={self._conf_threshold:.2f}, imgsz={self._imgsz}, "
            f"classes={list(self._target_classes.values())})"
        )
