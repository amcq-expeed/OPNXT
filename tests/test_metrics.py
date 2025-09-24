from fastapi.testclient import TestClient

from src.orchestrator.api.main import app


client = TestClient(app)


def test_metrics_endpoint_exposes_histogram():
    # Trigger a request to ensure histogram has an observation
    r = client.get("/health")
    assert r.status_code == 200

    m = client.get("/metrics")
    assert m.status_code == 200
    body = m.text

    # Basic exposition checks
    assert "# HELP opnxt_request_latency_seconds" in body
    assert "# TYPE opnxt_request_latency_seconds histogram" in body

    # Either the base metric or _count suffix should appear depending on Prom client
    assert (
        "opnxt_request_latency_seconds_count" in body
        or "opnxt_request_latency_seconds_bucket" in body
        or "opnxt_request_latency_seconds_sum" in body
    )
