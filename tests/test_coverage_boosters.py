import os
from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from .utils import admin_headers, contrib_headers


client = TestClient(app)


def _admin_headers():
    return admin_headers(client)


def _contrib_headers():
    return contrib_headers(client)


def test_api_prefixed_health_and_metrics():
    r = client.get("/api/health")
    assert r.status_code == 200
    r = client.get("/api/metrics")
    assert r.status_code == 200


def test_auth_me_unauthorized_401():
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_projects_delete_forbidden_for_contributor():
    # Create a project as contributor
    payload = {"name": "NoDelete", "description": "Contributor project"}
    r = client.post("/projects", json=payload, headers=_contrib_headers())
    assert r.status_code == 201
    proj = r.json()

    # Try to delete as contributor (should be forbidden)
    r = client.delete(f"/projects/{proj['project_id']}", headers=_contrib_headers())
    assert r.status_code == 403

    # Cleanup as admin
    r = client.delete(f"/projects/{proj['project_id']}", headers=_admin_headers())
    assert r.status_code == 204


def test_documents_zip_and_enrich_flow(tmp_path):
    # Create project
    payload = {"name": "ZipDoc", "description": "Zip generation test"}
    r = client.post("/projects", json=payload, headers=_admin_headers())
    assert r.status_code == 201
    proj = r.json()

    # Generate docs at least once (zip handler will also generate if missing)
    r = client.post(f"/projects/{proj['project_id']}/documents", headers=_admin_headers())
    assert r.status_code == 200

    # Fetch ZIP
    r = client.get(f"/projects/{proj['project_id']}/documents.zip", headers=_admin_headers())
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/zip")

    # Enrich endpoint should respond using fallback AI
    r = client.post(
        f"/projects/{proj['project_id']}/enrich",
        json={"prompt": "Build a simple portal with auth and SSO."},
        headers=_admin_headers(),
    )
    assert r.status_code == 200
    data = r.json()
    assert "answers" in data and "summaries" in data

    # Cleanup
    r = client.delete(f"/projects/{proj['project_id']}", headers=_admin_headers())
    assert r.status_code == 204


def test_mongo_repo_fallback_via_env(monkeypatch):
    # Force repository to use MongoProjectRepository fallback
    monkeypatch.setenv("OPNXT_REPO_IMPL", "mongo")

    payload = {"name": "MongoBacked", "description": "Fallback repo test"}
    r = client.post("/projects", json=payload, headers=_admin_headers())
    assert r.status_code == 201
    proj = r.json()
    assert proj["project_id"].startswith("PRJ-")

    # List and then delete
    r = client.get("/projects", headers=_admin_headers())
    assert r.status_code == 200
    assert any(p["project_id"] == proj["project_id"] for p in r.json())

    r = client.delete(f"/projects/{proj['project_id']}", headers=_admin_headers())
    assert r.status_code == 204
