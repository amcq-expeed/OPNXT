from src.orchestrator.services.chat_ai import reply_with_chat_ai


def test_reply_with_chat_ai_fallback(monkeypatch):
    # Ensure no keys so the LLM path is disabled and fallback is used
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    text = reply_with_chat_ai(
        project_name="Demo",
        user_message="- login\n- track sessions",
        history=[{"role": "user", "content": "hi"}],
        attachments=None,
    )
    assert "Converted to canonical SHALL requirements:" in text
    assert "The system SHALL Login." in text
    assert "The system SHALL Track sessions." in text
