from fastapi.testclient import TestClient

from src.orchestrator.api.main import app


client = TestClient(app)


def test_login_success_and_me():
    r = client.post(
        "/auth/login",
        json={"email": "adam.thacker@expeed.com", "password": "Password#1"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "adam.thacker@expeed.com"

    token = data["access_token"]
    r2 = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    me = r2.json()
    assert me["email"] == "adam.thacker@expeed.com"


def test_login_failure_wrong_password():
    r = client.post(
        "/auth/login",
        json={"email": "adam.thacker@expeed.com", "password": "WrongPass"},
    )
    assert r.status_code == 401


def test_me_unauthorized_without_token():
    r = client.get("/auth/me")
    assert r.status_code == 401
