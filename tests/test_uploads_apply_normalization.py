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
