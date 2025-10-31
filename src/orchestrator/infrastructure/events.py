# --- v1.0 update ---
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

try:  # pragma: no cover - optional dependency
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    redis = None  # type: ignore


# --- v1.0 update ---
class _RedisPublisher:
    def __init__(self, url: str) -> None:
        self._url = url
        self._client = None
        self._connect()

    def _connect(self) -> None:
        if redis is None:
            return
        try:
            self._client = redis.Redis.from_url(self._url, socket_timeout=0.5)
            self._client.ping()
        except Exception:
            self._client = None

    def publish(self, channel: str, payload: Dict[str, Any]) -> None:
        if not self._client:
            self._connect()
        if not self._client:
            return
        try:
            self._client.publish(channel, json.dumps(payload))
        except Exception:
            self._client = None


# --- v1.0 update ---
_publisher: Optional[_RedisPublisher] = None


# --- v1.0 update ---
def _get_publisher() -> Optional[_RedisPublisher]:
    global _publisher
    if _publisher is not None:
        return _publisher
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    _publisher = _RedisPublisher(url)
    return _publisher


# --- v1.0 update ---
def publish_event(event_type: str, payload: Dict[str, Any]) -> None:
    publisher = _get_publisher()
    if not publisher:
        return
    channel = f"opnxt.events.{event_type}"
    publisher.publish(channel, payload)


# --- v1.0 update ---
def load_event_client() -> Optional[_RedisPublisher]:
    return _get_publisher()
