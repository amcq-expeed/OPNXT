import importlib
import sys
import types

import pytest

from src.orchestrator.infrastructure import chat_store


@pytest.fixture
def fresh_store(monkeypatch):
    monkeypatch.setattr(chat_store, "_store", None, raising=False)
    monkeypatch.setattr(chat_store, "_db_mode_mongo_chat_enabled", False, raising=False)
    monkeypatch.delenv("OPNXT_CHAT_STORE_IMPL", raising=False)
    return chat_store.InMemoryChatStore()


def test_chat_store_search_empty_query_returns_empty(fresh_store):
    assert fresh_store.search_messages("") == []


def test_chat_store_search_respects_limit(fresh_store):
    session = fresh_store.create_session("proj-1", "user@example.com")
    for index in range(3):
        fresh_store.add_message(session.session_id, "user", f"log update iteration {index}")
    results = fresh_store.search_messages("iteration", limit=1)
    assert len(results) == 1


def test_chat_store_build_snippet_handles_positions(fresh_store):
    text = "Start of text " + ("A" * 80) + " keyword in middle " + ("B" * 80)
    snippet = fresh_store._build_snippet(text, "keyword")
    assert snippet.startswith("…")
    assert snippet.endswith("…")


def test_chat_store_build_snippet_no_match_returns_prefix(fresh_store):
    text = "Short text without much content"
    snippet = fresh_store._build_snippet(text, "needle")
    assert snippet.startswith("Short text")


def test_chat_store_update_session_persona_missing_raises(fresh_store):
    with pytest.raises(KeyError):
        fresh_store.update_session_persona("missing", "Advisor")


def test_chat_store_guest_and_recent_sessions(fresh_store):
    guest = fresh_store.create_session(None, "guest@example.com")
    project = fresh_store.create_session("proj-2", "owner@example.com")
    fresh_store.add_message(project.session_id, "assistant", "important update")

    guests = fresh_store.list_guest_sessions()
    assert any(sess.session_id == guest.session_id for sess in guests)

    recents = fresh_store.list_recent_sessions(limit=2)
    assert any(sess.session_id == project.session_id for sess in recents)

    assert fresh_store.count_sessions() == 2

    assert fresh_store.get_session("missing") is None


def test_chat_store_list_sessions_skips_missing_ids(fresh_store):
    fresh_store._by_project["proj-missing"] = ["ghost-session"]
    sessions = fresh_store.list_sessions("proj-missing")
    assert sessions == []


def test_chat_store_list_guest_sessions_skips_missing_ids(fresh_store):
    fresh_store._guest_sessions.append("ghost-guest")
    guests = fresh_store.list_guest_sessions()
    assert all(sess.session_id != "ghost-guest" for sess in guests)


def test_chat_store_search_with_project_scope(fresh_store):
    project_session = fresh_store.create_session("proj-search", "owner@example.com")
    fresh_store.add_message(project_session.session_id, "assistant", "Project update ready")

    results = fresh_store.search_messages("update", project_id="proj-search", limit=5)
    assert results and results[0][0].project_id == "proj-search"


def test_chat_store_search_handles_missing_session_entries(fresh_store):
    fresh_store._messages["ghost-session"] = []
    assert fresh_store.search_messages("anything") == []


def test_chat_store_get_chat_store_prefers_mongo_when_db_mode_enabled(monkeypatch):
    monkeypatch.setenv("DB_MODE", "mongo")

    fake_module = types.ModuleType("src.orchestrator.infrastructure.chat_store_mongo")

    class FakeMongoStore:
        marker = "fake"

    fake_module.MongoChatStore = lambda: FakeMongoStore()
    monkeypatch.setitem(sys.modules, "src.orchestrator.infrastructure.chat_store_mongo", fake_module)

    reloaded = importlib.reload(chat_store)
    try:
        resolved = reloaded.get_chat_store()
        assert isinstance(resolved, FakeMongoStore)
        assert reloaded._db_mode_mongo_chat_enabled is True
    finally:
        monkeypatch.delenv("DB_MODE", raising=False)
        importlib.reload(chat_store)


def test_chat_store_get_chat_store_handles_mongo_import_failure(monkeypatch):
    monkeypatch.setenv("DB_MODE", "mongo")
    empty_module = types.ModuleType("src.orchestrator.infrastructure.chat_store_mongo")
    monkeypatch.setitem(sys.modules, "src.orchestrator.infrastructure.chat_store_mongo", empty_module)

    reloaded = importlib.reload(chat_store)
    try:
        store = reloaded.get_chat_store()
        assert isinstance(store, reloaded.InMemoryChatStore)
        assert reloaded._db_mode_mongo_chat_enabled is False
    finally:
        monkeypatch.delenv("DB_MODE", raising=False)
        importlib.reload(chat_store)
