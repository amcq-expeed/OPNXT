import sys
import types
from datetime import datetime

import pytest

from src.orchestrator.infrastructure import chat_store, doc_store


@pytest.fixture(autouse=True)
def reset_singletons(monkeypatch):
    # Ensure each test starts with a clean singleton state
    monkeypatch.setattr(doc_store, "_doc_store_singleton", None, raising=False)
    monkeypatch.setattr(doc_store, "_db_mode_mongo_docs_enabled", False, raising=False)
    monkeypatch.delenv("OPNXT_DOC_STORE_IMPL", raising=False)

    monkeypatch.setattr(chat_store, "_store", None, raising=False)
    monkeypatch.setattr(chat_store, "_db_mode_mongo_chat_enabled", False, raising=False)
    monkeypatch.delenv("OPNXT_CHAT_STORE_IMPL", raising=False)


# ---------------------- Document Store coverage ----------------------


def test_inmemory_document_store_versioning_and_dedup():
    store = doc_store.InMemoryDocumentStore()

    v1 = store.save_document("PRJ-A", "Readme.md", "# Start", {"author": "ops"})
    assert v1 == 1

    v_dup = store.save_document("PRJ-A", "Readme.md", "# Start", {"status": "duplicate"})
    assert v_dup == 1  # no new version for duplicate content

    latest = store.get_document("PRJ-A", "Readme.md")
    assert latest is not None
    assert latest.version == 1
    assert latest.meta["status"] == "duplicate"

    v2 = store.save_document("PRJ-A", "Readme.md", "# Updated")
    assert v2 == 2

    history = store.list_documents("PRJ-A")
    assert history["Readme.md"][0]["version"] == 1
    assert history["Readme.md"][1]["version"] == 2

    specific = store.get_document("PRJ-A", "Readme.md", version=1)
    assert specific is not None and specific.content == "# Start"


def test_inmemory_document_store_accelerator_previews():
    store = doc_store.InMemoryDocumentStore()

    v1 = store.save_accelerator_preview("sess-1", "Preview.md", "Draft", {"seed": 1})
    assert v1 == 1

    # Duplicate payload merges metadata instead of bumping version
    v_dup = store.save_accelerator_preview("sess-1", "Preview.md", "Draft", {"status": "same"})
    assert v_dup == 1

    previews = store.list_accelerator_previews("sess-1")
    assert len(previews) == 1
    assert previews[0]["meta"]["status"] == "same"

    preview = store.get_accelerator_preview("sess-1", "Preview.md")
    assert preview is not None
    assert preview["meta"]["version"] == 1


def test_get_doc_store_defaults_to_inmemory(monkeypatch):
    store = doc_store.get_doc_store()
    assert isinstance(store, doc_store.InMemoryDocumentStore)

    # Subsequent calls reuse the singleton
    again = doc_store.get_doc_store()
    assert again is store


def test_get_doc_store_prefers_mongo_when_available(monkeypatch):
    class FakeMongoStore(doc_store.InMemoryDocumentStore):
        marker = "fake-mongo"

    monkeypatch.setenv("OPNXT_DOC_STORE_IMPL", "mongo")
    monkeypatch.setattr(doc_store, "_doc_store_singleton", None, raising=False)
    monkeypatch.setattr(doc_store, "_db_mode_mongo_docs_enabled", False, raising=False)

    fake_module = types.ModuleType("doc_store_mongo")
    fake_module.MongoDocumentStore = lambda: FakeMongoStore()
    monkeypatch.setitem(sys.modules, "src.orchestrator.infrastructure.doc_store_mongo", fake_module)

    store = doc_store.get_doc_store()
    assert isinstance(store, FakeMongoStore)


def test_get_doc_store_falls_back_when_mongo_init_fails(monkeypatch):
    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setenv("OPNXT_DOC_STORE_IMPL", "mongo")
    monkeypatch.setattr(doc_store, "_doc_store_singleton", None, raising=False)
    monkeypatch.setattr(doc_store, "_db_mode_mongo_docs_enabled", False, raising=False)

    failing_module = types.ModuleType("doc_store_mongo")
    failing_module.MongoDocumentStore = _boom
    monkeypatch.setitem(sys.modules, "src.orchestrator.infrastructure.doc_store_mongo", failing_module)

    store = doc_store.get_doc_store()
    assert isinstance(store, doc_store.InMemoryDocumentStore)


