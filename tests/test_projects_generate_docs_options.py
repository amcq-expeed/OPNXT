from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from .utils import admin_headers


client = TestClient(app)


def _auth_headers():
    return admin_headers(client)


def test_generate_documents_with_options_and_context(monkeypatch):
    hdrs = _auth_headers()
    r = client.post("/projects", json={"name": "GD", "description": "Initial desc"}, headers=hdrs)
    assert r.status_code == 201
    pid = r.json()["project_id"]

    ctx_payload = {
        "data": {
            "answers": {"Requirements": ["The system SHALL export data."]},
            "summaries": {"Planning": "Plan summary"},
        }
    }
    r = client.put(f"/projects/{pid}/context", json=ctx_payload, headers=hdrs)
    assert r.status_code == 200

    from src.orchestrator.api.routers import projects as pr
    monkeypatch.setattr(pr, "generate_with_master_prompt", lambda *args, **kwargs: {
        "ProjectCharter.md": "# Charter",
        "SRS.md": "# SRS",
        "SDD.md": "# SDD",
        "TestPlan.md": "# TestPlan",
    })
    monkeypatch.setattr(pr, "generate_backlog_with_master_prompt", lambda *args, **kwargs: {})

    opts = {
        "traceability_overlay": True,
        "paste_requirements": "- login\n- reset password",
        "answers": {"Design": ["Use FastAPI."]},
        "summaries": {"Design": "High level design"},
        "include_backlog": False,
    }

    r = client.post(f"/projects/{pid}/documents", json=opts, headers=hdrs)
    assert r.status_code == 200
    data = r.json()
    assert data["project_id"] == pid
    names = {a["filename"] for a in data["artifacts"]}
    assert {"ProjectCharter.md", "SRS.md", "SDD.md", "TestPlan.md"}.issubset(names)
