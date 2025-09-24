from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from src.orchestrator.infrastructure.doc_store import get_doc_store


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


def test_missing_project_routes_return_404():
    hdrs = _auth_headers()
    r = client.get("/projects/PRJ-NOPE", headers=hdrs)
    assert r.status_code == 404

    r = client.put("/projects/PRJ-NOPE/advance", headers=hdrs)
    assert r.status_code in (400, 404)

    r = client.delete("/projects/PRJ-NOPE", headers=hdrs)
    assert r.status_code == 404


def test_enrich_route_handles_exception(monkeypatch):
    hdrs = _auth_headers()
    # Create a project
    r = client.post("/projects", json={"name": "E", "description": "x"}, headers=hdrs)
    pid = r.json()["project_id"]

    from src.orchestrator.api.routers import projects as pr
    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(pr, "enrich_answers_with_ai", boom)

    r = client.post(f"/projects/{pid}/enrich", json={"prompt": "x"}, headers=hdrs)
    assert r.status_code == 500


def test_download_document_content_types():
    hdrs = _auth_headers()
    # Create project
    r = client.post("/projects", json={"name": "D", "description": "x"}, headers=hdrs)
    pid = r.json()["project_id"]

    # Save some docs directly in the store to test content types
    store = get_doc_store()
    store.save_document(pid, "data.json", "{\"a\":1}")
    store.save_document(pid, "table.csv", "a,b\n1,2")

    r = client.get(f"/projects/{pid}/documents/data.json/download", headers=hdrs)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/json")

    r = client.get(f"/projects/{pid}/documents/table.csv/download", headers=hdrs)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("text/csv")
