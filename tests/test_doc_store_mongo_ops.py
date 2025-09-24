import sys
import types

from src.orchestrator.infrastructure.doc_store import MongoDocumentStore


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)
    def sort(self, *args, **kwargs):
        # Support both sort("field", dir) and sort([(field, dir), ...])
        if not args:
            return self
        if len(args) == 1 and isinstance(args[0], list):
            fields = list(args[0])
            # Apply sorts in reverse for stable compound ordering
            for field, direction in reversed(fields):
                rev = direction == -1
                self._docs.sort(key=lambda d, f=field: d.get(f, 0), reverse=rev)
            return self
        if len(args) >= 2:
            field, direction = args[0], args[1]
            rev = direction == -1
            self._docs.sort(key=lambda d: d.get(field, 0), reverse=rev)
            return self
        return self
    def limit(self, n):
        if n is not None:
            self._docs = self._docs[:n]
        return self
    def __iter__(self):
        return iter(self._docs)


class _FakeCollection:
    def __init__(self):
        self.docs = []
    def create_index(self, *args, **kwargs):
        return "ok"
    def find(self, query=None):
        query = query or {}
        def _match(d):
            return all(d.get(k) == v for k, v in query.items())
        return _Cursor([d for d in self.docs if _match(d)])
    def find_one(self, query):
        for d in self.find(query):
            return d
        return None
    def insert_one(self, doc):
        self.docs.append(dict(doc))
        return types.SimpleNamespace(inserted_id=len(self.docs))


class _FakeDB:
    def __init__(self):
        self.cols = {"documents": _FakeCollection()}
    def __getitem__(self, name):
        return self.cols.setdefault(name, _FakeCollection())


class _FakeMongoClient:
    def __init__(self, url, serverSelectionTimeoutMS=None):
        self.url = url
        self._dbs = {"opnxt": _FakeDB()}
    def server_info(self):
        return {}
    def __getitem__(self, name):
        return self._dbs.setdefault(name, _FakeDB())


class _FakeGridOut:
    def __init__(self, data):
        self._data = data
    def read(self):
        return self._data


class _FakeGridFS:
    def __init__(self, db):
        self._store = {}
        self._next = 1
    def put(self, data, filename=None):
        fid = self._next
        self._next += 1
        self._store[fid] = data
        return fid
    def get(self, blob_id):
        return _FakeGridOut(self._store.get(blob_id, b""))


def test_mongo_document_store_crud(monkeypatch):
    # Stub modules
    pymongo = types.SimpleNamespace(MongoClient=_FakeMongoClient)
    gridfs = types.SimpleNamespace(GridFS=_FakeGridFS)
    monkeypatch.setitem(sys.modules, "pymongo", pymongo)
    monkeypatch.setitem(sys.modules, "gridfs", gridfs)

    store = MongoDocumentStore()

    pid = "PRJ-MONGO-1"
    # Save first version
    v1 = store.save_document(pid, "SRS.md", "alpha")
    assert v1 == 1

    # Duplicate content should not bump version
    v1b = store.save_document(pid, "SRS.md", "alpha")
    assert v1b == 1

    # New content bumps
    v2 = store.save_document(pid, "SRS.md", "beta")
    assert v2 == 2

    # List
    listing = store.list_documents(pid)
    assert "SRS.md" in listing and listing["SRS.md"][-1]["version"] == 2

    # Get latest
    dv = store.get_document(pid, "SRS.md")
    assert dv is not None and dv.version == 2 and dv.content == "beta"

    # Get specific version
    dv1 = store.get_document(pid, "SRS.md", version=1)
    assert dv1 is not None and dv1.content == "alpha"
