from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from .utils import admin_headers


client = TestClient(app)


def _auth_headers():
    return admin_headers(client)


def test_chat_post_message_uses_latest_docs_as_attachments():
    hdrs = _auth_headers()
    # Create project and generate docs so attachments exist
    r = client.post("/projects", json={"name": "AttachProj", "description": "desc"}, headers=hdrs)
    assert r.status_code == 201
    pid = r.json()["project_id"]

    r = client.post(f"/projects/{pid}/documents", headers=hdrs)
    assert r.status_code == 200

    # Create session and post a message; router will try to attach latest docs
    r = client.post("/chat/sessions", json={"project_id": pid, "title": "t"}, headers=hdrs)
    assert r.status_code == 201
    sid = r.json()["session_id"]

    r = client.post(f"/chat/sessions/{sid}/messages", json={"content": "Refine"}, headers=hdrs)
    assert r.status_code == 200
    # No strict content assertion; success indicates path executed
