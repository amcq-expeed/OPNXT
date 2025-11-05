import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.orchestrator.domain.accelerator_session import AcceleratorSession
from src.orchestrator.domain.chat_intents import ChatIntent
from src.orchestrator.services import accelerator_service


@pytest.fixture
def sample_intent():
    return ChatIntent(
        intent_id="design-build-guidance",
        title="Design Build Guidance",
        group="delivery",
        description="Support the team with build guidance",
        prefill_prompt="Provide build guidance",
        deliverables=["Checklist"],
        personas=["engineer"],
        guardrails=["enterprise-guardrails"],
        requirement_area="implementation",
    )


@pytest.fixture
def sample_session():
    return AcceleratorSession(
        accelerator_id="acc-1",
        session_id="sess-123",
        created_by="owner@example.com",
        created_at=datetime.now(timezone.utc).isoformat(),
        persona="engineer",
        project_id="proj-123",
        metadata={"status": "draft"},
    )


def _make_payload():
    return {
        "code": {
            "path": "src/service.py",
            "language": "python",
            "content": "print('hello world')",
        },
        "tests": {
            "path": "tests/test_service.py",
            "language": "python",
            "content": "assert True",
        },
        "config": {
            "path": "config/app.yaml",
            "language": "yaml",
            "content": "key: value",
        },
        "notes": ["note A"],
    }


def test_normalise_code_sections_handles_notes():
    sections, notes = accelerator_service._normalise_code_sections(
        {
            "code": {"path": "foo.py", "language": "python", "content": "print()"},
            "tests": {"content": "   "},
            "config": {"path": "cfg.yaml", "language": "yaml", "content": "k: v"},
            "notes": "single note",
        }
    )
    assert [section["kind"] for section in sections] == ["code", "config"]
    assert notes == ["single note"]


def test_publish_code_artifacts_generates_bundle(monkeypatch, sample_session, sample_intent):
    payload = _make_payload()

    added_artifacts = []
    saved_assets = []
    saved_previews = []
    queued = []
    recorded_metrics = []
    recorded_events = []
    updated_metadata = {}

    class StoreStub:
        def artifact_snapshot(self, session_id):
            return ([], 0)

        def add_artifact(self, session_id, **kwargs):
            added_artifacts.append((session_id, kwargs))

        def list_artifacts(self, session_id):
            return [item for _, item in added_artifacts]

        def save_asset(self, session_id, filename, data):
            saved_assets.append((session_id, filename, data))

        def get_session(self, session_id):
            return AcceleratorSession(
                accelerator_id="acc-1",
                session_id=session_id,
                created_by="owner@example.com",
                created_at=datetime.utcnow().isoformat(),
                metadata={"status": "ready"},
            )

    class DocStoreStub:
        def list_accelerator_previews(self, session_id):
            return [{"filename": "src/service.py", "content": "old"}]

        def save_accelerator_preview(self, *args, **kwargs):
            saved_previews.append((args, kwargs))

    monkeypatch.setattr(accelerator_service, "get_accelerator_store", lambda: StoreStub())
    monkeypatch.setattr(accelerator_service, "get_doc_store", lambda: DocStoreStub())
    monkeypatch.setattr(accelerator_service, "_queue_artifact", lambda sid, payload: queued.append((sid, payload)))
    monkeypatch.setattr(accelerator_service, "record_metric", lambda **kwargs: recorded_metrics.append(kwargs))
    monkeypatch.setattr(accelerator_service, "record_event", lambda event: recorded_events.append(event))
    monkeypatch.setattr(accelerator_service, "_update_session_metadata", lambda sid, meta: updated_metadata.update(meta))
    monkeypatch.setattr(accelerator_service, "_default_frontend_scaffold", lambda _title: {})
    monkeypatch.setattr(accelerator_service, "_build_ready_to_run_readme", lambda _title: "README")
    monkeypatch.setattr(accelerator_service, "_compose_capability_summary", lambda _title: "SUMMARY")
    monkeypatch.setattr(accelerator_service, "_package_ready_to_run_bundle", lambda files: b"zip-bytes")
    monkeypatch.setattr(accelerator_service, "_build_live_preview_html", lambda _title: "<html></html>")
    monkeypatch.setattr(accelerator_service, "_compose_ready_to_run_instructions", lambda: "Run it")

    accelerator_service._publish_code_artifacts(sample_session, sample_intent, payload, duration_ms=123.0)

    bundle_payloads = [payload for _, payload in queued if payload["type"] == "bundle"]
    assert bundle_payloads, "bundle artifact should be queued"
    assert any(args[0][1] == "draft.md" for args, _ in saved_previews) or saved_previews
    assert saved_assets
    assert recorded_metrics and recorded_events
    assert updated_metadata["status"] == "ready"


def test_seed_baseline_artifact_generates_draft(monkeypatch, sample_session, sample_intent):
    queued = []

    class StoreStub:
        def artifact_snapshot(self, session_id):
            return ([], 0)

        def list_messages(self, session_id):
            return [SimpleNamespace(role="user", content="Need draft"), SimpleNamespace(role="assistant", content="Working on it")]

        def add_artifact(self, *args, **kwargs):
            pass

        def get_session(self, session_id):
            return sample_session

    monkeypatch.setattr(accelerator_service, "get_accelerator_store", lambda: StoreStub())
    monkeypatch.setattr(accelerator_service, "get_doc_store", lambda: SimpleNamespace(save_accelerator_preview=lambda *args, **kwargs: None))
    monkeypatch.setattr(accelerator_service, "_queue_artifact", lambda sid, payload: queued.append(payload))

    refreshed = accelerator_service._seed_baseline_artifact(sample_session, sample_intent, "Intro text")
    assert refreshed.session_id == sample_session.session_id
    assert any(payload["type"] == "summary" for payload in queued)


def test_emit_stream_chunks(monkeypatch):
    queued = []
    monkeypatch.setattr(accelerator_service, "_queue_artifact", lambda sid, payload: queued.append(payload))
    monkeypatch.setattr(accelerator_service.time, "sleep", lambda _sec: None)

    accelerator_service._emit_stream_chunks("sess-1", "ABCDEFGH" * 20)
    assert queued, "chunks should be queued"


@pytest.mark.asyncio
async def test_stream_tokens_to_artifacts(monkeypatch):
    queued = []

    async def fake_iter_as_async(iterable):
        for item in iterable:
            yield item

    monkeypatch.setattr(accelerator_service, "iter_as_async", fake_iter_as_async)
    monkeypatch.setattr(accelerator_service, "_queue_artifact", lambda sid, payload: queued.append(payload))

    tokens = [{"token": "Hello"}, {"token": " World"}]
    text = await accelerator_service._stream_tokens_to_artifacts("sess-1", tokens)
    assert text == "Hello World"
    assert queued


@pytest.mark.asyncio
async def test_run_stream_task_under_running_loop(monkeypatch):
    async def coro():
        return "result"

    result = accelerator_service._run_stream_task(coro())
    assert result == "result"


def test_build_intro_message_includes_persona(sample_intent):
    user = SimpleNamespace(name="Alex Smith")
    text = accelerator_service._build_intro_message(sample_intent, user, "advisor")
    assert "Advisor" in text or "advisor" in text.lower()
