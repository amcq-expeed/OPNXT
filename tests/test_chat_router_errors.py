from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from .utils import admin_headers


client = TestClient(app)


def _auth_headers():
    return admin_headers(client)


def test_chat_404s_for_missing_project_and_session():
    hdrs = _auth_headers()

    # Create session under non-existent project -> 404
    r = client.post(
        "/chat/sessions",
        json={"project_id": "PRJ-DOES-NOT-EXIST", "title": "x"},
        headers=hdrs,
    )
    assert r.status_code == 404

    # List sessions for non-existent project -> 404
    r = client.get("/chat/sessions", params={"project_id": "PRJ-NOPE"}, headers=hdrs)
    assert r.status_code == 404

    # Get and list messages for non-existent session -> 404
    r = client.get("/chat/sessions/does-not-exist", headers=hdrs)
    assert r.status_code == 404

    r = client.get("/chat/sessions/does-not-exist/messages", headers=hdrs)
    assert r.status_code == 404


def test_chat_post_message_and_history_builds():
    hdrs = _auth_headers()
    # Create a project
    r = client.post("/projects", json={"name": "ChatProj", "description": "desc"}, headers=hdrs)
    assert r.status_code == 201
    pid = r.json()["project_id"]

    # Create session
    r = client.post("/chat/sessions", json={"project_id": pid, "title": "t"}, headers=hdrs)
    assert r.status_code == 201
    sid = r.json()["session_id"]

    # Post message -> assistant reply created (LLM or fallback)
    r = client.post(f"/chat/sessions/{sid}/messages", json={"content": "- login"}, headers=hdrs)
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "assistant" or body["role"] == "user"  # store behavior

    # Fetch back the session with messages
    r = client.get(f"/chat/sessions/{sid}", headers=hdrs)
    assert r.status_code == 200
    data = r.json()
    assert data["session"]["session_id"] == sid
    assert len(data["messages"]) >= 2
