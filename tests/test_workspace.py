from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from src.orchestrator.infrastructure.chat_store import get_chat_store
from src.orchestrator.infrastructure.accelerator_store import get_accelerator_store
from src.orchestrator.infrastructure.repository import get_repo
from .utils import otp_login

client = TestClient(app)


def _auth_headers():
    headers, _ = otp_login(client, "adam.thacker@expeed.com")
    return headers


def test_workspace_summary_and_recent_chats():
    # ensure initial state
    repo = get_repo()
    projects = repo.list()

    chat_store = get_chat_store()
    accelerator_store = get_accelerator_store()

    # Fire summary endpoint
    resp = client.get("/api/workspace/summary", headers=_auth_headers())
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["projects"] == len(projects)
    assert summary["chat_sessions"] == chat_store.count_sessions()
    assert summary["accelerator_sessions"] == accelerator_store.count_sessions()

    # Add a chat session via guest API to exercise list_recent_sessions
    headers = _auth_headers()
    guest = client.post(
        "/chat/guest/sessions",
        json={"title": "Workspace Test", "initial_message": "Hello"},
        headers=headers,
    )
    assert guest.status_code == 201

    recent = client.get("/api/workspace/chats/recent", headers=headers)
    assert recent.status_code == 200
    items = recent.json()
    assert items
    assert items[0]["title"] == "Workspace Test"


def test_accelerator_store_artifact_tracking():
    store = get_accelerator_store()
    session = store.create_session("doc-generation", created_by="tester@example.com")
    store.add_artifact(session.session_id, "Doc.md", "PRJ-TEST", {"version": 1})
    # Duplicate version should not add a second entry
    store.add_artifact(session.session_id, "Doc.md", "PRJ-TEST", {"version": 1})
    artifacts = store.list_artifacts(session.session_id)
    assert len(artifacts) == 1
    # New version should append
    store.add_artifact(session.session_id, "Doc.md", "PRJ-TEST", {"version": 2})
    artifacts = store.list_artifacts(session.session_id)
    assert len(artifacts) == 2
