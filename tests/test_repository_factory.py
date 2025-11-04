import os
from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from src.orchestrator.infrastructure import repository as repository_module
from .utils import otp_login


client = TestClient(app)


def test_get_repo_fallback_mongo(monkeypatch):
    # Switch implementation to 'mongo' which currently falls back to in-memory
    monkeypatch.setenv("OPNXT_REPO_IMPL", "mongo")
    monkeypatch.setattr(repository_module, "_mongo_repo", None, raising=False)
    monkeypatch.setattr(repository_module, "_repo", repository_module.InMemoryProjectRepository())
    monkeypatch.setattr(repository_module, "_mongo_repo_cls", None, raising=False)

    repo = repository_module.get_repo()
    from src.orchestrator.infrastructure import repository_mongo

    fallback_repo = repository_module._repo
    monkeypatch.setattr(repository_mongo, "_SHARED_FALLBACK_REPO", fallback_repo, raising=False)
    if hasattr(repo, "_fallback"):
        repo._fallback = fallback_repo  # type: ignore[attr-defined]
    if hasattr(repo, "_collection"):
        repo._collection = None  # type: ignore[attr-defined]
    if hasattr(repo, "_client"):
        repo._client = None  # type: ignore[attr-defined]

    # Create through API to exercise dependency path and RBAC
    headers, _ = otp_login(client, "adam.thacker@expeed.com")

    payload = {"name": "Repo Test", "description": "Fallback works"}
    r = client.post("/projects", json=payload, headers=headers)
    assert r.status_code == 201
    proj = r.json()

    repo = repository_module.get_repo()
    projects = repo.list()
    assert any(p.project_id == proj["project_id"] for p in projects)

    fetched = repo.get(proj["project_id"])
    assert fetched is not None
    assert fetched.name == payload["name"]

    # Clean up via API
    r = client.delete(f"/projects/{proj['project_id']}", headers=headers)
    assert r.status_code == 204
