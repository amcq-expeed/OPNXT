import os
from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from src.orchestrator.infrastructure.repository import get_repo
from .utils import otp_login


client = TestClient(app)


def test_get_repo_fallback_mongo(monkeypatch):
    # Switch implementation to 'mongo' which currently falls back to in-memory
    monkeypatch.setenv("OPNXT_REPO_IMPL", "mongo")
    repo = get_repo()

    # Create through API to exercise dependency path and RBAC
    headers, _ = otp_login(client, "adam.thacker@expeed.com")

    payload = {"name": "Repo Test", "description": "Fallback works"}
    r = client.post("/projects", json=payload, headers=headers)
    assert r.status_code == 201
    proj = r.json()

    # Ensure repo returns the same project
    p = repo.get(proj["project_id"])
    assert p is not None
    assert p.name == payload["name"]

    # Clean up via API
    r = client.delete(f"/projects/{proj['project_id']}", headers=headers)
    assert r.status_code == 204
