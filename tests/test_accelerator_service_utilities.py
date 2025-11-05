from datetime import datetime, timezone

import pytest

from src.orchestrator.domain.accelerator_session import AcceleratorSession
from src.orchestrator.domain.chat_intents import ChatIntent
from src.orchestrator.services import accelerator_service


@pytest.fixture
def sample_session():
    return AcceleratorSession(
        accelerator_id="acc-1",
        session_id="sess-1",
        created_by="user@example.com",
        created_at=datetime.now(timezone.utc).isoformat(),
        persona="executive",
        project_id="proj-9",
        metadata={"status": "draft"},
    )


@pytest.fixture
def sample_intent():
    return ChatIntent(
        intent_id="design-build-guidance",
        title="Design Build Guidance",
        description="Help design",
        group="delivery",
        prefill_prompt="",
        deliverables=["Checklist"],
        personas=["executive"],
        guardrails=["NFR-006"],
        requirement_area="implementation",
    )


def test_compute_and_infer_helpers_cover_paths():
    assert accelerator_service._compute_gate_stage("code") == "implementation"
    assert accelerator_service._compute_gate_stage("unknown") == "unspecified"

    assert accelerator_service._infer_kind_from_path("docs/readme.md") == "summary"
    assert accelerator_service._infer_kind_from_path("config/settings.yaml") == "config"
    assert accelerator_service._infer_kind_from_path("tests/test_service.py") == "test"
    assert accelerator_service._infer_kind_from_path("src/app.py") == "code"

    assert accelerator_service._infer_language_from_path("script.py") == "python"
    assert accelerator_service._infer_language_from_path("component.tsx") == "typescript"
    assert accelerator_service._infer_language_from_path("styles.css") == "css"
    assert accelerator_service._infer_language_from_path("unknown.bin", default="binary") == "binary"


def test_strip_and_parse_payload_variations():
    fenced = """```json\n{\n  \"code\": {\"path\": \"app.py\", \"language\": \"python\", \"content\": \"print(1)\"}\n}\n```"""
    raw = accelerator_service._strip_json_block(fenced)
    assert raw.startswith("{\n  \"code\"")

    parsed = accelerator_service._parse_code_payload(raw)
    assert parsed["code"]["path"] == "app.py"

    assert accelerator_service._parse_code_payload("not json") is None


def test_fallback_code_payload_structure():
    payload = accelerator_service._fallback_code_payload("Latest input goes here")
    sections, notes = accelerator_service._normalise_code_sections(payload)
    assert len(sections) == 3
    assert "Latest input goes here" in notes[0]


def test_compose_code_generation_prompt(sample_intent):
    excerpt = "USER: Provide more detail"
    prompt = accelerator_service._compose_code_generation_prompt(sample_intent, "Need scaffold", excerpt)
    assert "Need scaffold" in prompt
    assert accelerator_service._DEFAULT_CODE_PATH in prompt


def test_infer_persona_triggers_with_keywords():
    persona, keywords = accelerator_service._infer_persona("This roadmap needs architecture and ROI targets")
    assert persona in {"product", "architect", "executive"}
    assert any(term in {"roadmap", "architecture", "roi"} for term in keywords)


@pytest.mark.asyncio
async def test_stream_accelerator_artifacts_emits_snapshot_and_updates(monkeypatch, sample_session):
    events = []

    class StoreStub:
        def __init__(self):
            self._revision = 1
            self._artifacts = [{"filename": "foo"}]

        def artifact_snapshot(self, session_id):
            return list(self._artifacts), self._revision

    store = StoreStub()
    monkeypatch.setattr(accelerator_service, "get_accelerator_store", lambda: store)
    monkeypatch.setattr(accelerator_service, "record_metric", lambda **kwargs: None)

    # reset queue
    accelerator_service.artifacts_queue.reset(sample_session.session_id)
    accelerator_service.artifacts_queue.put_nowait(sample_session.session_id, {"type": "status", "preview": "ready"})

    generator = accelerator_service.stream_accelerator_artifacts(sample_session.session_id)
    snapshot = await generator.__anext__()
    assert snapshot["type"] == "snapshot"

    update = await generator.__anext__()
    assert update["type"] == "updates"

    await generator.aclose()


