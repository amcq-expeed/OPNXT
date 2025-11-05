import importlib
import sys
import types
from datetime import datetime

import pytest

from src.orchestrator.infrastructure import doc_store


def test_doc_store_get_document_missing_returns_none():
    store = doc_store.InMemoryDocumentStore()
    assert store.get_document("proj-1", "missing.md") is None


def test_doc_store_get_document_unknown_version_returns_none():
    store = doc_store.InMemoryDocumentStore()
    store.save_document("proj-1", "plan.md", "v1")
    assert store.get_document("proj-1", "plan.md", version=99) is None


def test_doc_store_accelerator_preview_missing_returns_none():
    store = doc_store.InMemoryDocumentStore()
    assert store.get_accelerator_preview("sess-x", "draft.md") is None


def test_doc_store_ensure_utc_handles_non_datetime():
    result = doc_store._ensure_utc("not-a-datetime")
    assert result.tzinfo is not None


def test_doc_store_isoformat_handles_naive_datetime():
    naive = datetime(2024, 1, 1, 9, 5, 0)
    formatted = doc_store._isoformat_utc(naive)
    assert formatted.endswith("Z")


def test_doc_store_db_mode_mongo_import_success(monkeypatch):
    monkeypatch.setenv("DB_MODE", "mongo")
    fake_module = types.ModuleType("src.orchestrator.infrastructure.doc_store_mongo")

    class FakeMongoStore:
        marker = "mongo"

        def __init__(self):
            self.initialized = True

        pass

    fake_module.MongoDocumentStore = FakeMongoStore
    monkeypatch.setitem(sys.modules, "src.orchestrator.infrastructure.doc_store_mongo", fake_module)

    reloaded = importlib.reload(doc_store)
    try:
        assert reloaded._mongo_doc_store_cls is FakeMongoStore
        assert reloaded._db_mode_mongo_docs_enabled is True
        instance = reloaded.get_doc_store()
        assert isinstance(instance, FakeMongoStore)
    finally:
        monkeypatch.delenv("DB_MODE", raising=False)
        importlib.reload(doc_store)


def test_doc_store_db_mode_mongo_import_failure(monkeypatch):
    monkeypatch.setenv("DB_MODE", "mongo")
    empty_module = types.ModuleType("src.orchestrator.infrastructure.doc_store_mongo")
    monkeypatch.setitem(sys.modules, "src.orchestrator.infrastructure.doc_store_mongo", empty_module)

    reloaded = importlib.reload(doc_store)
    try:
        assert reloaded._mongo_doc_store_cls is None
        assert reloaded._db_mode_mongo_docs_enabled is False
    finally:
        monkeypatch.delenv("DB_MODE", raising=False)
        importlib.reload(doc_store)


def test_mongo_doc_store_dedup_exception_creates_new_version(monkeypatch):
    store = doc_store.MongoDocumentStore()

    class CursorStub:
        def __iter__(self):
            yield {"version": 1, "blob_id": "previous"}

        def sort(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

    class MetaStub:
        def __init__(self):
            self.inserted = None

        def find(self, _query):
            return CursorStub()

        def insert_one(self, doc):
            self.inserted = doc

    class FsStub:
        def get(self, _blob_id):
            raise RuntimeError("gridfs failure")

        def put(self, _data, *_args, **_kwargs):
            return "new-blob-id"

    store._client = object()
    store._db = object()
    store._meta = MetaStub()
    store._fs = FsStub()

    version = store.save_document("proj-z", "Design.md", "fresh content", meta={"source": "test"})
    assert version == 2
    assert store._meta.inserted["meta"]["source"] == "test"


def test_mongo_doc_store_get_document_handles_missing(monkeypatch):
    store = doc_store.MongoDocumentStore()

    class EmptyCursor:
        def __iter__(self):
            return iter(())

        def sort(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

    class MetaStub:
        def find(self, _query):
            return EmptyCursor()

        def find_one(self, _query):
            return None

    store._client = object()
    store._db = object()
    store._meta = MetaStub()
    store._fs = object()

    assert store.get_document("proj-x", "missing.md") is None


def test_mongo_doc_store_accelerator_preview_delegates(monkeypatch):
    store = doc_store.MongoDocumentStore()

    class FallbackStub:
        def __init__(self):
            self.saved = None

        def save_accelerator_preview(self, *args, **kwargs):
            self.saved = (args, kwargs)
            return 5

        def list_accelerator_previews(self, session_id):
            return [{"session": session_id, "version": 1}]

        def get_accelerator_preview(self, session_id, filename):
            return {"session": session_id, "filename": filename}

    fallback = FallbackStub()
    store._fallback = fallback

    version = store.save_accelerator_preview("sess-1", "draft.md", "content", {"note": "v1"})
    assert version == 5
    assert fallback.saved[0][0] == "sess-1"

    previews = store.list_accelerator_previews("sess-1")
    assert previews[0]["version"] == 1

    preview = store.get_accelerator_preview("sess-1", "draft.md")
    assert preview["filename"] == "draft.md"