def test_mongo_doc_store_uses_fallback_operations():
    mongo = doc_store.MongoDocumentStore()
    version = mongo.save_document("PRJ-B", "notes.md", "alpha")
    assert version == 1

    listing = mongo.list_documents("PRJ-B")
    assert "notes.md" in listing

    retrieved = mongo.get_document("PRJ-B", "notes.md")
    assert retrieved is not None and retrieved.content == "alpha"


def test_doc_store_time_helpers_handle_naive_datetime():
    naive = datetime(2024, 1, 1, 12, 0, 0)
    ensured = doc_store._ensure_utc(naive)
    assert ensured.tzinfo is not None
    iso = doc_store._isoformat_utc(naive)
    assert iso.endswith("Z")


# ---------------------- Chat Store coverage ----------------------


def test_inmemory_chat_store_session_lifecycle():
    store = chat_store.InMemoryChatStore()

    project_session = store.create_session("PRJ-1", "leader@example.com", title="Kickoff", persona="Guide")
    assert project_session.persona == "Guide"

    guest_session = store.create_session(None, "guest@example.com", title="Guest Chat")
    assert guest_session.kind == "guest"

    store.add_message(project_session.session_id, "assistant", "Hello there")
    store.add_message(guest_session.session_id, "user", "Discuss SRS scope")

    sessions = store.list_sessions("PRJ-1")
    assert sessions and sessions[0].session_id == project_session.session_id

    recents = store.list_recent_sessions(limit=1)
    assert recents and recents[0].session_id in {project_session.session_id, guest_session.session_id}

    guests = store.list_guest_sessions()
    assert guests and guests[0].kind == "guest"

    updated = store.update_session_persona(project_session.session_id, None)
    assert updated.persona is None

    messages = store.list_messages(project_session.session_id)
    assert len(messages) == 1 and messages[0].role == "assistant"

    search = store.search_messages("srs")
    assert any("Discuss" in snippet for *_ , snippet in search)

    assert store.get_session("missing") is None

    with pytest.raises(KeyError):
        store.update_session_persona("missing", None)

    with pytest.raises(KeyError):
        store.add_message("missing", "user", "nope")

    assert store.search_messages("   ") == []


def test_get_chat_store_defaults_to_memory():
    store = chat_store.get_chat_store()
    assert isinstance(store, chat_store.InMemoryChatStore)

    again = chat_store.get_chat_store()
    assert again is store


def test_get_chat_store_prefers_mongo_when_available(monkeypatch):
    class FakeMongoChatStore(chat_store.InMemoryChatStore):
        marker = "fake-chat-mongo"

    monkeypatch.setenv("OPNXT_CHAT_STORE_IMPL", "mongo")
    monkeypatch.setattr(chat_store, "_store", None, raising=False)
    monkeypatch.setattr(chat_store, "_db_mode_mongo_chat_enabled", False, raising=False)

    fake_module = types.ModuleType("chat_store_mongo")
    fake_module.MongoChatStore = lambda: FakeMongoChatStore()
    monkeypatch.setitem(sys.modules, "src.orchestrator.infrastructure.chat_store_mongo", fake_module)

    store = chat_store.get_chat_store()
    assert isinstance(store, FakeMongoChatStore)


def test_get_chat_store_fallback_when_mongo_unavailable(monkeypatch):
    def _fail():
        raise RuntimeError("chat mongo boom")

    monkeypatch.setenv("OPNXT_CHAT_STORE_IMPL", "mongo")
    monkeypatch.setattr(chat_store, "_store", None, raising=False)
    monkeypatch.setattr(chat_store, "_db_mode_mongo_chat_enabled", False, raising=False)

    failing_module = types.ModuleType("chat_store_mongo")
    failing_module.MongoChatStore = _fail
    monkeypatch.setitem(sys.modules, "src.orchestrator.infrastructure.chat_store_mongo", failing_module)

    store = chat_store.get_chat_store()
    assert isinstance(store, chat_store.InMemoryChatStore)


# ---------------------- Ensure env toggles cleaned ----------------------


def test_chat_store_respects_singleton_reset(monkeypatch):
    first = chat_store.get_chat_store()
    monkeypatch.setattr(chat_store, "_store", None, raising=False)
    monkeypatch.setenv("OPNXT_CHAT_STORE_IMPL", "memory")
    second = chat_store.get_chat_store()
    assert second is not first
