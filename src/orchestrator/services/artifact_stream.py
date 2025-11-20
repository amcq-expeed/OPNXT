from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Any, Deque, Dict, Optional


class ArtifactStream:
    """Thread-safe fan-out queue keyed by stream identifier."""

    def __init__(self) -> None:
        self._queues: Dict[str, Deque[Dict[str, Any]]] = {}
        self._locks: Dict[str, Lock] = {}

    def _queue(self, stream_id: str) -> tuple[Deque[Dict[str, Any]], Lock]:
        if stream_id not in self._queues:
            self._queues[stream_id] = deque()
            self._locks[stream_id] = Lock()
        return self._queues[stream_id], self._locks[stream_id]

    def put_nowait(self, stream_id: str, payload: Dict[str, Any]) -> None:
        queue, lock = self._queue(stream_id)
        with lock:
            queue.append(payload)

    async def get_for_session(self, stream_id: str) -> Optional[Dict[str, Any]]:
        queue, lock = self._queue(stream_id)
        with lock:
            if queue:
                return queue.popleft()
        return None

    def reset(self, stream_id: str) -> None:
        self._queues.pop(stream_id, None)
        self._locks.pop(stream_id, None)


artifact_stream = ArtifactStream()


def queue_stream_event(stream_id: str, payload: Dict[str, Any]) -> None:
    """Helper to enqueue payloads with basic exception shielding."""

    try:
        artifact_stream.put_nowait(stream_id, payload)
    except Exception:  # pragma: no cover - defensive logging
        # We avoid pulling in logger here to keep this helper light; callers log.
        pass
