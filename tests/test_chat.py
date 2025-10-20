from fastapi.testclient import TestClient
from unittest.mock import patch
import os

from src.orchestrator.api.main import app
from .utils import admin_headers


client = TestClient(app)


def _auth_headers():
    return admin_headers(client)


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


def test_chat_models_endpoint_returns_catalog():
    resp = client.get("/chat/models", headers=_auth_headers())
    assert resp.status_code == 200
    models = resp.json()
    assert isinstance(models, list)
    assert any(m.get("provider") == "adaptive" for m in models)


@patch("src.orchestrator.api.routers.chat.reply_with_chat_ai", autospec=True)
def test_chat_post_message_with_override(mock_reply):
    mock_reply.return_value = "stubbed response"
    pr = client.post(
        "/projects",
        json={"name": "OverrideProj", "description": "Test override"},
        headers=_auth_headers(),
    )
    assert pr.status_code == 201
    project = pr.json()

    cr = client.post(
        "/chat/sessions",
        json={"project_id": project["project_id"], "title": "Override Session"},
        headers=_auth_headers(),
    )
    assert cr.status_code == 201
    session = cr.json()

    payload = {
        "content": "Please summarise the latest release.",
        "provider": "openai",
        "model": "gpt-4o-mini",
    }
    pm = client.post(
        f"/chat/sessions/{session['session_id']}/messages",
        json=payload,
        headers=_auth_headers(),
    )
    assert pm.status_code == 200
    mock_reply.assert_called()
    kwargs = mock_reply.call_args.kwargs
    assert kwargs.get("provider") == "openai"
    assert kwargs.get("model") == "gpt-4o-mini"


def test_guest_chat_session_flow():
    payload = {
        "title": "Quick Start Chat",
        "initial_message": "We need to validate the analytics dashboard chat experience.",
    }
    resp = client.post("/chat/guest/sessions", json=payload, headers=_auth_headers())
    assert resp.status_code == 201
    data = resp.json()
    assert data["session"]["kind"] == "guest"
    assert data["session"].get("project_id") is None
    assert isinstance(data.get("messages"), list)
    assert len(data["messages"]) >= 1  # initial user message present

    session_id = data["session"]["session_id"]
    follow_up = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "Capture readiness metrics and error states."},
        headers=_auth_headers(),
    )
    assert follow_up.status_code == 200
    assert follow_up.json()["role"] == "assistant"
