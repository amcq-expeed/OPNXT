from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from .utils import admin_headers, contrib_headers


client = TestClient(app)


def _admin_headers():
    return admin_headers(client)


def _contrib_headers():
    return contrib_headers(client)


def test_context_put_get_and_generation():
    # Create
    r = client.post(
        "/projects",
        json={"name": "CtxProj", "description": "Context test"},
        headers=_contrib_headers(),
    )
    assert r.status_code == 201
    proj = r.json()
    pid = proj["project_id"]

    # Put context
    payload = {
        "data": {
            "summaries": {"Planning": "Plan summary"},
            "answers": {"Requirements": ["The system SHALL support A."]},
        }
    }
    r = client.put(f"/projects/{pid}/context", json=payload, headers=_contrib_headers())
    assert r.status_code == 200

    # Get context (viewer role can read)
    r = client.get(f"/projects/{pid}/context", headers=_admin_headers())
    assert r.status_code == 200
    ctx = r.json()
    assert ctx["data"]["summaries"]["Planning"] == "Plan summary"

    # Generate docs (should succeed and merge stored context)
    r = client.post(f"/projects/{pid}/documents", headers=_contrib_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["project_id"] == pid

    # Cleanup
    r = client.delete(f"/projects/{pid}", headers=_admin_headers())
    assert r.status_code == 204


def test_impacts_endpoint_heuristic():
    # Create
    r = client.post(
        "/projects",
        json={"name": "ImpactProj", "description": "Impact test"},
        headers=_admin_headers(),
    )
    assert r.status_code == 201
    proj = r.json()
    pid = proj["project_id"]

    # Request impacts for an FR that likely exists in the traceability titles
    r = client.post(
        f"/projects/{pid}/impacts",
        json={"changed": ["FR-003", "FR-011"]},
        headers=_admin_headers(),
    )
    assert r.status_code == 200
    resp = r.json()
    assert resp["project_id"] == pid
    assert any(it["kind"] == "document" for it in resp.get("impacts", []))

    # Cleanup
    r = client.delete(f"/projects/{pid}", headers=_admin_headers())
    assert r.status_code == 204
