"""Alert Engine for IBVAP AI Engine.

Module 10: Unified Alert Management and Priority Engine.

Sits downstream of Module 8 (FenceBreachDetector) and Module 9 (LoiteringDetector)
in the video analytics pipeline:

    VideoSource (M1)
        -> FramePreprocessor (M2)
        -> YOLODetector (M3)
        -> ByteTrackTracker (M4)
        -> EventMemory (M5)
        -> MovementAnalyzer (M6)
        -> ZoneManager (M7)
        -> FenceBreachDetector (M8)
        -> LoiteringDetector (M9)
        -> AlertEngine (M10)  <- this module

Objective:
    Convert detected security events from M8 and M9 into structured, immutable
    IBVAP alerts, assign deterministic severity/priority, prevent duplicate
    alert spam, maintain active alert states, and manage operator acknowledgement
    and resolution workflows.

Key Design Principles:
- Reusable Engine: Encapsulated within AlertEngine without database/API dependencies.
- Immutable Records: Alert instances are frozen dataclasses. State changes produce
  new records while preserving historical audit state.
- Duplicate Protection: Rejects duplicate events for the same underlying security
  incident using deterministic event identity and temporal deduplication keys.
- State Machine: Strict enforcement of transitions (ACTIVE -> ACKNOWLEDGED -> RESOLVED
  or ACTIVE -> RESOLVED). Invalid backwards transitions raise exceptions.
- Deterministic Priority Sorting: Prioritizes by severity (CRITICAL > HIGH > MEDIUM > LOW)
  and then by newest timestamp first.
- Context Preservation: Retains track ID, zone metadata, spatial coordinates,
  duration, and full source event information.
- Safe Lifecycle: reset() and clear() reset only M10 state without mutating M1–M9.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple, Union

logger = logging.getLogger("ibvap.ai_engine.alerts")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AlertError(Exception):
    """Base exception for all alert engine errors."""
    pass


class AlertNotFoundError(AlertError):
    """Raised when an alert with a specified ID is not found."""
    pass


class InvalidAlertStateTransitionError(AlertError):
    """Raised when an illegal alert status transition is attempted."""
    pass


class AlertValidationError(AlertError):
    """Raised when input parameters, event types, or alert configurations are invalid."""
    pass


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class AlertType(str, Enum):
    """Supported security alert event categories."""

    FENCE_BREACH = "FENCE_BREACH"
    LOITERING = "LOITERING"


class AlertSeverity(str, Enum):
    """Severity and priority level of a security alert."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @property
    def priority_rank(self) -> int:
        """Numerical priority rank for sorting (higher value = higher priority)."""
        ranks = {
            AlertSeverity.CRITICAL: 4,
            AlertSeverity.HIGH: 3,
            AlertSeverity.MEDIUM: 2,
            AlertSeverity.LOW: 1,
        }
        return ranks[self]


class AlertStatus(str, Enum):
    """Lifecycle status of an alert."""

    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


# Valid state transitions
VALID_STATUS_TRANSITIONS: Dict[AlertStatus, Set[AlertStatus]] = {
    AlertStatus.ACTIVE: {AlertStatus.ACKNOWLEDGED, AlertStatus.RESOLVED},
    AlertStatus.ACKNOWLEDGED: {AlertStatus.RESOLVED},
    AlertStatus.RESOLVED: set(),
}

# Default deterministic severity mapping policy (V1)
DEFAULT_SEVERITY_MAPPING: Dict[AlertType, AlertSeverity] = {
    AlertType.FENCE_BREACH: AlertSeverity.CRITICAL,
    AlertType.LOITERING: AlertSeverity.HIGH,
}


