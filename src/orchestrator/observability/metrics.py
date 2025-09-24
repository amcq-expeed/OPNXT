from __future__ import annotations

"""Prometheus metrics for the OPNXT FastAPI backend.

Adds an HTTP middleware that records request latency per method/path/status.
"""

import time
from typing import Callable, Awaitable

from prometheus_client import Histogram
from starlette.requests import Request
from starlette.responses import Response

# Histogram buckets chosen for web latencies (seconds)
REQUEST_LATENCY = Histogram(
    "opnxt_request_latency_seconds",
    "HTTP request latency in seconds",
    labelnames=("method", "path", "status"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
)


def sanitize_path(path: str) -> str:
    """Reduce high-cardinality paths (e.g., /projects/{id}) to a coarse label.

    This simple implementation keeps static segments only; extend as needed.
    """
    # Keep only top-level segment (e.g., /projects)
    if not path:
        return "/"
    segs = path.split("?")[0].split("/")
    if len(segs) > 1:
        return "/" + segs[1]
    return path


def metrics_middleware_factory() -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    async def middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # Avoid observing the metrics endpoint itself
        if request.url.path.startswith("/metrics"):
            return await call_next(request)
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        try:
            REQUEST_LATENCY.labels(
                method=request.method,
                path=sanitize_path(request.url.path),
                status=str(response.status_code),
            ).observe(elapsed)
        except Exception:
            # Never block the request due to metrics; fail closed
            pass
        return response

    return middleware
