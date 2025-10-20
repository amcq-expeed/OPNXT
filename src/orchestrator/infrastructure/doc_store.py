from __future__ import annotations

import os
from dataclasses import dataclass
import hashlib
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Protocol
from threading import RLock


@dataclass
class DocVersion:
    version: int
    filename: str
    created_at: datetime
    meta: Dict[str, Any]
    content: str


class DocumentStore(Protocol):
    def save_document(self, project_id: str, filename: str, content: str, meta: Optional[Dict[str, Any]] = None) -> int: ...
    def list_documents(self, project_id: str) -> Dict[str, List[Dict[str, Any]]]: ...
    def get_document(self, project_id: str, filename: str, version: Optional[int] = None) -> Optional[DocVersion]: ...
    def save_accelerator_preview(self, session_id: str, filename: str, content: str, meta: Optional[Dict[str, Any]] = None) -> int: ...
    def list_accelerator_previews(self, session_id: str) -> List[Dict[str, Any]]: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _ensure_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    return _utc_now()


def _isoformat_utc(value: Any) -> str:
    dt = _ensure_utc(value)
    return dt.isoformat().replace("+00:00", "Z")


class InMemoryDocumentStore:
    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, List[DocVersion]]] = {}
        self._accelerator_data: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = RLock()

    def save_document(self, project_id: str, filename: str, content: str, meta: Optional[Dict[str, Any]] = None) -> int:
        with self._lock:
            proj = self._data.setdefault(project_id, {})
            versions = proj.setdefault(filename, [])
            # Deduplicate: if content is identical to last version, do NOT bump version
            if versions and versions[-1].content == content:
                # Optionally merge meta into last version's meta
                if meta:
                    versions[-1].meta.update(meta)
                return versions[-1].version
            version = (versions[-1].version + 1) if versions else 1
            dv = DocVersion(
                version=version,
                filename=filename,
                created_at=_utc_now(),
                meta=dict(meta or {}),
                content=content,
            )
            versions.append(dv)
            return version

    def list_documents(self, project_id: str) -> Dict[str, List[Dict[str, Any]]]:
        with self._lock:
            out: Dict[str, List[Dict[str, Any]]] = {}
            for fname, versions in self._data.get(project_id, {}).items():
                out[fname] = [
                    {
                        "version": v.version,
                        "created_at": _isoformat_utc(v.created_at),
                        "meta": v.meta,
                    }
                    for v in versions
                ]
            return out

    def get_document(self, project_id: str, filename: str, version: Optional[int] = None) -> Optional[DocVersion]:
        with self._lock:
            versions = self._data.get(project_id, {}).get(filename, [])
            if not versions:
                return None
            if version is None:
                return versions[-1]
            for v in versions:
                if v.version == version:
                    return v
            return None

    def save_accelerator_preview(self, session_id: str, filename: str, content: str, meta: Optional[Dict[str, Any]] = None) -> int:
        with self._lock:
            entries = self._accelerator_data.setdefault(session_id, [])
            version = len(entries) + 1
            entry = {
                "version": version,
                "filename": filename,
                "created_at": _isoformat_utc(_utc_now()),
                "meta": dict(meta or {}),
                "content": content,
            }
            entries.append(entry)
            return version

    def list_accelerator_previews(self, session_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._accelerator_data.get(session_id, []))


