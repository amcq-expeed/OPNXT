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


def test_chat_flow_creates_session_and_messages():
    # Create a project
    pr = client.post(
        "/projects",
        json={"name": "ChatProj", "description": "Test chat refinement"},
        headers=_auth_headers(),
    )
    assert pr.status_code == 201
    project = pr.json()

    # Create a chat session
    cr = client.post(
        "/chat/sessions",
        json={"project_id": project["project_id"], "title": "Initial Refinement"},
        headers=_auth_headers(),
    )
    assert cr.status_code == 201
    session = cr.json()

    # List sessions for the project
    ls = client.get(
        f"/chat/sessions",
        params={"project_id": project["project_id"]},
        headers=_auth_headers(),
    )
    assert ls.status_code == 200
    sessions = ls.json()
    assert any(s["session_id"] == session["session_id"] for s in sessions)

    # Post a message and expect assistant reply
    pm = client.post(
        f"/chat/sessions/{session['session_id']}/messages",
        json={"content": "User wants login with MFA and SSO."},
        headers=_auth_headers(),
    )
    assert pm.status_code == 200
    assistant_msg = pm.json()
    assert assistant_msg["role"] == "assistant"
    assert isinstance(assistant_msg["content"], str) and len(assistant_msg["content"].strip()) > 0

    # List messages should include both user and assistant
    lm = client.get(
        f"/chat/sessions/{session['session_id']}/messages",
        headers=_auth_headers(),
    )
    assert lm.status_code == 200
    msgs = lm.json()
    roles = [m["role"] for m in msgs]
    assert "user" in roles and "assistant" in roles

    # Fetch session with messages
    gs = client.get(
        f"/chat/sessions/{session['session_id']}",
        headers=_auth_headers(),
    )
    assert gs.status_code == 200
    data = gs.json()
    assert data["session"]["session_id"] == session["session_id"]
    assert isinstance(data.get("messages"), list)
