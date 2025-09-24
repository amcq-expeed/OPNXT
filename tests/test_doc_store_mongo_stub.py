import types
import sys

from src.orchestrator.infrastructure.doc_store import MongoDocumentStore


class _FakeCollection:
    def create_index(self, *args, **kwargs):
        return "ok"

    def find(self, *args, **kwargs):
        class _Cur:
            def sort(self, *a, **k):
                return self
            def limit(self, n):
                return self
            def __iter__(self):
                return iter([])
        return _Cur()

    def insert_one(self, doc):
        return type("Res", (), {"inserted_id": 1})()

    def find_one(self, *args, **kwargs):
        return None


class _FakeDB(dict):
    def __getitem__(self, name):
        return _FakeCollection()


class _FakeMongoClient:
    def __init__(self, url, serverSelectionTimeoutMS=None):
        self.url = url
    def server_info(self):
        return {}
    def __getitem__(self, name):
        return _FakeDB()


class _FakeGridOut:
    def __init__(self, content):
        self._c = content
    def read(self):
        return self._c.encode("utf-8")


class _FakeGridFS:
    def __init__(self, db):
        pass
    def put(self, data, filename=None):
        return 123
    def get(self, blob_id):
        return _FakeGridOut("content")


def test_mongo_document_store_initializes_without_fallback(monkeypatch):
    # Insert stub modules into sys.modules to satisfy imports
    pymongo = types.SimpleNamespace(MongoClient=_FakeMongoClient)
    gridfs = types.SimpleNamespace(GridFS=_FakeGridFS)
    monkeypatch.setitem(sys.modules, "pymongo", pymongo)
    monkeypatch.setitem(sys.modules, "gridfs", gridfs)

    store = MongoDocumentStore()
    # With fake modules present and client usable, fallback should be disabled
    assert store._use_fallback() is False