# ---------------------------------------------------------------------------
# Structured Immutable Alert Data Model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Alert:
    """Immutable security alert record.

    Attributes:
        alert_id: Unique identifier for the alert (e.g., 'ALT-00001').
        track_id: Persistent tracking ID of the suspect object.
        alert_type: Type of security event (AlertType.FENCE_BREACH, AlertType.LOITERING).
        severity: Severity level (CRITICAL, HIGH, MEDIUM, LOW).
        status: Current lifecycle status (ACTIVE, ACKNOWLEDGED, RESOLVED).
        timestamp: Time of alert detection in seconds (epoch or video time).
        camera_id: Identifier of the source camera sensor, if available.
        zone_id: Identifier of the associated geofence or zone, if available.
        zone_name: Descriptive name of the zone, if available.
        zone_type: Zone classification type (e.g., 'RESTRICTED', 'SENSITIVE').
        center: Spatial centroid (cx, cy) of the object at detection time.
        message: Concise human-readable notification message.
        source_event: Reference to the original source event (FenceBreachEvent, LoiteringEvent).
        metadata: Additional contextual diagnostics and attributes.
        acknowledged_at: Timestamp when the alert was acknowledged, or None.
        acknowledged_by: Optional identifier of the operator who acknowledged.
        resolved_at: Timestamp when the alert was resolved, or None.
        resolved_by: Optional identifier of the operator who resolved.
    """

    alert_id: str
    track_id: int
    alert_type: AlertType
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.ACTIVE
    timestamp: float = field(default_factory=time.time)
    camera_id: Optional[str] = None
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    zone_type: Optional[str] = None
    center: Optional[Tuple[float, float]] = None
    message: str = ""
    source_event: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    acknowledged_at: Optional[float] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[float] = None
    resolved_by: Optional[str] = None

    @property
    def is_active(self) -> bool:
        """Return True if the alert is in ACTIVE status."""
        return self.status == AlertStatus.ACTIVE

    @property
    def is_acknowledged(self) -> bool:
        """Return True if the alert is in ACKNOWLEDGED status."""
        return self.status == AlertStatus.ACKNOWLEDGED

    @property
    def is_resolved(self) -> bool:
        """Return True if the alert is in RESOLVED status."""
        return self.status == AlertStatus.RESOLVED

    @property
    def priority_rank(self) -> int:
        """Return the numerical priority ranking of this alert."""
        return self.severity.priority_rank

    def to_dict(self) -> Dict[str, Any]:
        """Serialize alert fields to a JSON-compatible dictionary."""
        return {
            "alert_id": self.alert_id,
            "track_id": self.track_id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "status": self.status.value,
            "timestamp": self.timestamp,
            "camera_id": self.camera_id,
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "zone_type": self.zone_type,
            "center": list(self.center) if self.center is not None else None,
            "message": self.message,
            "metadata": dict(self.metadata),
            "acknowledged_at": self.acknowledged_at,
            "acknowledged_by": self.acknowledged_by,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
        }


# ---------------------------------------------------------------------------
# Message Generators
# ---------------------------------------------------------------------------

def generate_fence_breach_message(
    track_id: int,
    zone_name: Optional[str] = None,
    zone_id: Optional[str] = None,
    zone_type: Optional[str] = None,
) -> str:
    """Generate a human-readable message for a fence breach alert."""
    target = zone_name or zone_id
    if target:
        return f"Track {track_id} breached virtual fence into '{target}'."
    if zone_type:
        return f"Track {track_id} entered {zone_type.lower()} perimeter."
    return f"Track {track_id} breached virtual perimeter fence."


def generate_loitering_message(
    track_id: int,
    duration_seconds: float = 0.0,
    zone_name: Optional[str] = None,
    zone_id: Optional[str] = None,
) -> str:
    """Generate a human-readable message for a loitering alert."""
    target = zone_name or zone_id
    dur_str = f"{duration_seconds:.1f}s" if duration_seconds > 0 else "prolonged duration"
    if target:
        return f"Track {track_id} loitered in '{target}' for {dur_str}."
    return f"Track {track_id} loitered for {dur_str}."


# ---------------------------------------------------------------------------
# Alert Engine
# ---------------------------------------------------------------------------

