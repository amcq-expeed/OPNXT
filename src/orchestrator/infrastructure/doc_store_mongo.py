# --- v1.0 update ---
from __future__ import annotations

# --- v1.0 update ---
import asyncio
import os
from datetime import UTC, datetime
from typing import Any, Dict, Optional

try:  # pragma: no cover - optional dependency
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket  # type: ignore
except Exception:  # pragma: no cover - dependency optional
    AsyncIOMotorClient = None  # type: ignore
    AsyncIOMotorGridFSBucket = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from bson import ObjectId  # type: ignore
except Exception:  # pragma: no cover - dependency optional
    ObjectId = None  # type: ignore


# --- v1.0 update ---
class MongoDocumentStore:
    def __init__(self) -> None:
        from .doc_store import (  # local import to avoid circular
            InMemoryDocumentStore,
            DocVersion,
            _ensure_utc,
            _utc_now,
        )

        self._fallback = InMemoryDocumentStore()
        self._DocVersion = DocVersion
        self._ensure_utc = _ensure_utc
        self._utc_now = _utc_now
        self._client: AsyncIOMotorClient | None = None
        self._db = None
        self._collection = None
        self._fs: AsyncIOMotorGridFSBucket | None = None
        if AsyncIOMotorClient is None or AsyncIOMotorGridFSBucket is None:
            return
        try:
            mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
            mongo_db = os.getenv("MONGO_DB", "opnxt")
            self._client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=500)
            self._run(self._client.server_info())
            self._db = self._client[mongo_db]
            self._collection = self._db["documents"]
            self._fs = AsyncIOMotorGridFSBucket(self._db)
            self._run(self._collection.create_index(
                [
                    ("project_id", 1),
                    ("filename", 1),
                    ("version", 1),
                ],
                unique=True,
            ))
        except Exception:
            self._client = None
            self._collection = None
            self._db = None
            self._fs = None

    # --- v1.0 update ---
    def save_document(self, project_id: str, filename: str, content: str, meta: Optional[Dict[str, Any]] = None) -> int:
        if not self._collection or not self._fs:
            return self._fallback.save_document(project_id, filename, content, meta)
        try:
            last = self._run(
                self._collection.find({"project_id": project_id, "filename": filename})
                .sort("version", -1)
                .limit(1)
                .to_list(length=1)
            )
            last_doc = last[0] if last else None
            if last_doc and ObjectId is not None:
                try:
                    blob_id = last_doc.get("blob_id")
                    if blob_id:
                        read_stream = self._fs.open_download_stream(blob_id)
                        data = self._run(read_stream.read())
                        if isinstance(data, bytes) and data.decode("utf-8") == content:
                            return int(last_doc.get("version", 1))
                except Exception:
                    pass
            version = int(last_doc.get("version", 0)) + 1 if last_doc else 1
            blob_id = self._run(self._fs.upload_from_stream(filename, content.encode("utf-8")))
            doc = {
                "project_id": project_id,
                "filename": filename,
                "version": version,
                "created_at": self._utc_now(),
                "meta": dict(meta or {}),
                "blob_id": blob_id,
            }
            self._run(self._collection.insert_one(doc))
            return version
        except Exception:
            return self._fallback.save_document(project_id, filename, content, meta)

    # --- v1.0 update ---
    def list_documents(self, project_id: str) -> Dict[str, Any]:
        if not self._collection:
            return self._fallback.list_documents(project_id)
        try:
            cursor = self._collection.find({"project_id": project_id}).sort([
                ("filename", 1),
                ("version", 1),
            ])
            docs = self._run(cursor.to_list(length=5000))
            out: Dict[str, Any] = {}
            for doc in docs:
                fname = str(doc.get("filename"))
                out.setdefault(fname, []).append(
                    {
                        "version": int(doc.get("version", 0)),
                        "created_at": self._ensure_utc(doc.get("created_at")).isoformat().replace("+00:00", "Z"),
                        "meta": doc.get("meta") or {},
                    }
                )
            return out
        except Exception:
            return self._fallback.list_documents(project_id)

    # --- v1.0 update ---
    def get_document(self, project_id: str, filename: str, version: Optional[int] = None):
        if not self._collection or not self._fs:
            return self._fallback.get_document(project_id, filename, version)
        try:
            query = {"project_id": project_id, "filename": filename}
            if version is not None:
                query["version"] = version
                doc = self._run(self._collection.find_one(query))
            else:
                doc_list = self._run(
                    self._collection.find(query).sort("version", -1).limit(1).to_list(length=1)
                )
                doc = doc_list[0] if doc_list else None
            if not doc:
                return None
            blob_id = doc.get("blob_id")
            if not blob_id:
                return None
            data = self._run(self._fs.open_download_stream(blob_id).read())
            content = data.decode("utf-8") if isinstance(data, bytes) else str(data)
            return self._DocVersion(
                version=int(doc.get("version", 0)),
                filename=str(doc.get("filename")),
                created_at=self._ensure_utc(doc.get("created_at")),
                meta=doc.get("meta") or {},
                content=content,
            )
        except Exception:
            return self._fallback.get_document(project_id, filename, version)

    # --- v1.0 update ---
    def save_accelerator_preview(self, session_id: str, filename: str, content: str, meta: Optional[Dict[str, Any]] = None) -> int:
        return self._fallback.save_accelerator_preview(session_id, filename, content, meta)

    # --- v1.0 update ---
    def list_accelerator_previews(self, session_id: str):
        return self._fallback.list_accelerator_previews(session_id)

    # --- v1.0 update ---
    def _run(self, awaitable: Any) -> Any:
        if not asyncio.iscoroutine(awaitable):
            return awaitable
        try:
            return asyncio.run(awaitable)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(awaitable)
            finally:
                loop.close()

