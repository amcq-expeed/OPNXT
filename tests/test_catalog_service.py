from src.orchestrator.services.catalog_service import list_intents, get_intent


def test_list_intents_returns_all_by_default():
    intents = list_intents()
    assert len(intents) >= 4
    assert intents[0].intent_id == "requirements-baseline"


def test_list_intents_prioritizes_matching_persona():
    intents = list_intents(persona="Engineer")
    # ensure all intents still present
    ids = [intent.intent_id for intent in intents]
    assert set(ids) >= {
        "requirements-baseline",
        "generate-sdlc-doc",
        "design-build-guidance",
        "enhance-documentation",
    }
    # all engineer-aligned intents should appear before any non-matching intent
    def has_engineer(intent_id: str) -> bool:
        return "engineer" in {p.lower() for p in get_intent(intent_id).personas}

    first_non_engineer = next((i for i, intent in enumerate(intents) if not has_engineer(intent.intent_id)), len(intents))
    assert all(
        has_engineer(intent.intent_id) for intent in intents[:first_non_engineer]
    )


def test_get_intent_returns_match_and_none():
    intent = get_intent("enhance-documentation")
    assert intent is not None
    assert intent.title.startswith("Enhance")

    assert get_intent("missing-intent") is None


def test_list_intents_handles_unknown_persona_gracefully():
    intents = list_intents(persona="Nonexistent")
    assert len(intents) >= 4
    # order should fall back to default catalog sequence
    assert intents[0].intent_id == "requirements-baseline"


def test_intent_guardrails_and_personas_present():
    intents = list_intents()
    target = next(i for i in intents if i.intent_id == "generate-sdlc-doc")
    assert "enterprise-guardrails" in target.guardrails
    assert "engineer" in target.personas
