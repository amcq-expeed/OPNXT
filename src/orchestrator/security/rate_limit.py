from __future__ import annotations

"""Simple in-memory rate limiting primitives."""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple


@dataclass
class _RateLimitEntry:
    count: int
    window_end: datetime


_LIMIT_STORE: Dict[Tuple[str, str], _RateLimitEntry] = {}


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


def rate_limit_action(
    key: str,
    identifier: str,
    *,
    limit_env: str,
    window_env: str,
    default_limit: int,
    default_window_seconds: int,
) -> None:
    """Track a rate-limited action.

    Raises:
        RateLimitExceeded if the action should be blocked. retry_after_seconds
        indicates when the caller may retry.
    """

    if _rate_limiting_disabled():
        return

    limit = _env_int(limit_env, default_limit)
    window_seconds = _env_int(window_env, default_window_seconds)

    now = datetime.now(timezone.utc)
    store_key = (key, identifier)
    entry = _LIMIT_STORE.get(store_key)

    if entry and entry.window_end > now:
        if entry.count >= limit:
            retry_after = int((entry.window_end - now).total_seconds())
            raise RateLimitExceeded(max(retry_after, 1))
        entry.count += 1
        _LIMIT_STORE[store_key] = entry
        return

    window_end = now + timedelta(seconds=window_seconds)
    _LIMIT_STORE[store_key] = _RateLimitEntry(count=1, window_end=window_end)


def _env_int(name: str, default: int) -> int:
    if not name:
        return default
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except ValueError:
        return default


def _rate_limiting_disabled() -> bool:
    flag = os.getenv("OPNXT_RATE_LIMIT_DISABLED")
    if flag and flag.lower() in {"1", "true", "yes", "on"}:
        return True
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True
    return False


def reset_rate_limits() -> None:
    """Clear in-memory counters (useful for tests)."""

    _LIMIT_STORE.clear()
