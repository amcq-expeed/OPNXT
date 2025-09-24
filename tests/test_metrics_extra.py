from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.orchestrator.observability import metrics


def test_sanitize_path_cases():
    assert metrics.sanitize_path("") == "/"
    assert metrics.sanitize_path("/projects/PRJ-1") == "/projects"
    assert metrics.sanitize_path("/metrics") == "/metrics"


def test_middleware_does_not_break_on_metrics_exception(monkeypatch):
    app = FastAPI()
    app.middleware("http")(metrics.metrics_middleware_factory())

    @app.get("/ok")
    def ok():
        return {"ok": True}

    class Boom:
        def labels(self, *args, **kwargs):
            raise RuntimeError("boom")

    # Force observe to raise inside middleware
    monkeypatch.setattr(metrics, "REQUEST_LATENCY", Boom())

    client = TestClient(app)
    r = client.get("/ok")
    assert r.status_code == 200
