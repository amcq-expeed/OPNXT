from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
import uuid

try:  # pragma: no cover - optional dependency
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection  # type: ignore
except Exception:  # pragma: no cover - dependency optional
    AsyncIOMotorClient = None  # type: ignore[misc]
    AsyncIOMotorCollection = None  # type: ignore[misc]

from ..domain.accelerator_session import AcceleratorMessage, AcceleratorSession


MAX_LIVE_ARTIFACTS = 50


class MongoAcceleratorStore:
    """Mongo-backed AcceleratorStore with graceful fallback to memory."""

    def __init__(self) -> None:
        from .accelerator_store import InMemoryAcceleratorStore  # local import to avoid circular

        self._fallback = InMemoryAcceleratorStore()
        self._client: AsyncIOMotorClient | None = None
        self._sessions: AsyncIOMotorCollection | None = None
        self._messages: AsyncIOMotorCollection | None = None
        self._artifacts: AsyncIOMotorCollection | None = None
        self._live: AsyncIOMotorCollection | None = None
        self._attachments: AsyncIOMotorCollection | None = None
        self._assets: AsyncIOMotorCollection | None = None
        if AsyncIOMotorClient is None:
            return
        try:
            mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
            mongo_db = os.getenv("MONGO_DB", "opnxt")
            self._client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=500)
            self._run(self._client.server_info())
            db = self._client[mongo_db]
            self._sessions = db["accelerator_sessions"]
            self._messages = db["accelerator_messages"]
            self._artifacts = db["accelerator_artifacts"]
            self._live = db["accelerator_live_artifacts"]
            self._attachments = db["accelerator_attachments"]
            self._assets = db["accelerator_assets"]
            self._ensure_indexes()
        except Exception:
            self._client = None
            self._sessions = None
            self._messages = None
            self._artifacts = None
            self._live = None
            self._attachments = None
            self._assets = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def create_session(
        self,
        accelerator_id: str,
        created_by: str,
        persona: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AcceleratorSession:
        if self._use_fallback():
            return self._fallback.create_session(accelerator_id, created_by, persona=persona, metadata=metadata)

        session_id = uuid.uuid4().hex
        now = self._now_iso()
        doc = {
            "session_id": session_id,
            "accelerator_id": accelerator_id,
            "created_by": created_by,
            "created_at": now,
            "persona": persona,
            "project_id": None,
            "promoted_at": None,
            "metadata": dict(metadata or {}),
            "artifact_revision": 0,
        }
        try:
            self._run(self._sessions.insert_one(doc))  # type: ignore[arg-type]
            return self._to_session(doc)
        except Exception:
            return self._fallback.create_session(accelerator_id, created_by, persona=persona, metadata=metadata)

    def get_session(self, session_id: str) -> Optional[AcceleratorSession]:
        if self._use_fallback():
            return self._fallback.get_session(session_id)
        try:
            doc = self._run(self._sessions.find_one({"session_id": session_id}))  # type: ignore[arg-type]
            if not doc:
                return None
            return self._to_session(doc)
        except Exception:
            return self._fallback.get_session(session_id)

    def list_sessions(self, limit: Optional[int] = None) -> List[AcceleratorSession]:
        if self._use_fallback():
            return self._fallback.list_sessions(limit)
        try:
            cursor = (
                self._sessions.find({}).sort("created_at", -1)  # type: ignore[arg-type]
            )
            if limit is not None:
                cursor = cursor.limit(limit)
            docs = self._run(cursor.to_list(length=limit or 500))
            return [self._to_session(doc) for doc in docs]
        except Exception:
            return self._fallback.list_sessions(limit)

    def list_recent_sessions(self, limit: Optional[int] = None) -> List[AcceleratorSession]:
        sessions = self.list_sessions(limit=None)
        sessions.sort(
            key=lambda sess: (sess.metadata or {}).get("last_activity") or sess.created_at,
            reverse=True,
        )
        if limit is not None:
            sessions = sessions[: max(0, limit)]
        return sessions

    def count_sessions(self) -> int:
        if self._use_fallback():
            return self._fallback.count_sessions()
        try:
            return int(self._run(self._sessions.count_documents({})))  # type: ignore[arg-type]
        except Exception:
            return self._fallback.count_sessions()

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AcceleratorMessage:
        if self._use_fallback():
            return self._fallback.add_message(session_id, role, content, metadata=metadata)
        now = self._now_iso()
        try:
            session = self._run(self._sessions.find_one({"session_id": session_id}))  # type: ignore[arg-type]
            if not session:
                raise KeyError("Session not found")
            message_id = uuid.uuid4().hex
            doc = {
                "message_id": message_id,
                "session_id": session_id,
                "role": role,
                "content": content,
                "created_at": now,
                "metadata": dict(metadata or {}),
            }
            self._run(self._messages.insert_one(doc))  # type: ignore[arg-type]
            self._run(
                self._sessions.update_one(
                    {"session_id": session_id},  # type: ignore[list-item]
                    {
                        "$set": {
                            "metadata.message_count": self._increment_message_count(session, session_id),
                            "metadata.last_activity": now,
                        }
                    },
                )
            )
            return AcceleratorMessage(
                message_id=message_id,
                session_id=session_id,
                role=role,
                content=content,
                created_at=now,
                metadata=metadata,
            )
        except KeyError:
            raise
        except Exception:
            return self._fallback.add_message(session_id, role, content, metadata=metadata)

    def list_messages(self, session_id: str) -> List[AcceleratorMessage]:
        if self._use_fallback():
            return self._fallback.list_messages(session_id)
        try:
            cursor = self._messages.find({"session_id": session_id}).sort("created_at", 1)  # type: ignore[arg-type]
            docs = self._run(cursor.to_list(length=2000))
            return [self._to_message(doc) for doc in docs]
        except Exception:
            return self._fallback.list_messages(session_id)

    def add_artifact(
        self,
        session_id: str,
        filename: str,
        project_id: Optional[str],
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self._use_fallback():
            return self._fallback.add_artifact(session_id, filename, project_id, meta)
        payload = {
            "session_id": session_id,
            "filename": filename,
            "project_id": project_id,
            "meta": dict(meta or {}),
            "created_at": self._now_iso(),
        }
        try:
            existing = self._run(
                self._artifacts.find_one(
                    {
                        "session_id": session_id,
                        "filename": filename,
                        "meta.version": payload["meta"].get("version"),
                    }
                )
            )
            if existing:
                return self._cleanup_artifact(existing)
            self._run(self._artifacts.insert_one(payload))  # type: ignore[arg-type]
            self._increment_artifact_revision(session_id)
            self._refresh_artifact_metadata(session_id)
            return self._cleanup_artifact(payload)
        except Exception:
            return self._fallback.add_artifact(session_id, filename, project_id, meta)

    def add_live_artifact(self, session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._use_fallback():
            return self._fallback.add_live_artifact(session_id, payload)
        enriched = dict(payload or {})
        enriched.setdefault("id", uuid.uuid4().hex)
        enriched.setdefault("created_at", self._now_iso())
        enriched["session_id"] = session_id
        try:
            self._run(self._live.insert_one(enriched))  # type: ignore[arg-type]
            self._prune_live_artifacts(session_id)
            self._increment_artifact_revision(session_id)
            return enriched
        except Exception:
            return self._fallback.add_live_artifact(session_id, payload)

    def save_asset(self, session_id: str, filename: str, content: bytes) -> None:
        if self._use_fallback():
            self._fallback.save_asset(session_id, filename, content)
            return
        try:
            self._run(
                self._assets.update_one(
                    {"session_id": session_id, "filename": filename},  # type: ignore[list-item]
                    {
                        "$set": {
                            "session_id": session_id,
                            "filename": filename,
                            "content": bytes(content),
                            "updated_at": self._now_iso(),
                        }
                    },
                    upsert=True,
                )
            )
        except Exception:
            self._fallback.save_asset(session_id, filename, content)

    def get_asset(self, session_id: str, filename: str) -> Optional[bytes]:
        if self._use_fallback():
            return self._fallback.get_asset(session_id, filename)
        try:
            doc = self._run(
                self._assets.find_one({"session_id": session_id, "filename": filename})  # type: ignore[arg-type]
            )
            if not doc:
                return None
            content = doc.get("content")
            if isinstance(content, (bytes, bytearray)):
                return bytes(content)
            return None
        except Exception:
            return self._fallback.get_asset(session_id, filename)

    def list_assets(self, session_id: str) -> List[str]:
        if self._use_fallback():
            return self._fallback.list_assets(session_id)
        try:
            cursor = self._assets.find({"session_id": session_id}, {"filename": 1})  # type: ignore[arg-type]
            docs = self._run(cursor.to_list(length=200))
            return [str(doc.get("filename")) for doc in docs if doc.get("filename")]
        except Exception:
            return self._fallback.list_assets(session_id)

    def list_artifacts(self, session_id: str) -> List[Dict[str, Any]]:
        if self._use_fallback():
            return self._fallback.list_artifacts(session_id)
        try:
            cursor = self._artifacts.find({"session_id": session_id}).sort("created_at", 1)  # type: ignore[arg-type]
            docs = self._run(cursor.to_list(length=2000))
            return [self._cleanup_artifact(doc) for doc in docs]
        except Exception:
            return self._fallback.list_artifacts(session_id)

    def artifact_snapshot(self, session_id: str):
        if self._use_fallback():
            return self._fallback.artifact_snapshot(session_id)
        try:
            static = self.list_artifacts(session_id)
            cursor = self._live.find({"session_id": session_id}).sort("created_at", 1)  # type: ignore[arg-type]
            live_docs = self._run(cursor.to_list(length=MAX_LIVE_ARTIFACTS))
            artifacts = static + [self._cleanup_live(doc) for doc in live_docs]
            session = self._run(
                self._sessions.find_one({"session_id": session_id}, {"artifact_revision": 1})  # type: ignore[arg-type]
            )
            revision = int(session.get("artifact_revision", 0)) if session else 0
            return artifacts, revision
        except Exception:
            return self._fallback.artifact_snapshot(session_id)

    def update_session_metadata(self, session_id: str, metadata: Dict[str, Any]) -> AcceleratorSession:
        if self._use_fallback():
            return self._fallback.update_session_metadata(session_id, metadata)
        try:
            updated = self._run(
                self._sessions.find_one_and_update(  # type: ignore[call-arg]
                    {"session_id": session_id},
                    {"$set": {"metadata": dict(metadata or {})}},
                    return_document=True,
                )
            )
            if not updated:
                raise KeyError("Session not found")
            return self._to_session(updated)
        except KeyError:
            raise
        except Exception:
            return self._fallback.update_session_metadata(session_id, metadata)

    def promote_session(self, session_id: str, project_id: str) -> Optional[AcceleratorSession]:
        if self._use_fallback():
            return self._fallback.promote_session(session_id, project_id)
        try:
            now = self._now_iso()
            updated = self._run(
                self._sessions.find_one_and_update(  # type: ignore[call-arg]
                    {"session_id": session_id},
                    {"$set": {"project_id": project_id, "promoted_at": now}},
                    return_document=True,
                )
            )
            return self._to_session(updated) if updated else None
        except Exception:
            return self._fallback.promote_session(session_id, project_id)

    def update_persona(self, session_id: str, persona: Optional[str]) -> AcceleratorSession:
        if self._use_fallback():
            return self._fallback.update_persona(session_id, persona)
        try:
            updated = self._run(
                self._sessions.find_one_and_update(  # type: ignore[call-arg]
                    {"session_id": session_id},
                    {"$set": {"persona": persona}},
                    return_document=True,
                )
            )
            if not updated:
                raise KeyError("Session not found")
            return self._to_session(updated)
        except KeyError:
            raise
        except Exception:
            return self._fallback.update_persona(session_id, persona)

    def add_attachment(self, session_id: str, attachment: Dict[str, Any]) -> Dict[str, Any]:
        if self._use_fallback():
            return self._fallback.add_attachment(session_id, attachment)
        payload = dict(attachment or {})
        payload.setdefault("id", str(uuid.uuid4()))
        payload.setdefault("uploaded_at", self._now_iso())
        payload["session_id"] = session_id
        try:
            self._run(
                self._attachments.insert_one(payload)  # type: ignore[arg-type]
            )
            self._refresh_attachment_metadata(session_id)
            return self._public_attachment(payload)
        except Exception:
            return self._fallback.add_attachment(session_id, attachment)

    def get_attachment(self, session_id: str, attachment_id: str) -> Optional[Dict[str, Any]]:
        if self._use_fallback():
            return self._fallback.get_attachment(session_id, attachment_id)
        try:
            doc = self._run(
                self._attachments.find_one({"session_id": session_id, "id": attachment_id})  # type: ignore[arg-type]
            )
            if not doc:
                return None
            return self._public_attachment(doc)
        except Exception:
            return self._fallback.get_attachment(session_id, attachment_id)

    def list_attachments(self, session_id: str) -> List[Dict[str, Any]]:
        if self._use_fallback():
            return self._fallback.list_attachments(session_id)
        try:
            cursor = self._attachments.find({"session_id": session_id}).sort("uploaded_at", 1)  # type: ignore[arg-type]
            docs = self._run(cursor.to_list(length=200))
            return [self._public_attachment(doc) for doc in docs]
        except Exception:
            return self._fallback.list_attachments(session_id)

    def attachment_count(self, session_id: str) -> int:
        if self._use_fallback():
            return self._fallback.attachment_count(session_id)
        try:
            return int(
                self._run(self._attachments.count_documents({"session_id": session_id}))  # type: ignore[arg-type]
            )
        except Exception:
            return self._fallback.attachment_count(session_id)

    def remove_attachment(self, session_id: str, attachment_id: str) -> None:
        if self._use_fallback():
            self._fallback.remove_attachment(session_id, attachment_id)
            return
        try:
            self._run(
                self._attachments.delete_one({"session_id": session_id, "id": attachment_id})  # type: ignore[arg-type]
            )
            self._refresh_attachment_metadata(session_id)
        except Exception:
            self._fallback.remove_attachment(session_id, attachment_id)

    def attachment_text_map(self, session_id: str) -> Dict[str, str]:
        if self._use_fallback():
            return self._fallback.attachment_text_map(session_id)
        try:
            cursor = self._attachments.find({"session_id": session_id})  # type: ignore[arg-type]
            docs = self._run(cursor.to_list(length=200))
            mapping: Dict[str, str] = {}
            for doc in docs:
                text = doc.get("text")
                if not text:
                    continue
                name = (doc.get("filename") or doc.get("id") or "attachment").strip()
                mapping[str(name)] = str(text)
            return mapping
        except Exception:
            return self._fallback.attachment_text_map(session_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _use_fallback(self) -> bool:
        return (
            self._sessions is None
            or self._messages is None
            or self._artifacts is None
            or self._live is None
            or self._attachments is None
            or self._assets is None
        )

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

    def _now_iso(self) -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    def _ensure_indexes(self) -> None:
        if self._sessions is None:
            return
        try:
            self._run(self._sessions.create_index("session_id", unique=True))
            self._run(self._sessions.create_index("created_at"))
            self._run(self._messages.create_index("session_id"))  # type: ignore[arg-type]
            self._run(self._messages.create_index("created_at"))  # type: ignore[arg-type]
            self._run(self._artifacts.create_index([("session_id", 1), ("created_at", 1)]))  # type: ignore[arg-type]
            self._run(self._live.create_index([("session_id", 1), ("created_at", 1)]))  # type: ignore[arg-type]
            self._run(self._attachments.create_index([("session_id", 1), ("uploaded_at", 1)]))  # type: ignore[arg-type]
            self._run(self._assets.create_index([("session_id", 1), ("filename", 1)], unique=True))  # type: ignore[arg-type]
        except Exception:
            pass

    def _to_session(self, doc: Dict[str, Any]) -> AcceleratorSession:
        metadata = dict(doc.get("metadata") or {})
        return AcceleratorSession(
            accelerator_id=str(doc.get("accelerator_id")),
            session_id=str(doc.get("session_id")),
            created_by=str(doc.get("created_by")),
            created_at=str(doc.get("created_at")),
            persona=doc.get("persona"),
            project_id=doc.get("project_id"),
            promoted_at=doc.get("promoted_at"),
            metadata=metadata,
        )

    def _to_message(self, doc: Dict[str, Any]) -> AcceleratorMessage:
        return AcceleratorMessage(
            message_id=str(doc.get("message_id")),
            session_id=str(doc.get("session_id")),
            role=str(doc.get("role")),
            content=str(doc.get("content", "")),
            created_at=str(doc.get("created_at")),
            metadata=doc.get("metadata") or None,
        )

    def _cleanup_artifact(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "filename": doc.get("filename"),
            "project_id": doc.get("project_id"),
            "meta": dict(doc.get("meta") or {}),
            "created_at": doc.get("created_at"),
        }

    def _cleanup_live(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(doc or {})
        payload.pop("_id", None)
        payload.pop("session_id", None)
        return payload

    def _public_attachment(self, attachment: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not attachment:
            return {}
        public = dict(attachment)
        public.pop("_id", None)
        public.pop("text", None)
        public.pop("session_id", None)
        return public

    def _refresh_attachment_metadata(self, session_id: str) -> None:
        snapshot = self.list_attachments(session_id)
        if self._use_fallback():
            return
        try:
            update: Dict[str, Any] = {"metadata.attachments": snapshot}
            if not snapshot:
                update = {"$unset": {"metadata.attachments": ""}}
                self._run(
                    self._sessions.update_one({"session_id": session_id}, update)  # type: ignore[arg-type]
                )
            else:
                self._run(
                    self._sessions.update_one(
                        {"session_id": session_id},
                        {"$set": {"metadata.attachments": snapshot}},
                    )
                )
        except Exception:
            pass

    def _refresh_artifact_metadata(self, session_id: str) -> None:
        artifacts = self.list_artifacts(session_id)
        if self._use_fallback():
            return
        try:
            self._run(
                self._sessions.update_one(
                    {"session_id": session_id},
                    {"$set": {"metadata.artifacts": artifacts}},
                )
            )
        except Exception:
            pass

    def _increment_artifact_revision(self, session_id: str) -> None:
        if self._use_fallback():
            return
        try:
            self._run(
                self._sessions.update_one(
                    {"session_id": session_id},
                    {"$inc": {"artifact_revision": 1}},
                )
            )
        except Exception:
            pass

    def _increment_message_count(self, session_doc: Dict[str, Any], session_id: str) -> int:
        current = session_doc.get("metadata", {}).get("message_count")
        try:
            return int(current or 0) + 1
        except Exception:
            return 1

    def _prune_live_artifacts(self, session_id: str) -> None:
        if self._use_fallback():
            return
        try:
            count = int(
                self._run(self._live.count_documents({"session_id": session_id}))  # type: ignore[arg-type]
            )
            if count <= MAX_LIVE_ARTIFACTS:
                return
            surplus = count - MAX_LIVE_ARTIFACTS
            oldest = self._run(
                self._live.find({"session_id": session_id})
                .sort("created_at", 1)
                .limit(surplus)
                .to_list(length=surplus)
            )
            ids = [doc.get("_id") for doc in oldest if doc.get("_id")]
            if ids:
                self._run(self._live.delete_many({"_id": {"$in": ids}}))
        except Exception:
            pass
