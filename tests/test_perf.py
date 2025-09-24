import os
import statistics
import time
from typing import List

from fastapi.testclient import TestClient

from src.orchestrator.api.main import app


client = TestClient(app)


def p95(values: List[float]) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = int(round(0.95 * (len(values) - 1)))
    return values[k]


def measure_get(path: str, n: int = 10) -> List[float]:
    times: List[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        r = client.get(path)
        dt = time.perf_counter() - t0
        assert r.status_code == 200
        times.append(dt)
    return times


def test_health_latency():
    times = measure_get("/health", n=10)
    p95_val = p95(times)
    # Gate only when PERF_GATE=1 to avoid CI flakiness across runners
    if os.getenv("PERF_GATE", "0") == "1":
        assert p95_val < 0.2, f"/health p95 too high: {p95_val:.3f}s"


def test_projects_basic_latency_and_doc_gen():
    # Acquire token
    r = client.post(
        "/auth/login",
        json={"email": "adam.thacker@expeed.com", "password": "Password#1"},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create project
    payload = {"name": "Perf Project", "description": "Measure timings"}
    r = client.post("/projects", json=payload, headers=headers)
    assert r.status_code == 201
    proj = r.json()

    # Measure list latency (10x)
    times = []
    for _ in range(10):
        t0 = time.perf_counter()
        rr = client.get("/projects", headers=headers)
        dt = time.perf_counter() - t0
        assert rr.status_code == 200
        times.append(dt)
    p95_list = p95(times)

    # Generate docs once and measure
    t0 = time.perf_counter()
    r = client.post(f"/projects/{proj['project_id']}/documents", headers=headers)
    dt_docs = time.perf_counter() - t0
    assert r.status_code == 200

    # Optional gates
    if os.getenv("PERF_GATE", "0") == "1":
        # Dashboard (list) target 2s p95 per requirements map
        assert p95_list < 2.0, f"/projects list p95 too high: {p95_list:.3f}s"
        # Doc gen target 10s
        assert dt_docs < 10.0, f"/documents took too long: {dt_docs:.3f}s"
