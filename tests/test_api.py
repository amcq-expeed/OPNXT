from fastapi.testclient import TestClient

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


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "components" in data


def test_projects_flow():
    # Create project
    payload = {
        "name": "Test Project",
        "description": "Test description",
        "type": "web_application",
        "methodology": "agile",
    }
    r = client.post("/projects", json=payload, headers=_auth_headers())
    assert r.status_code == 201
    proj = r.json()
    assert proj["status"] == "initialized"
    assert proj["current_phase"] == "charter"

    # List projects
    r = client.get("/projects", headers=_auth_headers())
    assert r.status_code == 200
    items = r.json()
    assert any(p["project_id"] == proj["project_id"] for p in items)

    # Advance phase
    r = client.put(f"/projects/{proj['project_id']}/advance", headers=_auth_headers())
    assert r.status_code == 200
    proj2 = r.json()
    assert proj2["current_phase"] == "requirements"


def test_catalog_intents():
    resp = client.get("/catalog/intents", headers=_auth_headers())
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) >= 4
    first = items[0]
    for key in ("intent_id", "title", "group", "prefill_prompt"):
        assert key in first


def test_accelerator_session_flow():
    headers = _auth_headers()

    # Launch accelerator session
    launch = client.post("/accelerators/doc-generation/sessions?persona=pm", headers=headers)
    assert launch.status_code == 201
    payload = launch.json()
    session = payload["session"]
    assert session["accelerator_id"] == "doc-generation"
    assert payload["intent"]["intent_id"] == "doc-generation"
    assert payload["messages"]
    session_id = session["session_id"]

    # Post a user message; expect assistant reply is returned
    msg_resp = client.post(
        f"/accelerators/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "We're drafting a PRD."},
    )
    assert msg_resp.status_code == 201
    assistant = msg_resp.json()
    assert assistant["role"] == "assistant"
    assert assistant["content"]

    # Fetch session transcript
    transcript = client.get(f"/accelerators/sessions/{session_id}", headers=headers)
    assert transcript.status_code == 200
    history = transcript.json()
    assert len(history["messages"]) >= 2

    # Promote to project
    promote = client.post(
        f"/accelerators/sessions/{session_id}/promote",
        headers=headers,
        json={"name": "Accelerator Demo"},
    )
    assert promote.status_code == 201
    promoted = promote.json()
    assert promoted["project_id"]

    # Confirm project exists via projects API
    proj_get = client.get(f"/projects/{promoted['project_id']}", headers=headers)
    assert proj_get.status_code == 200


def test_generate_documents(tmp_path, monkeypatch):
    # Use a unique project
    payload = {
        "name": "Docs Project",
        "description": "Generate docs test",
    }
    r = client.post("/projects", json=payload, headers=_auth_headers())
    assert r.status_code == 201
    proj = r.json()

    # Trigger doc generation
    r = client.post(f"/projects/{proj['project_id']}/documents", headers=_auth_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["project_id"] == proj["project_id"]
    filenames = {a["filename"] for a in data["artifacts"]}
    # Expect our standard artifacts
    assert {"ProjectCharter.md", "SRS.md", "SDD.md", "TestPlan.md"}.issubset(filenames)

    # Delete project
    r = client.delete(f"/projects/{proj['project_id']}", headers=_auth_headers())
    assert r.status_code == 204

    # Verify deletion
    r = client.get(f"/projects/{proj['project_id']}", headers=_auth_headers())
    assert r.status_code == 404
