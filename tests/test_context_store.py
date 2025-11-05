from src.orchestrator.services.context_store import ContextStore, get_context_store


def test_context_store_put_and_get_are_copy_isolated():
    store = ContextStore()

    payload = {"key": "value", "nested": {"child": 1}}
    returned = store.put("PRJ-123", payload)
    assert returned == payload
    assert returned is not payload  # ensure defensive copy

    fetched = store.get("PRJ-123")
    assert fetched == payload
    assert fetched is not payload

    # mutations on result should not leak back for top-level keys
    fetched["key"] = "mutated"

    reread = store.get("PRJ-123")
    assert reread["key"] == "value"

    # Because ContextStore performs a shallow copy, nested objects remain shared
    fetched["nested"]["child"] = 99
    reread_nested = store.get("PRJ-123")
    assert reread_nested["nested"]["child"] == 99


def test_get_context_store_singleton_retains_state(monkeypatch):
    singleton = get_context_store()
    singleton.put("PRJ-ABC", {"foo": "bar"})

    # re-importing should yield same singleton
    other = get_context_store()
    assert other.get("PRJ-ABC") == {"foo": "bar"}

    # ensure tests do not leak: reset stored data
    monkeypatch.setattr(singleton, "_data", {}, raising=False)
