from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from .utils import otp_login


client = TestClient(app)


def _auth_headers():
    headers, _ = otp_login(client, "adam.thacker@expeed.com")
    return headers


def test_upload_analyze_and_apply_flow():
    # Create a project
    r = client.post(
        "/projects",
        json={"name": "UploadProj", "description": "Import CEO reqs"},
        headers=_auth_headers(),
    )
    assert r.status_code == 201
    proj = r.json()
    pid = proj["project_id"]

    # Analyze an uploaded requirements text file
    files = [
        (
            "files",
            ("ceo-reqs.txt", b"Users must be able to login; The system shall export reports", "text/plain"),
        )
    ]
    r = client.post(f"/projects/{pid}/uploads/analyze", files=files, headers=_auth_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["project_id"] == pid
    assert isinstance(data.get("items"), list)
    # At least one requirement extracted
    all_reqs = []
    for it in data["items"]:
        all_reqs.extend(it.get("requirements", []))
    assert len(all_reqs) >= 1

    # Apply extracted requirements to Stored Context
    r = client.post(
        f"/projects/{pid}/uploads/apply",
        json={"requirements": all_reqs, "category": "Requirements", "append_only": True},
        headers=_auth_headers(),
    )
    assert r.status_code == 200
    ctx = r.json()
    # Verify stored context now contains Requirements
    answers = (ctx.get("data") or {}).get("answers") or {}
    reqs = answers.get("Requirements") or []
    assert isinstance(reqs, list)
    assert len(reqs) >= 1
