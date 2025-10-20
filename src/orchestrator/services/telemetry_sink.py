from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_logger = logging.getLogger("opnxt.telemetry")
_metric_logger = logging.getLogger("opnxt.metrics")


@dataclass
class TelemetryEvent:
    name: str
    properties: Dict[str, Any] = field(default_factory=dict)
    actor: str | None = None


# Keep a rolling buffer of recent events for diagnostics (best-effort only)
_RECENT_EVENTS: List[TelemetryEvent] = []
_MAX_BUFFER = 200


def record_event(event: TelemetryEvent) -> None:
    """Persist a telemetry event by logging and storing in an in-memory buffer."""

    _RECENT_EVENTS.append(event)
    if len(_RECENT_EVENTS) > _MAX_BUFFER:
        del _RECENT_EVENTS[0 : len(_RECENT_EVENTS) - _MAX_BUFFER]

    try:
        _logger.info(
            "telemetry_event",
            extra={
                "telemetry_name": event.name,
                "telemetry_actor": event.actor,
                "telemetry_properties": event.properties,
            },
        )
    except Exception:
        # Logging failures should not surface to callers
        pass


def list_recent_events(limit: int = 50) -> List[TelemetryEvent]:
    if limit <= 0:
        return []
    return list(_RECENT_EVENTS[-limit:])


def record_metric(
    *,
    name: str,
    value: float,
    properties: Optional[Dict[str, Any]] = None,
    metric_type: str = "gauge",
) -> None:
    """Emit a telemetry metric.

    Parameters
    ----------
    name: str
        Metric identifier (snake_case preferred).
    value: float
        Numeric gauge/counter value.
    properties: dict[str, Any] | None
        Additional dimensions (e.g., intent_id, session_id).
    metric_type: str
        "gauge" (default), "counter", or "gauge_delta" for +/- adjustments.
    """

    payload = {
        "metric_name": name,
        "metric_value": value,
        "metric_properties": dict(properties or {}),
        "metric_type": metric_type,
    }

    try:
        _metric_logger.info("metric_event", extra=payload)
    except Exception:
        pass
