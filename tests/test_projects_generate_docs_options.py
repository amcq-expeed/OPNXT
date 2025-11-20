from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from src.orchestrator.infrastructure.doc_store import get_doc_store
from src.orchestrator.services import doc_validation
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


def test_generate_documents_enforces_compliance(monkeypatch):
    hdrs = _auth_headers()
    r = client.post("/projects", json={"name": "Compliance", "description": "desc"}, headers=hdrs)
    assert r.status_code == 201
    pid = r.json()["project_id"]

    from src.orchestrator.api.routers import projects as pr

    baseline_docs = {
        fname: "\n".join(sections) + "\nBaseline"
        for fname, sections in doc_validation.REQUIRED_SECTIONS.items()
    }

    pr._get_baseline_documents.cache_clear()
    monkeypatch.setattr(pr, "generate_all_docs", lambda *args, **kwargs: baseline_docs)

    def _incomplete_docs(*args, **kwargs):
        return {fname: f"# {fname}\nLLM body" for fname in baseline_docs}

    monkeypatch.setattr(pr, "generate_with_master_prompt", _incomplete_docs)
    monkeypatch.setattr(pr, "generate_backlog_with_master_prompt", lambda *args, **kwargs: {})

    r = client.post(f"/projects/{pid}/documents", json={}, headers=hdrs)
    assert r.status_code == 200, r.text
    payload = r.json()

    doc_store = get_doc_store()
    filenames = {a["filename"] for a in payload["artifacts"]}
    assert set(baseline_docs.keys()).issubset(filenames)

    for artifact in payload["artifacts"]:
        fname = artifact["filename"]
        if fname not in baseline_docs:
            continue
        content = artifact["content"]
        assert "## LLM Draft Supplement" in content
        assert "LLM body" in content
        stored = doc_store.get_document(pid, fname)
        assert stored is not None
        assert stored.meta.get("compliance_fallback") is True