class MongoDocumentStore:
    """Mongo-backed document store using GridFS for content.

    If Mongo is unreachable and OPNXT_DOC_STORE_REQUIRE_MONGO is not true,
    operations fall back to an internal in-memory store to avoid breaking dev/CI.
    """

    def __init__(self) -> None:
        self._fallback = InMemoryDocumentStore()
        self._client = None
        self._db = None
        self._fs = None
        try:
            from pymongo import MongoClient  # type: ignore
            import gridfs  # type: ignore

            mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
            mongo_db = os.getenv("MONGO_DB", "opnxt")
            self._client = MongoClient(mongo_url, serverSelectionTimeoutMS=500)
            # Trigger server selection
            self._client.server_info()
            self._db = self._client[mongo_db]
            self._fs = gridfs.GridFS(self._db)
            # Metadata collection
            self._meta = self._db["documents"]
            self._meta.create_index([("project_id", 1), ("filename", 1), ("version", 1)], unique=True)
        except Exception:
            # Remain in fallback mode
            self._client = None
            self._db = None
            self._fs = None
            self._meta = None

    def _use_fallback(self) -> bool:
        return self._client is None or self._db is None or self._fs is None or self._meta is None

    def save_document(self, project_id: str, filename: str, content: str, meta: Optional[Dict[str, Any]] = None) -> int:
        if self._use_fallback():
            if os.getenv("OPNXT_DOC_STORE_REQUIRE_MONGO", "false").lower() in ("1", "true", "yes"):  # pragma: no cover
                raise RuntimeError("Mongo document store required but not available")
            return self._fallback.save_document(project_id, filename, content, meta)
        # Determine next version
        last_cursor = (
            self._meta.find({"project_id": project_id, "filename": filename})
            .sort("version", -1)
            .limit(1)
        )
        last_doc = next(iter(last_cursor), None)
        last_ver = int(last_doc.get("version", 0)) if last_doc else 0
        # Deduplicate by content hash
        try:
            if last_doc is not None:
                grid_out = self._fs.get(last_doc.get("blob_id"))
                prev_content = grid_out.read().decode("utf-8")
                if prev_content == content:
                    return last_ver
        except Exception:
            # If any error occurs during dedup check, proceed to save a new version
            pass
        version = last_ver + 1
        # Save content to GridFS
        file_id = self._fs.put(content.encode("utf-8"), filename=filename)
        doc = {
            "project_id": project_id,
            "filename": filename,
            "version": version,
            "created_at": _utc_now(),
            "meta": dict(meta or {}),
            "blob_id": file_id,
        }
        self._meta.insert_one(doc)
        return version

    def list_documents(self, project_id: str) -> Dict[str, List[Dict[str, Any]]]:
        if self._use_fallback():
            return self._fallback.list_documents(project_id)
        out: Dict[str, List[Dict[str, Any]]] = {}
        for doc in self._meta.find({"project_id": project_id}).sort([("filename", 1), ("version", 1)]):
            fname = str(doc.get("filename"))
            out.setdefault(fname, []).append(
                {
                    "version": int(doc.get("version", 0)),
                    "created_at": _isoformat_utc(doc.get("created_at")),
                    "meta": doc.get("meta") or {},
                }
            )
        return out

    def get_document(self, project_id: str, filename: str, version: Optional[int] = None) -> Optional[DocVersion]:
        if self._use_fallback():
            return self._fallback.get_document(project_id, filename, version)
        query = {"project_id": project_id, "filename": filename}
        if version is not None:
            query["version"] = version
        else:
            # last version
            doc = (
                self._meta.find({"project_id": project_id, "filename": filename})
                .sort("version", -1)
                .limit(1)
            )
            doc = next(iter(doc), None)
            if not doc:
                return None
            query["version"] = int(doc.get("version", 0))
        doc = self._meta.find_one(query)
        if not doc:
            return None
        blob_id = doc.get("blob_id")
        grid_out = self._fs.get(blob_id)
        content = grid_out.read().decode("utf-8")
        return DocVersion(
            version=int(doc.get("version", 0)),
            filename=str(doc.get("filename")),
            created_at=_ensure_utc(doc.get("created_at")),
            meta=doc.get("meta") or {},
            content=content,
        )

    def save_accelerator_preview(self, session_id: str, filename: str, content: str, meta: Optional[Dict[str, Any]] = None) -> int:
        return self._fallback.save_accelerator_preview(session_id, filename, content, meta)

    def list_accelerator_previews(self, session_id: str) -> List[Dict[str, Any]]:
        return self._fallback.list_accelerator_previews(session_id)


_doc_store_singleton: DocumentStore | None = None


def get_doc_store() -> DocumentStore:
    global _doc_store_singleton
    if _doc_store_singleton is not None:
        return _doc_store_singleton
    impl = os.getenv("OPNXT_DOC_STORE_IMPL", "memory").lower()
    if impl == "mongo":
        _doc_store_singleton = MongoDocumentStore()
        return _doc_store_singleton
    _doc_store_singleton = InMemoryDocumentStore()
    return _doc_store_singleton
