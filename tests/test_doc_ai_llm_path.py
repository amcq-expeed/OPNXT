from src.orchestrator.services import doc_ai as dai


def test_doc_ai_llm_json_extraction_and_normalization(monkeypatch):
    # Enable LLM path
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    class StubLLM:
        def __init__(self, *args, **kwargs):
            pass
        def invoke(self, msgs):
            # Return JSON embedded in extra text to trigger regex extraction fallback
            txt = (
                "Some heading before JSON\n"
                "{\n"
                "  \"planning_summary\": \"improve security\",\n"
                "  \"requirements\": [\n"
                "    \"the system shall log in\",\n"
                "    \"- multi factor\",\n"
                "    \"\u2022 performance\",\n"
                "    \"heading\",\n"
                "    \"1) rate limits\"\n"
                "  ],\n"
                "  \"design_notes\": [\"\", \"Add caching\"]\n"
                "}\n"
            )
            return type("Resp", (), {"content": txt})()

    monkeypatch.setattr(dai, "ChatOpenAI", StubLLM)

    answers, summaries = dai.enrich_answers_with_ai("A short description")
    # Ensure normalized SHALL requirements exist and are deduplicated
    reqs = answers.get("Requirements", [])
    assert any(x.startswith("The system SHALL") for x in reqs)
    # Heading (too short) should be dropped; MFA and performance normalized; numbers normalized
    assert any("Rate limits." in x for x in reqs)
    # Design notes present and trimmed
    design = answers.get("Design", [])
    assert isinstance(design, list) and len(design) >= 1
    assert summaries.get("Planning")