def test_schedule_code_generation_success(monkeypatch, sample_session, sample_intent):
    queued = []
    published = []
    updated_metadata = {}

    class StoreStub:
        def artifact_snapshot(self, session_id):
            return ([], 0)

        def get_session(self, session_id):
            return sample_session

        def list_artifacts(self, session_id):
            return []

    store = StoreStub()
    monkeypatch.setattr(accelerator_service, "get_accelerator_store", lambda: store)
    monkeypatch.setattr(accelerator_service, "_queue_artifact", lambda sid, art: queued.append((sid, art)))
    monkeypatch.setattr(
        accelerator_service,
        "_generate_code_payload",
        lambda session, intent, latest: {"code": {"path": "app.py", "language": "python", "content": "print('hi')"}},
    )

    def capture_update(sid, meta):
        updated_metadata.update(meta)

    monkeypatch.setattr(accelerator_service, "_update_session_metadata", capture_update)

    def fake_publish(session, intent, payload, duration_ms):
        published.append(payload)
        accelerator_service._update_session_metadata(
            session.session_id,
            {
                "status": "ready",
                "artifacts": [{"filename": payload["code"]["path"]}],
                "last_generated_at": 0.0,
            },
        )

    monkeypatch.setattr(accelerator_service, "_publish_code_artifacts", fake_publish)
    monkeypatch.setattr(accelerator_service.time, "sleep", lambda _sec: None)
    monkeypatch.setattr(accelerator_service.time, "perf_counter", lambda: 0.0)

    class ImmediateThread:
        def __init__(self, target, args=(), kwargs=None, daemon=None):
            self._target = target
            self._args = args
            self._kwargs = kwargs or {}

        def start(self):
            self._target(*self._args, **self._kwargs)

    monkeypatch.setattr(accelerator_service, "Thread", ImmediateThread)

    accelerator_service._schedule_code_generation(sample_session.session_id, sample_intent, "Latest details")

    assert any(artifact[1]["title"] == "Generating code scaffold" for artifact in queued)
    assert published and published[0]["code"]["path"] == "app.py"
    assert updated_metadata["status"] == "ready"


def test_schedule_code_generation_error_path(monkeypatch, sample_session, sample_intent):
    queued = []
    updated_metadata = {}

    class StoreStub:
        def artifact_snapshot(self, session_id):
            return ([], 0)

        def get_session(self, session_id):
            return sample_session

    store = StoreStub()
    monkeypatch.setattr(accelerator_service, "get_accelerator_store", lambda: store)
    monkeypatch.setattr(accelerator_service, "_queue_artifact", lambda sid, art: queued.append(art))
    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(accelerator_service, "_generate_code_payload", _raise)
    monkeypatch.setattr(accelerator_service, "_publish_code_artifacts", lambda *args, **kwargs: None)
    monkeypatch.setattr(accelerator_service, "_update_session_metadata", lambda sid, meta: updated_metadata.update(meta))
    monkeypatch.setattr(accelerator_service.time, "sleep", lambda _sec: None)

    class ImmediateThread:
        def __init__(self, target, args=(), kwargs=None, daemon=None):
            self._target = target
            self._args = args
            self._kwargs = kwargs or {}

        def start(self):
            self._target(*self._args, **self._kwargs)

    monkeypatch.setattr(accelerator_service, "Thread", ImmediateThread)

    accelerator_service._schedule_code_generation(sample_session.session_id, sample_intent, "Latest details")

    assert any(artifact["title"] == "Code scaffolding delayed" for artifact in queued)
    assert updated_metadata["status"] == "ready"
