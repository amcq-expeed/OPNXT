from __future__ import annotations

from typing import Dict, Any
from threading import RLock


class ContextStore:
    """Thread-safe in-memory context store per project.

    Replace with persistent store as part of Mongo implementation.
    """

    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, Any]] = {}
        self._lock = RLock()

    def get(self, project_id: str) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data.get(project_id, {}))

    def put(self, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._data[project_id] = dict(payload or {})
            return dict(self._data[project_id])


_store = ContextStore()


def get_context_store() -> ContextStore:
    return _store
