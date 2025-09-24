from fastapi.testclient import TestClient

from src.orchestrator.api.main import app


client = TestClient(app)


def test_register_then_me_and_login():
    # Register a new viewer user
    email = "viewer@test.com"
    password = "Password#1"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "name": "Viewer Test",
            "password": password,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data

    # Call /auth/me with returned token
    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 200
    me = r.json()
    assert me["email"].lower() == email
    assert "viewer" in (me.get("roles") or [])

    # Login using same credentials should work
    r = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert r.status_code == 200
    assert "access_token" in r.json()
