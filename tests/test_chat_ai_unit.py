from __future__ import annotations

from types import SimpleNamespace

from src.orchestrator.services import chat_ai


def test_detect_user_intent_troubleshooting_looks_at_history():
    history = [{"role": "assistant", "content": "Encountered an error during deploy"}]
    assert chat_ai.detect_user_intent("Need help", history) == "troubleshooting"


def test_detect_user_intent_documentation_and_fallback():
    assert chat_ai.detect_user_intent("Need an SRS outline") == "documentation"
    assert chat_ai.detect_user_intent("Tell me a story") == "idea"


def test_determine_purpose_marks_approve():
    assert chat_ai._determine_purpose(" approve ") == "governance_artifact"
    assert chat_ai._determine_purpose("hello") == "conversation"


def test_breaker_cycle(monkeypatch):
    # reset breaker globals
    monkeypatch.setattr(chat_ai, "_BREAKER_STATE", {"fails": 0, "opened_at": 0.0}, raising=False)
    monkeypatch.setattr(chat_ai, "_BREAKER_THRESHOLD", 2, raising=False)
    monkeypatch.setattr(chat_ai, "_BREAKER_COOLDOWN", 5.0, raising=False)

    clock = SimpleNamespace(current=100.0)

    def fake_time() -> float:
        return clock.current

    monkeypatch.setattr(chat_ai, "time", SimpleNamespace(time=fake_time))

    chat_ai._record_fail()
    assert not chat_ai._breaker_open()

    chat_ai._record_fail()
    assert chat_ai._breaker_open()  # breaker now open

    clock.current += 10.0  # advance past cooldown
    assert not chat_ai._breaker_open()  # resets after cooldown

    # Once reset, a success should zero out counters
    chat_ai._record_fail()
    chat_ai._record_success()
    assert chat_ai._BREAKER_STATE["fails"] == 0
    assert not chat_ai._breaker_open()


def test_messages_to_prompt_orders_roles():
    prompt = chat_ai.LocalLLMClient._messages_to_prompt(
        [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hi"},
        ]
    )
    assert prompt.splitlines()[0] == "SYSTEM: You are helpful"
    assert prompt.endswith("ASSISTANT:")


def test_attachment_block_skips_empty_entries():
    block = chat_ai._attachment_block({"empty.txt": "  ", "brief.md": "Content"})
    assert "empty.txt" not in block
    assert "brief.md" in block


def test_diagnose_gaps_identifies_missing_sections():
    text = "Stakeholder update covers objectives but lacks risk or nfr references."
    gaps = chat_ai._diagnose_gaps(text)
    assert set(gaps) == {
        "interfaces (UI/API/integrations)",
        "testing/acceptance criteria",
        "data model/retention",
    }

    # Provide comprehensive text to clear gaps
    full_text = (
        "Stakeholder review highlights objectives, KPIs, risk mitigation, UI layout, API contract, "
        "testing strategy, and data model retention while addressing performance NFRs."
    )
    assert chat_ai._diagnose_gaps(full_text) == []
