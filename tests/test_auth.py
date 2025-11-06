from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from .utils import otp_login, _fetch_otp_from_store


client = TestClient(app)


def test_login_success_and_me():
    headers, payload = otp_login(client, "adam.thacker@expeed.com")
    assert payload["user"]["email"].lower() == "adam.thacker@expeed.com"
    assert "admin" in payload["user"]["roles"]

    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 200
    me = r.json()
    assert me["email"].lower() == "adam.thacker@expeed.com"
    assert "admin" in (me.get("roles") or [])


def test_login_failure_wrong_code():
    r = client.post("/auth/request-otp", json={"email": "adam.thacker@expeed.com"})
    assert r.status_code == 200
    r = client.post(
        "/auth/verify-otp",
        json={"email": "adam.thacker@expeed.com", "code": "000000"},
    )
    assert r.status_code == 400
    assert "Invalid code" in r.json()["detail"]


def test_login_failure_unknown_user_without_name():
    r = client.post("/auth/request-otp", json={"email": "missing@example.com"})
    assert r.status_code == 200
    otp = _fetch_otp_from_store("missing@example.com")
    assert otp
    r = client.post(
        "/auth/verify-otp",
        json={"email": "missing@example.com", "code": otp},
    )
    assert r.status_code == 400
    assert "Name required" in r.json()["detail"]
