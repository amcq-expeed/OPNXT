from fastapi.testclient import TestClient
import io
import json
import shutil

from src.orchestrator.api.main import app
from .utils import admin_headers


client = TestClient(app)


def _auth_headers():
    return admin_headers(client)


def test_ai_docs_returns_503_when_llm_unavailable(monkeypatch):
    # Create project
    r = client.post("/projects", json={"name": "AIDD", "description": "desc"}, headers=_auth_headers())
    assert r.status_code == 201
    pid = r.json()["project_id"]

    # Force master prompt to act as unavailable
    from src.orchestrator.api.routers import projects as projects_router

    def fake_gen(project_name, input_text, doc_types=None, attachments=None):
        return {}

    monkeypatch.setattr(projects_router, "generate_with_master_prompt", fake_gen)

    r = client.post(f"/projects/{pid}/ai-docs", json={"input_text": "seed"}, headers=_auth_headers())
    assert r.status_code == 503


def test_download_zip_and_docx_conversion_error(monkeypatch):
    # Create project and generate docs
    r = client.post("/projects", json={"name": "Zip", "description": "desc"}, headers=_auth_headers())
    assert r.status_code == 201
    pid = r.json()["project_id"]

    r = client.post(f"/projects/{pid}/documents", headers=_auth_headers())
    assert r.status_code == 200

    # Download zip
    r = client.get(f"/projects/{pid}/documents.zip", headers=_auth_headers())
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/zip")

    # Force pandoc missing and request DOCX conversion
    import src.orchestrator.api.routers.projects as pr
    monkeypatch.setattr(pr.shutil, "which", lambda x: None)

    r = client.get(
        f"/projects/{pid}/documents/SRS.md/docx",
        headers=_auth_headers(),
    )
    assert r.status_code == 503


def test_uploads_analyze_and_apply(tmp_path):
    # Create project
    r = client.post("/projects", json={"name": "Uploads", "description": "desc"}, headers=_auth_headers())
    assert r.status_code == 201
    pid = r.json()["project_id"]

    # Prepare a small text file in-memory
    content = b"User registration\n- reset password\n"
    files = {"files": ("reqs.txt", io.BytesIO(content), "text/plain")}

    r = client.post(
        f"/projects/{pid}/uploads/analyze",
        files=files,
        headers=_auth_headers(),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["project_id"] == pid
    assert len(data["items"]) >= 1
    reqs = data["items"][0]["requirements"]

    # Apply requirements into context
    r = client.post(
        f"/projects/{pid}/uploads/apply",
        json={"requirements": reqs, "category": "Requirements"},
        headers=_auth_headers(),
    )
    assert r.status_code == 200
    ctx = r.json()["data"]
    assert "answers" in ctx and "Requirements" in ctx["answers"]
    assert any(s.startswith("The system SHALL") for s in ctx["answers"]["Requirements"]) 
