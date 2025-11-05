from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from src.orchestrator.api.routers import accelerators as accel_router
from .utils import admin_headers

client = TestClient(app)


def _headers():
    return admin_headers(client)


def test_create_session_unknown_intent_returns_404(monkeypatch):
    def _raise(*args, **kwargs):
        raise ValueError("Unknown accelerator intent")

    monkeypatch.setattr(accel_router, "launch_accelerator_session", _raise)

    resp = client.post("/accelerators/nonexistent-intent/sessions", headers=_headers())
    assert resp.status_code == 404
    assert "Unknown" in resp.json()["detail"]


def test_post_message_invalid_session_returns_400(monkeypatch):
    def _raise(*args, **kwargs):
        raise ValueError("session missing")

    monkeypatch.setattr(accel_router, "post_accelerator_message", _raise)

    resp = client.post(
        "/accelerators/sessions/fake-session/messages",
        headers=_headers(),
        json={"content": "Hello"},
    )
    assert resp.status_code == 400
    assert "session" in resp.json()["detail"].lower()


def test_delete_attachment_missing_returns_404(monkeypatch):
    def _raise(*args, **kwargs):
        raise ValueError("attachment missing")

    monkeypatch.setattr(accel_router, "remove_accelerator_attachment", _raise)

    resp = client.delete(
        "/accelerators/sessions/fake-session/attachments/missing",
        headers=_headers(),
    )
    assert resp.status_code == 404


def test_raw_artifact_non_utf8_returns_415(monkeypatch):
    monkeypatch.setattr(accel_router, "get_accelerator_asset_blob", lambda *args, **kwargs: b"\xff\xfe")

    resp = client.get(
        "/accelerators/sessions/fake-session/artifacts/output.raw/raw",
        headers=_headers(),
    )
    assert resp.status_code == 415
    assert "not utf-8" in resp.json()["detail"].lower()


def test_stream_endpoint_not_found(monkeypatch):
    def _raise(*args, **kwargs):
        raise ValueError("missing session")

    monkeypatch.setattr(accel_router, "load_accelerator_context", _raise)

    resp = client.get(
        "/accelerators/sessions/fake-session/artifacts/stream",
        headers=_headers(),
    )
    assert resp.status_code == 404
    assert "missing" in resp.json()["detail"].lower()
