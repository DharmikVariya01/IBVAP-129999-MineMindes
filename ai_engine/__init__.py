"""IBVAP AI Engine Package.

Modular video analytics pipeline for intelligent border surveillance:
- video_input: Video stream acquisition and RTSP frame reading
- preprocessing: Image transformations, scaling, and color space conversions
- detector: Deep learning object detection (YOLO)
- tracker: Multi-object tracking and trajectory persistence (ByteTrack)
- event_memory: Temporal buffer and tracking memory
- movement: Direction, velocity, and trajectory calculation
- zones: Geofencing, restricted zone polygons, and boundary math
- rules: Surveillance rule evaluation (intrusion, loitering, tripwires)
- alerts: Alert creation and priority dispatching
- pipeline: End-to-end analytics pipeline orchestrator
"""

__version__ = "0.1.0"
