from fastapi.testclient import TestClient
import json

from src.orchestrator.api.main import app
from .utils import admin_headers


client = TestClient(app)


def _auth_headers():
    return admin_headers(client)


def test_ai_docs_prompt_includes_structured_context_and_chat_transcript(monkeypatch):
    # 1) Create a project
    pr = client.post(
        "/projects",
        json={"name": "AI Docs Project", "description": "AI docs description"},
        headers=_auth_headers(),
    )
    assert pr.status_code == 201
    proj = pr.json()
    pid = proj["project_id"]

    # 2) Put structured context (answers/summaries)
    ctx_payload = {
        "data": {
            "answers": {
                "Requirements": [
                    "The system SHALL allow foo.",
                    "The system SHALL support bar.",
                ]
            },
            "summaries": {"Planning": "High-level planning summary."},
        }
    }
    r = client.put(f"/projects/{pid}/context", json=ctx_payload, headers=_auth_headers())
    assert r.status_code == 200

    # 3) Create a chat session and add a couple messages
    r = client.post(
        "/chat/sessions",
        json={"project_id": pid, "title": "MVP Chat"},
        headers=_auth_headers(),
    )
    assert r.status_code == 201
    session = r.json()
    sid = session["session_id"]

    r = client.post(
        f"/chat/sessions/{sid}/messages",
        json={"content": "User provides a well-structured requirement document and mentions stakeholders and constraints."},
        headers=_auth_headers(),
    )
    assert r.status_code == 200

    # 4) Stub the master prompt function to capture the prompt and return deterministic outputs
    captured = {}

    def fake_generate_with_master_prompt(project_name, input_text, doc_types=None, attachments=None):
        captured["project_name"] = project_name
        captured["input_text"] = input_text
        captured["doc_types"] = doc_types
        captured["attachments"] = attachments or {}
        return {
            "ProjectCharter.md": "# Project Charter\n",
            "SRS.md": "# SRS\n",
            "SDD.md": "# SDD\n",
            "TestPlan.md": "# Test Plan\n",
        }

    # IMPORTANT: projects.py imported the symbol directly, so patch it on the projects module
    from src.orchestrator.api.routers import projects as projects_router
    monkeypatch.setattr(projects_router, "generate_with_master_prompt", fake_generate_with_master_prompt)

    # 5) Call ai-docs
    req_body = {
        "input_text": "Seed text from UI",
        "doc_types": ["ProjectCharter", "SRS", "SDD", "TestPlan", "Backlog"],  # backlog should be ignored
        "include_backlog": False,
    }
    r = client.post(f"/projects/{pid}/ai-docs", json=req_body, headers=_auth_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["project_id"] == pid

    # 6) Validate that structured context and transcript were included in the prompt
    prompt = captured.get("input_text", "")
    assert "STRUCTURED CONTEXT (answers/summaries as JSON):" in prompt
    assert "CHAT TRANSCRIPT (latest):" in prompt
    assert "The system SHALL allow foo." in prompt

    # Note: doc_types normalization is performed inside master_prompt_ai.generate_with_master_prompt,
    # which we replaced with a fake above. Therefore we do not assert normalization here.


def test_master_prompt_normalizes_doc_types(monkeypatch):
    # Stub _get_llm so we can inspect the system prompt and avoid real API calls
    captured_msgs = {}

    class StubLLM:
        def invoke(self, msgs):
            captured_msgs["msgs"] = msgs
            # Return minimal valid JSON payload expected by the parser
            json_text = json.dumps({
                "ProjectCharter": "# Project Charter\n",
                "SRS": "# SRS\n",
                "SDD": "# SDD\n",
                "TestPlan": "# Test Plan\n",
            })
            return type("Resp", (), {"content": json_text})()

    from src.orchestrator.services import master_prompt_ai as mp
    monkeypatch.setattr(mp, "_get_llm", lambda: StubLLM())

    # Call generator with types that include Backlog and variants
    out = mp.generate_with_master_prompt(
        project_name="X",
        input_text="seed",
        doc_types=["ProjectCharter", "SRS", "SDD", "TestPlan", "Backlog", "test strategy"],
        attachments={},
    )

    # Outputs produced
    assert set(out.keys()) == {"ProjectCharter.md", "SRS.md", "SDD.md", "TestPlan.md"}

    # Inspect system prompt; ensure Backlog is not included as a guided doc type (bullet),
    # while allowing "Backlog" to appear elsewhere in the master prompt text.
    msgs = captured_msgs.get("msgs", [])
    sys = "\n\n".join([m.get("content", "") for m in msgs if m.get("role") == "system"])
    assert "- Project Charter:" in sys
    assert "- SRS:" in sys
    assert "- SDD:" in sys
    assert "- Test Plan:" in sys
    assert "- Backlog:" not in sys
