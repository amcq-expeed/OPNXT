from src.orchestrator.infrastructure.doc_store import InMemoryDocumentStore, MongoDocumentStore


def test_inmemory_doc_store_versioning_and_dedup():
    store = InMemoryDocumentStore()
    pid = "PRJ-TEST-0001"

    v1 = store.save_document(pid, "SRS.md", "content v1", meta={"overlay": False})
    assert v1 == 1
    # Dedup: same content should not bump version; meta merges
    v1b = store.save_document(pid, "SRS.md", "content v1", meta={"note": "same"})
    assert v1b == 1

    # New content -> version increments
    v2 = store.save_document(pid, "SRS.md", "content v2")
    assert v2 == 2

    versions = store.list_documents(pid)
    assert "SRS.md" in versions
    assert versions["SRS.md"][-1]["version"] == 2

    latest = store.get_document(pid, "SRS.md")
    assert latest is not None and latest.version == 2 and latest.content == "content v2"

    first = store.get_document(pid, "SRS.md", version=1)
    assert first is not None and first.content == "content v1"


def test_mongo_doc_store_fallback(monkeypatch):
    # Ensure we do not require Mongo; fallback should be active by default when pymongo not installed
    monkeypatch.setenv("OPNXT_DOC_STORE_REQUIRE_MONGO", "false")
    store = MongoDocumentStore()

    pid = "PRJ-TEST-0002"
    v1 = store.save_document(pid, "Test.md", "alpha")
    assert v1 >= 1
    listing = store.list_documents(pid)
    assert "Test.md" in listing
    dv = store.get_document(pid, "Test.md")
    assert dv is not None and dv.content == "alpha"
