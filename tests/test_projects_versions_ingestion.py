from fastapi.testclient import TestClient
from pathlib import Path

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


def test_versions_ingestion_from_filesystem(tmp_path):
    # Create project
    r = client.post(
        "/projects",
        json={"name": "Ingest", "description": "desc"},
        headers=_auth_headers(),
    )
    assert r.status_code == 201
    pid = r.json()["project_id"]

    # Create a docs/generated/<pid>/MyDoc.md file without touching the version store
    out_dir = Path("docs") / "generated" / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "MyDoc.md").write_text("# Hello\ncontent", encoding="utf-8")

    # Call versions endpoint, expecting ingestion to occur and return versions for MyDoc.md
    r = client.get(f"/projects/{pid}/documents/versions", headers=_auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"] == pid
    assert "MyDoc.md" in body["versions"]
    assert body["versions"]["MyDoc.md"][-1]["version"] >= 1
