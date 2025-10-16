from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from .utils import admin_headers, contrib_headers

client = TestClient(app)


def test_agents_crud_and_rbac():
    admin = admin_headers(client)
    contrib = contrib_headers(client)

    # List (viewer+); use admin
    r = client.get("/agents", headers=admin)
    assert r.status_code == 200
    start_count = len(r.json())

    # Create (contributor+)
    payload = {
        "name": "Router Bot",
        "description": "Routes work",
        "capabilities": ["route", "plan"],
        "endpoint_url": "http://localhost:9100/hook",
    }
    r = client.post("/agents", json=payload, headers=contrib)
    assert r.status_code == 201
    agent = r.json()
    agent_id = agent["agent_id"]

    # Get (viewer+)
    r = client.get(f"/agents/{agent_id}", headers=admin)
    assert r.status_code == 200
    assert r.json()["name"] == payload["name"]

    # Update (contributor+)
    r = client.put(
        f"/agents/{agent_id}",
        json={"status": "active"},
        headers=contrib,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "active"

    # Delete should be forbidden for contributor
    r = client.delete(f"/agents/{agent_id}", headers=contrib)
    assert r.status_code == 403

    # Delete (admin)
    r = client.delete(f"/agents/{agent_id}", headers=admin)
    assert r.status_code == 204

    # Verify gone
    r = client.get(f"/agents/{agent_id}", headers=admin)
    assert r.status_code == 404

    # List count back to start
    r = client.get("/agents", headers=admin)
    assert r.status_code == 200
    assert len(r.json()) == start_count
