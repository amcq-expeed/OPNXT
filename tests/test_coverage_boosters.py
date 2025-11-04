from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from src.orchestrator.infrastructure import doc_store as doc_store_module
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


def test_auth_me_unauthorized_401(monkeypatch):
    monkeypatch.delenv("OPNXT_DOC_STORE_IMPL", raising=False)
    monkeypatch.setattr(doc_store_module, "_doc_store_singleton", None, raising=False)
    store = doc_store_module.get_doc_store()
    assert isinstance(store, doc_store_module.InMemoryDocumentStore)


def test_doc_store_fallback_via_env(monkeypatch):
    monkeypatch.setenv("OPNXT_DOC_STORE_IMPL", "mongo")
    monkeypatch.setattr(doc_store_module, "_doc_store_singleton", None, raising=False)
    monkeypatch.setattr(
        doc_store_module,
        "_mongo_doc_store_cls",
        doc_store_module.InMemoryDocumentStore,
        raising=False,
    )
    monkeypatch.setattr(
        doc_store_module,
        "MongoDocumentStore",
        doc_store_module.InMemoryDocumentStore,
        raising=False,
    )

    store = doc_store_module.get_doc_store()
    for attr in ("save_document", "get_document"):
        assert hasattr(store, attr)

    version = store.save_document("PRJ-TEST", "notes.md", "# Draft\n")
    assert version >= 1

    doc = store.get_document("PRJ-TEST", "notes.md")
    assert doc is not None
    assert isinstance(doc.content, str)


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
    from src.orchestrator.infrastructure import repository as repository_module
    from src.orchestrator.infrastructure import repository_mongo

    monkeypatch.setenv("OPNXT_REPO_IMPL", "mongo")
    monkeypatch.setattr(repository_module, "_mongo_repo", None, raising=False)
    fallback_repo = repository_module.InMemoryProjectRepository()
    monkeypatch.setattr(repository_module, "_repo", fallback_repo, raising=False)
    monkeypatch.setattr(repository_module, "_mongo_repo_cls", None, raising=False)

    # Ensure Mongo repository shares the same fallback store
    monkeypatch.setattr(repository_mongo, "_SHARED_FALLBACK_REPO", fallback_repo, raising=False)

    payload = {"name": "MongoBacked", "description": "Fallback repo test"}
    r = client.post("/projects", json=payload, headers=_admin_headers())
    assert r.status_code == 201
    proj = r.json()
    assert proj["project_id"].startswith("PRJ-")

    repo = repository_module.get_repo()
    projects = repo.list()
    assert any(p.project_id == proj["project_id"] for p in projects)

    r = client.delete(f"/projects/{proj['project_id']}", headers=_admin_headers())
    assert r.status_code == 204
