from fastapi.testclient import TestClient

from src.orchestrator.api.main import app

client = TestClient(app)


def _auth_headers(email: str, password: str):
    r = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _admin_headers():
    return _auth_headers("adam.thacker@expeed.com", "Password#1")


def _contrib_headers():
    return _auth_headers("contrib@example.com", "Password#1")


def test_agents_crud_and_rbac():
    # List (viewer+); use admin
    r = client.get("/agents", headers=_admin_headers())
    assert r.status_code == 200
    start_count = len(r.json())

    # Create (contributor+)
    payload = {
        "name": "Router Bot",
        "description": "Routes work",
        "capabilities": ["route", "plan"],
        "endpoint_url": "http://localhost:9100/hook",
    }
    r = client.post("/agents", json=payload, headers=_contrib_headers())
    assert r.status_code == 201
    agent = r.json()
    agent_id = agent["agent_id"]

    # Get (viewer+)
    r = client.get(f"/agents/{agent_id}", headers=_admin_headers())
    assert r.status_code == 200
    assert r.json()["name"] == payload["name"]

    # Update (contributor+)
    r = client.put(
        f"/agents/{agent_id}",
        json={"status": "active"},
        headers=_contrib_headers(),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "active"

    # Delete should be forbidden for contributor
    r = client.delete(f"/agents/{agent_id}", headers=_contrib_headers())
    assert r.status_code == 403

    # Delete (admin)
    r = client.delete(f"/agents/{agent_id}", headers=_admin_headers())
    assert r.status_code == 204

    # Verify gone
    r = client.get(f"/agents/{agent_id}", headers=_admin_headers())
    assert r.status_code == 404

    # List count back to start
    r = client.get("/agents", headers=_admin_headers())
    assert r.status_code == 200
    assert len(r.json()) == start_count
