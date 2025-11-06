import asyncio

import pytest

from src.orchestrator.services import accelerator_service


@pytest.fixture
def isolated_stream(monkeypatch):
    stream = accelerator_service._ArtifactStream()
    monkeypatch.setattr(accelerator_service, "artifacts_queue", stream)
    return stream


def test_coerce_text_handles_varied_inputs():
    assert accelerator_service._coerce_text("plain") == "plain"
    assert accelerator_service._coerce_text({"text": "value"}) == "value"
    assert accelerator_service._coerce_text({"message": "msg"}) == "msg"
    assert accelerator_service._coerce_text({}) == ""
    assert accelerator_service._coerce_text(None) == ""


@pytest.mark.parametrize(
    "latest_input,expected",
    [
        ("Need a bundle zip plus HTML preview", True),
        ("bundle only", False),
        ("please send preview", False),
        ("   ", False),
    ],
)
def test_should_request_ready_bundle(latest_input, expected):
    assert accelerator_service._should_request_ready_bundle(latest_input) is expected


def test_ensure_ready_bundle_flag_sets_flag_when_needed():
    payload = {"type": "bundle"}
    updated = accelerator_service._ensure_ready_bundle_flag(payload, "ready to run bundle with ui preview")
    assert updated is payload
    assert updated["include_ready_bundle"] is True


def test_ensure_ready_bundle_flag_respects_existing_flag():
    payload = {"type": "bundle", "include_ready_bundle": False}
    updated = accelerator_service._ensure_ready_bundle_flag(payload, "bundle and preview")
    assert updated["include_ready_bundle"] is False


def test_queue_artifact_enqueues_payload(isolated_stream):
    payload = {"type": "test", "data": 123}
    accelerator_service._queue_artifact("session-1", payload)
    stored = asyncio.run(isolated_stream.get_for_session("session-1"))
    assert stored == payload


def test_extract_requirement_refs_normalizes_and_sorts():
    text = "FR-001 relates to fr-002 and nfr-7. Also Fr-001 appears twice."
    refs = accelerator_service._extract_requirement_refs(text, "fr")
    assert refs == ["FR-001", "FR-002", "FR-7"]


def test_summarize_diff_covers_cases():
    assert accelerator_service._summarize_diff(None, "new") == "Initial version"
    assert accelerator_service._summarize_diff("same", "same") == "No changes"

    previous = "\n".join(f"line {i}" for i in range(5))
    current = "\n".join(f"line {i}" for i in range(8))
    summary = accelerator_service._summarize_diff(previous, current, max_lines=3)
    assert summary.count("\n") >= 3
    assert summary.endswith("… (diff truncated)")


@pytest.mark.parametrize(
    "path,expected",
    [
        ("src/foo.py", "code"),
        ("tests/test_example.py", "test"),
        ("docs/readme.md", "summary"),
        ("config/settings.yaml", "config"),
    ],
)
def test_infer_kind_from_path(path, expected):
    assert accelerator_service._infer_kind_from_path(path) == expected


@pytest.mark.parametrize(
    "path,expected",
    [
        ("main.py", "python"),
        ("component.tsx", "typescript"),
        ("script.js", "javascript"),
        ("styles.css", "css"),
        ("diagram.yaml", "yaml"),
        ("data.json", "json"),
        ("template.html", "html"),
        ("note.md", "markdown"),
        ("binary.bin", "text"),
    ],
)
def test_infer_language_from_path(path, expected):
    assert accelerator_service._infer_language_from_path(path) == expected


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("code", "implementation"),
        ("test", "testing"),
        ("config", "governance"),
        ("summary", "analysis"),
        ("bundle", "implementation"),
        ("unknown", "unspecified"),
    ],
)
def test_compute_gate_stage(kind, expected):
    assert accelerator_service._compute_gate_stage(kind) == expected


def test_strip_json_block_removes_code_fences():
    fenced = "```json\n{\"foo\": \"bar\"}\n```"
    assert accelerator_service._strip_json_block(fenced) == '{"foo": "bar"}'


def test_parse_code_payload_handles_valid_and_invalid():
    wrapped = "```\n{\"file\": \"path\"}\n```"
    assert accelerator_service._parse_code_payload(wrapped) == {"file": "path"}
    assert accelerator_service._parse_code_payload("not json") is None


def test_fallback_code_payload_includes_context():
    result = accelerator_service._fallback_code_payload("make a scaffold")
    note = result["notes"][0]
    assert "Fallback scaffold generated" in note
    assert "make a scaffold" in note
    assert "evaluate_intake" in result["code"]["content"]


def test_artifact_stream_reset_drops_queue(isolated_stream):
    payload = {"type": "kept"}
    accelerator_service._queue_artifact("session-reset", payload)
    isolated_stream.reset("session-reset")
    assert asyncio.run(isolated_stream.get_for_session("session-reset")) is None
