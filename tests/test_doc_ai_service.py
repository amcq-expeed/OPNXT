from src.orchestrator.services.doc_ai import enrich_answers_with_ai


def test_enrich_answers_fallback_no_key(monkeypatch):
    # Ensure no API key so the service falls back deterministically
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    answers, summaries = enrich_answers_with_ai("Allow users to register and reset passwords")
    assert isinstance(answers, dict)
    assert "Requirements" in answers
    reqs = answers["Requirements"]
    assert isinstance(reqs, list) and len(reqs) >= 1
    assert all(isinstance(x, str) for x in reqs)
    assert all(x.startswith("The system SHALL") for x in reqs)
    assert isinstance(summaries, dict)


def test_enrich_answers_fallback_empty(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    answers, summaries = enrich_answers_with_ai("")
    assert answers["Requirements"][0].startswith("The system SHALL address:")
    assert summaries["Planning"] in ("Project purpose", "")
