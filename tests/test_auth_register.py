from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from .utils import otp_login, _fetch_otp_from_store


client = TestClient(app)


def test_verify_otp_creates_new_user_and_returns_me():
    email = "viewer@test.com"
    name = "Viewer Test"

    # Request OTP
    r = client.post("/auth/request-otp", json={"email": email})
    assert r.status_code == 200
    code = _fetch_otp_from_store(email)
    assert code

    # Verify OTP with name to create account
    r = client.post(
        "/auth/verify-otp",
        json={"email": email, "code": code, "name": name},
    )
    assert r.status_code == 200
    token_payload = r.json()
    headers = {"Authorization": f"Bearer {token_payload['access_token']}"}

    # Call /auth/me to confirm user
    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 200
    me = r.json()
    assert me["email"].lower() == email
    assert "viewer" in (me.get("roles") or [])

    # Reuse helper for subsequent logins
    headers2, payload2 = otp_login(client, email, name=name)
    assert payload2["user"]["email"].lower() == email
    assert headers2["Authorization"].startswith("Bearer ")
