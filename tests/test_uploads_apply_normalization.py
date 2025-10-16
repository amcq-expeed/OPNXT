from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from .utils import otp_login


client = TestClient(app)


def _auth_headers():
    headers, _ = otp_login(client, "adam.thacker@expeed.com")
    return headers


def test_apply_upload_requirements_normalizes_shall():
    # Create project
    r = client.post(
        "/projects",
        json={"name": "ApplyNorm", "description": "desc"},
        headers=_auth_headers(),
    )
    assert r.status_code == 201
    pid = r.json()["project_id"]

    # Apply short phrases directly (bypassing analyze) to ensure canonicalization
    reqs = ["reset password", "User registration"]

    r = client.post(
        f"/projects/{pid}/uploads/apply",
        json={"requirements": reqs, "category": "Requirements"},
        headers=_auth_headers(),
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert "answers" in data
    lst = data["answers"]["Requirements"]
    assert any(s.startswith("The system SHALL ") for s in lst)
