from fastapi.testclient import TestClient

from src.orchestrator.api.main import app


client = TestClient(app)


def _auth_headers(email: str, password: str):
    r = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _admin_headers():
    return _auth_headers("adam.thacker@expeed.com", "Password#1")


def test_document_versions_list_and_fetch(monkeypatch):
    call_counter = {"count": 0}

    def _fake_master_prompt(*_args, **_kwargs):
        call_counter["count"] += 1
        suffix = call_counter["count"]
        return {
            "ProjectCharter.md": f"# Charter v{suffix}\n",
            "SRS.md": f"# SRS v{suffix}\nRequirement v{suffix}",
            "SDD.md": f"# SDD v{suffix}\n",
            "TestPlan.md": f"# Test Plan v{suffix}\n",
        }

    monkeypatch.setattr(
        "src.orchestrator.api.routers.projects.generate_with_master_prompt",
        _fake_master_prompt,
    )
    monkeypatch.setattr(
        "src.orchestrator.api.routers.projects.generate_backlog_with_master_prompt",
        lambda *_a, **_k: {},
    )

    from src.orchestrator.api.routers.projects import generate_with_master_prompt as patched_gen

    assert patched_gen is _fake_master_prompt

    # Create project
    r = client.post(
        "/projects",
        json={"name": "Versioned", "description": "Doc versioning"},
        headers=_admin_headers(),
    )
    assert r.status_code == 201
    proj = r.json()
    pid = proj["project_id"]

    # Generate docs v1
    r = client.post(f"/projects/{pid}/documents", headers=_admin_headers())
    assert r.status_code == 200

    # List versions
    r = client.get(f"/projects/{pid}/documents/versions", headers=_admin_headers())
    assert r.status_code == 200
    versions = r.json()
    assert versions["project_id"] == pid
    # Expect at least SRS.md
    assert any(fname == "SRS.md" for fname in versions["versions"].keys())
    srs_versions = versions["versions"].get("SRS.md", [])
    assert len(srs_versions) >= 1
    assert srs_versions[-1]["version"] >= 1

    # Fetch v1 content for SRS.md
    v1 = srs_versions[0]["version"]
    r = client.get(f"/projects/{pid}/documents/SRS.md/versions/{v1}", headers=_admin_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "SRS.md"
    assert body["version"] == v1
    assert isinstance(body["content"], str) and len(body["content"]) > 0

    # Generate docs v2
    r = client.post(f"/projects/{pid}/documents", headers=_admin_headers())
    assert r.status_code == 200

    # List versions again
    r = client.get(f"/projects/{pid}/documents/versions", headers=_admin_headers())
    assert r.status_code == 200
    versions2 = r.json()
    srs_versions2 = versions2["versions"].get("SRS.md", [])
    assert len(srs_versions2) >= 2
    latest = srs_versions2[-1]["version"]
    assert latest > v1

    # Cleanup
    r = client.delete(f"/projects/{pid}", headers=_admin_headers())
    assert r.status_code == 204
