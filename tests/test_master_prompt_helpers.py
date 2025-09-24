from src.orchestrator.services import master_prompt_ai as mp


def test_is_placeholder_key_variants():
    assert mp._is_placeholder_key(None) is True
    assert mp._is_placeholder_key(" ") is True
    for k in ["__REDACTED__", "__REPLACE_WITH_YOUR_KEY__", "changeme", "change-me-in-dev", "your_api_key_here", "placeholder"]:
        assert mp._is_placeholder_key(k) is True
    assert mp._is_placeholder_key("real-key") is False


def test_extract_json_fallback():
    txt = "prefix {\n \"a\": 1\n} suffix"
    data = mp._extract_json(txt)
    assert data["a"] == 1


def test_generate_with_master_prompt_fallback_when_no_llm(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    # Force no LLM
    monkeypatch.setattr(mp, "ChatOpenAI", None)
    out = mp.generate_with_master_prompt("X", "seed", doc_types=["Backlog"])  # backlog ignored
    assert out == {}


def test_generate_with_master_prompt_success(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    class StubLLM:
        def __init__(self, *a, **k):
            pass
        def invoke(self, msgs):
            # Return doc json
            return type("R", (), {"content": "{\n  \"ProjectCharter\": \"# C\", \n \"SRS\": \"# S\", \n \"SDD\": \"# D\", \n \"TestPlan\": \"# T\"\n}"})()

    monkeypatch.setattr(mp, "ChatOpenAI", StubLLM)
    # Reduce dependency on big prompt file
    monkeypatch.setattr(mp, "_load_master_prompt", lambda: "PROMPT")

    out = mp.generate_with_master_prompt("X", "seed", doc_types=["ProjectCharter", "Backlog", "unknown"])  # backlog/unknown filtered
    assert set(out.keys()) == {"ProjectCharter.md", "SRS.md", "SDD.md", "TestPlan.md"}


def test_generate_backlog_with_master_prompt_success(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    class StubLLM:
        def __init__(self, *a, **k):
            pass
        def invoke(self, msgs):
            return type("R", (), {"content": "{\n  \"BacklogMarkdown\": \"# B\", \n \"BacklogCSV\": \"a,b\\n1,2\", \n \"BacklogJSON\": {\"k\":1}\n}"})()

    monkeypatch.setattr(mp, "ChatOpenAI", StubLLM)
    monkeypatch.setattr(mp, "_load_master_prompt", lambda: "PROMPT")

    out = mp.generate_backlog_with_master_prompt("X", attachments={"SRS.md": "x"})
    assert set(out.keys()) == {"Backlog.md", "Backlog.csv", "Backlog.json"}
