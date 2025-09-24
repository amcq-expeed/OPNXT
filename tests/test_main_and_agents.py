from fastapi.testclient import TestClient

from src.orchestrator.api.main import app


client = TestClient(app)


def _auth_headers():
    r = client.post(
        "/auth/login",
        json={
            "email": "adam.thacker@expeed.com",
            "password": "Password#1",
        },
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_main_root_endpoints():
    r = client.get("/")
    assert r.status_code == 200
    r = client.get("/api")
    assert r.status_code == 200


def test_agents_404s():
    hdrs = _auth_headers()
    r = client.get("/agents/bogus", headers=hdrs)
    assert r.status_code == 404
    r = client.put("/agents/bogus", json={"name": "x"}, headers=hdrs)
    assert r.status_code == 404
    r = client.delete("/agents/bogus", headers=hdrs)
    assert r.status_code == 404