class AlertEngine:
    """Unified Alert Management Engine for IBVAP.

    Consumes security events from M8 and M9, creates structured immutable alerts,
    applies configurable severity mapping, enforces deduplication, maintains
    alert states, and provides priority sorting and state lifecycle methods.
    """

    def __init__(
        self,
        severity_mapping: Optional[Dict[AlertType, AlertSeverity]] = None,
        default_camera_id: Optional[str] = None,
        id_prefix: str = "ALT",
    ) -> None:
        """Initialize AlertEngine.

        Args:
            severity_mapping: Optional custom mapping from AlertType to AlertSeverity.
            default_camera_id: Default camera ID to assign if event does not specify one.
            id_prefix: Prefix for generated alert IDs (default: 'ALT').
        """
        self._severity_mapping = (
            dict(severity_mapping) if severity_mapping is not None else dict(DEFAULT_SEVERITY_MAPPING)
        )
        self._default_camera_id = default_camera_id
        self._id_prefix = str(id_prefix).strip() or "ALT"

        # In-memory storage: alert_id -> Alert
        self._alerts: Dict[str, Alert] = {}

        # Deduplication tracker: Set of unique event fingerprint keys
        self._processed_event_keys: Set[Any] = set()

        # Alert sequence counter
        self._counter: int = 0

    # -----------------------------------------------------------------------
    # Configuration and Policy
    # -----------------------------------------------------------------------

    @property
    def severity_mapping(self) -> Dict[AlertType, AlertSeverity]:
        """Return a copy of the active severity mapping."""
        return dict(self._severity_mapping)

    def set_severity(self, alert_type: Union[AlertType, str], severity: Union[AlertSeverity, str]) -> None:
        """Update severity mapping for a given alert type."""
        t = AlertType(alert_type)
        s = AlertSeverity(severity)
        self._severity_mapping[t] = s

    # -----------------------------------------------------------------------
    # Deduplication and ID Generation
    # -----------------------------------------------------------------------

    def _next_alert_id(self) -> str:
        """Generate a monotonically increasing unique alert ID."""
        self._counter += 1
        return f"{self._id_prefix}-{self._counter:05d}"

    def _build_fence_breach_dedup_key(self, event: Any) -> Tuple[Any, ...]:
        """Create a deterministic deduplication key for a fence breach event."""
        track_id = getattr(event, "track_id", None)
        breach_count = getattr(event, "breach_count", 1)
        fence_id = getattr(event, "fence_id", None)
        zone_id = getattr(event, "zone_id", None)
        frame_id = getattr(event, "frame_id", None)
        return (AlertType.FENCE_BREACH, track_id, breach_count, fence_id, zone_id, frame_id)

    def _build_loitering_dedup_key(self, event: Any) -> Tuple[Any, ...]:
        """Create a deterministic deduplication key for a loitering event."""
        track_id = getattr(event, "track_id", None)
        loitering_count = getattr(event, "loitering_count", 1)
        zone_id = getattr(event, "zone_id", None)
        frame_id = getattr(event, "frame_id", None)
        return (AlertType.LOITERING, track_id, loitering_count, zone_id, frame_id)

    # -----------------------------------------------------------------------
    # Event Ingestion and Conversion
    # -----------------------------------------------------------------------

    def process_fence_breach(
        self,
        event: Any,
        camera_id: Optional[str] = None,
        custom_severity: Optional[AlertSeverity] = None,
    ) -> Optional[Alert]:
        """Convert an M8 FenceBreachEvent into an Alert record.

        Args:
            event: M8 FenceBreachEvent or equivalent duck-typed object.
            camera_id: Optional camera identifier.
            custom_severity: Optional explicit severity overriding the policy.

        Returns:
            A newly created Alert, or None if the event is a duplicate.
        """
        if event is None:
            raise AlertValidationError("Event cannot be None.")

        track_id = getattr(event, "track_id", None)
        if track_id is None:
            raise AlertValidationError("Fence breach event must contain a 'track_id'.")

        # Deduplication check
        dedup_key = self._build_fence_breach_dedup_key(event)
        event_obj_id = id(event)
        if dedup_key in self._processed_event_keys or event_obj_id in self._processed_event_keys:
            logger.debug("Duplicate fence breach event ignored for track %s", track_id)
            return None

        # Determine severity
        severity = custom_severity or self._severity_mapping.get(
            AlertType.FENCE_BREACH, AlertSeverity.CRITICAL
        )

        # Extract event metadata safely
        zone_id = getattr(event, "zone_id", None) or getattr(event, "fence_id", None)
        zone_name = None
        zone_type = None
        meta = dict(getattr(event, "metadata", {}) or {})

        if "zone_name" in meta:
            zone_name = meta["zone_name"]
        if "zone_type" in meta:
            zone_type = meta["zone_type"]

        center = getattr(event, "center", None)
        if center is not None:
            center = (float(center[0]), float(center[1]))

        raw_ts = getattr(event, "timestamp", None)
        if raw_ts is None:
            ts = time.time()
        elif isinstance(raw_ts, datetime):
            ts = raw_ts.timestamp()
        else:
            ts = float(raw_ts)

        cam_id = camera_id or self._default_camera_id
        message = generate_fence_breach_message(
            track_id=track_id,
            zone_name=zone_name,
            zone_id=zone_id,
            zone_type=zone_type,
        )

        alert = Alert(
            alert_id=self._next_alert_id(),
            track_id=int(track_id),
            alert_type=AlertType.FENCE_BREACH,
            severity=severity,
            status=AlertStatus.ACTIVE,
            timestamp=ts,
            camera_id=cam_id,
            zone_id=zone_id,
            zone_name=zone_name,
            zone_type=zone_type,
            center=center,
            message=message,
            source_event=event,
            metadata={
                **meta,
                "breach_count": getattr(event, "breach_count", 1),
                "frame_id": getattr(event, "frame_id", None),
                "fence_id": getattr(event, "fence_id", None),
            },
        )

        # Register alert and mark dedup keys
        self._processed_event_keys.add(dedup_key)
        self._processed_event_keys.add(event_obj_id)
        self._alerts[alert.alert_id] = alert
        logger.info("Created alert %s (%s, Track %d)", alert.alert_id, alert.severity.value, track_id)
        return alert

    def process_loitering(
        self,
        event: Any,
        camera_id: Optional[str] = None,
        custom_severity: Optional[AlertSeverity] = None,
    ) -> Optional[Alert]:
        """Convert an M9 LoiteringEvent into an Alert record.

        Args:
            event: M9 LoiteringEvent or equivalent duck-typed object.
            camera_id: Optional camera identifier.
            custom_severity: Optional explicit severity overriding the policy.

        Returns:
            A newly created Alert, or None if the event is a duplicate.
        """
        if event is None:
            raise AlertValidationError("Event cannot be None.")

        track_id = getattr(event, "track_id", None)
        if track_id is None:
            raise AlertValidationError("Loitering event must contain a 'track_id'.")

        # Deduplication check
        dedup_key = self._build_loitering_dedup_key(event)
        event_obj_id = id(event)
        if dedup_key in self._processed_event_keys or event_obj_id in self._processed_event_keys:
            logger.debug("Duplicate loitering event ignored for track %s", track_id)
            return None

        # Determine severity
        severity = custom_severity or self._severity_mapping.get(
            AlertType.LOITERING, AlertSeverity.HIGH
        )

        # Extract event metadata safely
        zone_id = getattr(event, "zone_id", None)
        zone_name = getattr(event, "zone_name", None)
        zone_type = getattr(event, "zone_type", None)
        duration = float(getattr(event, "duration_seconds", 0.0))

        center = getattr(event, "current_center", None) or getattr(event, "anchor_center", None)
        if center is not None:
            center = (float(center[0]), float(center[1]))

        raw_ts = getattr(event, "timestamp", None)
        if raw_ts is None:
            ts = time.time()
        elif isinstance(raw_ts, datetime):
            ts = raw_ts.timestamp()
        else:
            ts = float(raw_ts)

        cam_id = camera_id or self._default_camera_id
        message = generate_loitering_message(
            track_id=track_id,
            duration_seconds=duration,
            zone_name=zone_name,
            zone_id=zone_id,
        )

        alert = Alert(
            alert_id=self._next_alert_id(),
            track_id=int(track_id),
            alert_type=AlertType.LOITERING,
            severity=severity,
            status=AlertStatus.ACTIVE,
            timestamp=ts,
            camera_id=cam_id,
            zone_id=zone_id,
            zone_name=zone_name,
            zone_type=zone_type,
            center=center,
            message=message,
            source_event=event,
            metadata={
                "duration_seconds": duration,
                "spatial_displacement": float(getattr(event, "spatial_displacement", 0.0)),
                "spatial_radius": float(getattr(event, "spatial_radius", 0.0)),
                "threshold_seconds": float(getattr(event, "threshold_seconds", 0.0)),
                "loitering_count": getattr(event, "loitering_count", 1),
                "frame_id": getattr(event, "frame_id", None),
                "anchor_center": getattr(event, "anchor_center", None),
            },
        )

        # Register alert and mark dedup keys
        self._processed_event_keys.add(dedup_key)
        self._processed_event_keys.add(event_obj_id)
        self._alerts[alert.alert_id] = alert
        logger.info("Created alert %s (%s, Track %d)", alert.alert_id, alert.severity.value, track_id)
        return alert

    def process_event(
        self,
        event: Any,
        camera_id: Optional[str] = None,
        custom_severity: Optional[AlertSeverity] = None,
    ) -> Optional[Alert]:
        """Introspect and convert an unknown event into an Alert.

        Supports FenceBreachEvent and LoiteringEvent.
        """
        if event is None:
            raise AlertValidationError("Event cannot be None.")

        # Identify event type from class or event_type attribute
        raw_type = getattr(event, "event_type", None)
        class_name = type(event).__name__

        if (
            raw_type == AlertType.FENCE_BREACH
            or raw_type == "FENCE_BREACH"
            or "FenceBreach" in class_name
            or hasattr(event, "breach_count")
        ):
            return self.process_fence_breach(event, camera_id=camera_id, custom_severity=custom_severity)

        if (
            raw_type == AlertType.LOITERING
            or raw_type == "LOITERING"
            or "Loitering" in class_name
            or hasattr(event, "duration_seconds")
        ):
            return self.process_loitering(event, camera_id=camera_id, custom_severity=custom_severity)

        raise AlertValidationError(
            f"Unsupported security event type: {raw_type or class_name} ({type(event)})"
        )

    def process_events(
        self,
        events: Sequence[Any],
        camera_id: Optional[str] = None,
    ) -> List[Alert]:
        """Process a sequence of security events and return newly created alerts.

        Duplicate events returning None are excluded from the output list.
        """
        new_alerts: List[Alert] = []
        for event in events:
            alert = self.process_event(event, camera_id=camera_id)
            if alert is not None:
                new_alerts.append(alert)
        return new_alerts

    # -----------------------------------------------------------------------
    # Alert Querying and Retrieval
    # -----------------------------------------------------------------------

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Retrieve an alert by its ID, or None if not found."""
        return self._alerts.get(alert_id)

    def get_active_alerts(
        self,
        sort_by_priority: bool = True,
        include_acknowledged: bool = False,
    ) -> List[Alert]:
        """Return active alerts, optionally sorted by priority.

        Args:
            sort_by_priority: When True, sort by severity (CRITICAL first) and then newest.
            include_acknowledged: When True, include ACKNOWLEDGED alerts alongside ACTIVE.
        """
        target_statuses = {AlertStatus.ACTIVE}
        if include_acknowledged:
            target_statuses.add(AlertStatus.ACKNOWLEDGED)

        matches = [a for a in self._alerts.values() if a.status in target_statuses]
        if sort_by_priority:
            return self._sort_alerts_by_priority(matches)
        return matches

    def get_all_alerts(self, sort_by_priority: bool = True) -> List[Alert]:
        """Return all alerts across all statuses."""
        alerts = list(self._alerts.values())
        if sort_by_priority:
            return self._sort_alerts_by_priority(alerts)
        return alerts

    def filter_alerts(
        self,
        alert_type: Optional[Union[AlertType, str]] = None,
        severity: Optional[Union[AlertSeverity, str]] = None,
        status: Optional[Union[AlertStatus, str]] = None,
        track_id: Optional[int] = None,
        zone_id: Optional[str] = None,
        camera_id: Optional[str] = None,
        sort_by_priority: bool = True,
    ) -> List[Alert]:
        """Filter alerts matching specific criteria."""
        type_filter = AlertType(alert_type) if alert_type is not None else None
        sev_filter = AlertSeverity(severity) if severity is not None else None
        status_filter = AlertStatus(status) if status is not None else None

        results = []
        for alert in self._alerts.values():
            if type_filter is not None and alert.alert_type != type_filter:
                continue
            if sev_filter is not None and alert.severity != sev_filter:
                continue
            if status_filter is not None and alert.status != status_filter:
                continue
            if track_id is not None and alert.track_id != track_id:
                continue
            if zone_id is not None and alert.zone_id != zone_id:
                continue
            if camera_id is not None and alert.camera_id != camera_id:
                continue
            results.append(alert)

        if sort_by_priority:
            return self._sort_alerts_by_priority(results)
        return results

    # -----------------------------------------------------------------------
    # State Machine: Acknowledgement and Resolution
    # -----------------------------------------------------------------------

    def acknowledge(
        self,
        alert_id: str,
        acknowledged_by: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> Alert:
        """Transition an alert from ACTIVE to ACKNOWLEDGED.

        Raises:
            AlertNotFoundError: If alert_id does not exist.
            InvalidAlertStateTransitionError: If alert is already ACKNOWLEDGED or RESOLVED.
        """
        current_alert = self.get_alert(alert_id)
        if current_alert is None:
            raise AlertNotFoundError(f"Alert with ID '{alert_id}' not found.")

        target_status = AlertStatus.ACKNOWLEDGED
        allowed = VALID_STATUS_TRANSITIONS.get(current_alert.status, set())
        if target_status not in allowed:
            raise InvalidAlertStateTransitionError(
                f"Cannot transition alert '{alert_id}' from {current_alert.status.value} to {target_status.value}."
            )

        ts = timestamp if timestamp is not None else time.time()
        updated_alert = replace(
            current_alert,
            status=target_status,
            acknowledged_at=ts,
            acknowledged_by=acknowledged_by,
        )
        self._alerts[alert_id] = updated_alert
        logger.info("Alert %s acknowledged by %s", alert_id, acknowledged_by or "operator")
        return updated_alert

    def resolve(
        self,
        alert_id: str,
        resolved_by: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> Alert:
        """Transition an alert from ACTIVE or ACKNOWLEDGED to RESOLVED.

        Raises:
            AlertNotFoundError: If alert_id does not exist.
            InvalidAlertStateTransitionError: If alert is already RESOLVED.
        """
        current_alert = self.get_alert(alert_id)
        if current_alert is None:
            raise AlertNotFoundError(f"Alert with ID '{alert_id}' not found.")

        target_status = AlertStatus.RESOLVED
        allowed = VALID_STATUS_TRANSITIONS.get(current_alert.status, set())
        if target_status not in allowed:
            raise InvalidAlertStateTransitionError(
                f"Cannot transition alert '{alert_id}' from {current_alert.status.value} to {target_status.value}."
            )

        ts = timestamp if timestamp is not None else time.time()
        updated_alert = replace(
            current_alert,
            status=target_status,
            resolved_at=ts,
            resolved_by=resolved_by,
        )
        self._alerts[alert_id] = updated_alert
        logger.info("Alert %s resolved by %s", alert_id, resolved_by or "operator")
        return updated_alert

    # -----------------------------------------------------------------------
    # Statistics and Counts
    # -----------------------------------------------------------------------

    def count_active_alerts(self, include_acknowledged: bool = False) -> int:
        """Count active alerts."""
        return len(self.get_active_alerts(sort_by_priority=False, include_acknowledged=include_acknowledged))

    def count_alerts_by_severity(self) -> Dict[AlertSeverity, int]:
        """Return counts of all alerts grouped by severity."""
        counts = {sev: 0 for sev in AlertSeverity}
        for alert in self._alerts.values():
            counts[alert.severity] += 1
        return counts

    def count_alerts_by_type(self) -> Dict[AlertType, int]:
        """Return counts of all alerts grouped by event type."""
        counts = {t: 0 for t in AlertType}
        for alert in self._alerts.values():
            counts[alert.alert_type] += 1
        return counts

    def count_alerts_by_status(self) -> Dict[AlertStatus, int]:
        """Return counts of all alerts grouped by status."""
        counts = {s: 0 for s in AlertStatus}
        for alert in self._alerts.values():
            counts[alert.status] += 1
        return counts

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def reset(self) -> AlertEngine:
        """Reset all internal state, clearing alerts and deduplication memory.

        Does NOT mutate or affect any upstream modules (M1–M9).
        """
        self._alerts.clear()
        self._processed_event_keys.clear()
        self._counter = 0
        logger.info("AlertEngine state reset.")
        return self

    def clear(self) -> AlertEngine:
        """Synonym for reset()."""
        return self.reset()

    # -----------------------------------------------------------------------
    # Sorting Utilities
    # -----------------------------------------------------------------------

    @staticmethod
    def _sort_alerts_by_priority(alerts: Sequence[Alert]) -> List[Alert]:
        """Sort alerts deterministically by priority rank (highest first), then newest first."""
        return sorted(
            alerts,
            key=lambda a: (a.severity.priority_rank, a.timestamp),
            reverse=True,
        )

    def __len__(self) -> int:
        """Return the total number of alerts recorded."""
        return len(self._alerts)

    def __repr__(self) -> str:
        return (
            f"AlertEngine(total_alerts={len(self._alerts)}, "
            f"active={self.count_active_alerts()}, "
            f"dedup_keys={len(self._processed_event_keys)})"
        )
