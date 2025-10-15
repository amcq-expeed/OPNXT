from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

_logger = logging.getLogger("opnxt.telemetry")


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
