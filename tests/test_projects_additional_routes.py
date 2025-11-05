from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from src.orchestrator.infrastructure.doc_store import get_doc_store
from src.orchestrator.services.context_store import get_context_store
from .utils import admin_headers


client = TestClient(app)


def _auth_headers():
    return admin_headers(client)


def test_project_context_roundtrip():
    headers = _auth_headers()
    create = client.post(
        "/projects",
        json={"name": "ContextProj", "description": "Context tracking"},
        headers=headers,
    )
    assert create.status_code == 201
    pid = create.json()["project_id"]

    # Default context should be empty dict
    resp = client.get(f"/projects/{pid}/context", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"] == {}

    new_ctx = {
        "answers": {"Requirements": ["The system SHALL import data."]},
        "summaries": {"Planning": "Initial plan"},
    }
    put = client.put(
        f"/projects/{pid}/context",
        json={"data": new_ctx},
        headers=headers,
    )
    assert put.status_code == 200
    assert put.json()["data"]["answers"]["Requirements"]

    # Ensure persisted in store
    store_ctx = get_context_store().get(pid)
    assert store_ctx["answers"]["Requirements"][0].startswith("The system SHALL")


def test_impacts_endpoint_returns_deduped_items():
    headers = _auth_headers()
    create = client.post(
        "/projects",
        json={"name": "ImpactProj", "description": "Impact analysis"},
        headers=headers,
    )
    assert create.status_code == 201
    pid = create.json()["project_id"]

    resp = client.post(
        f"/projects/{pid}/impacts",
        json={"changed": ["FR-001", "FR-001"]},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == pid
    seen = {(item["kind"], item["name"]) for item in body["impacts"]}
    assert len(seen) == len(body["impacts"])


def test_document_versions_and_download_routes():
    headers = _auth_headers()
    create = client.post(
        "/projects",
        json={"name": "DocsProj", "description": "Docs"},
        headers=headers,
    )
    assert create.status_code == 201
    pid = create.json()["project_id"]

    store = get_doc_store()
    store.save_document(pid, "ProjectCharter.md", "# Charter")

    versions = client.get(f"/projects/{pid}/documents/versions", headers=headers)
    assert versions.status_code == 200
    data = versions.json()
    assert data["project_id"] == pid
    assert "ProjectCharter.md" in data["versions"]

    specific = client.get(
        f"/projects/{pid}/documents/ProjectCharter.md/versions/1",
        headers=headers,
    )
    assert specific.status_code == 200
    assert specific.json()["content"].startswith("# Charter")

    download = client.get(
        f"/projects/{pid}/documents/ProjectCharter.md/download",
        headers=headers,
    )
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/markdown")
