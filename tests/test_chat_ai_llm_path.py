from src.orchestrator.services import chat_ai as ca


def test_chat_ai_llm_path_truncates_attachments(monkeypatch):
    # Provide a fake API key to enable LLM branch
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("OPNXT_ENABLE_LOCAL_PROVIDER", raising=False)

    captured = {}

    class StubLLM:
        def __init__(self, *args, **kwargs):
            pass
        def invoke(self, msgs):
            captured["msgs"] = msgs
            return type("Resp", (), {"content": "OK"})()

    monkeypatch.setattr(ca, "ChatOpenAI", StubLLM)

    long_text = "a" * 13000
    out = ca.reply_with_chat_ai(
        project_name="X",
        user_message="Hello",
        history=[{"role": "user", "content": "prev"}],
        attachments={"SRS.md": long_text},
    )
    assert out == "OK"

    msgs = captured.get("msgs", [])
    # Ensure an attachments system message exists and is truncated
    sys_msgs = [m for m in msgs if m.get("role") == "system"]
    joined = "\n\n".join(m.get("content", "") for m in sys_msgs)
    assert "ATTACHED DOCUMENTS AS CONTEXT:" in joined
    assert "[truncated]" in joined
