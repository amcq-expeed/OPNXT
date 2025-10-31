# --- v1.0 update ---
from __future__ import annotations

# --- v1.0 update ---
import asyncio
from datetime import UTC, datetime
import os
from typing import Any, Dict, List, Optional, Tuple
import uuid

try:  # pragma: no cover - optional dependency
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection  # type: ignore
except Exception:  # pragma: no cover - dependency optional
    AsyncIOMotorClient = None  # type: ignore[misc]
    AsyncIOMotorCollection = None  # type: ignore[misc]

from ..domain.chat_models import ChatSession, ChatMessage


# --- v1.0 update ---
class MongoChatStore:
    def __init__(self) -> None:
        from .chat_store import InMemoryChatStore  # local import to avoid circular dependency

        self._fallback = InMemoryChatStore()
        self._client: AsyncIOMotorClient | None = None
        self._sessions: AsyncIOMotorCollection | None = None
        self._messages: AsyncIOMotorCollection | None = None
        if AsyncIOMotorClient is None:
            return
        try:
            mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
            mongo_db = os.getenv("MONGO_DB", "opnxt")
            self._client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=500)
            self._run(self._client.server_info())
            db = self._client[mongo_db]
            self._sessions = db["chat_sessions"]
            self._messages = db["chat_messages"]
            self._run(self._sessions.create_index("session_id", unique=True))
            self._run(self._sessions.create_index("project_id"))
            self._run(self._sessions.create_index("updated_at"))
            self._run(self._messages.create_index("session_id"))
            self._run(self._messages.create_index("created_at"))
        except Exception:
            self._client = None
            self._sessions = None
            self._messages = None

    # --- v1.0 update ---
    def create_session(
        self,
        project_id: Optional[str],
        created_by: str,
        title: Optional[str] = None,
        persona: Optional[str] = None,
        kind: str = "project",
    ) -> ChatSession:
        if self._use_fallback():
            return self._fallback.create_session(project_id, created_by, title=title, persona=persona, kind=kind)
        session_id = uuid.uuid4().hex
        now = self._now_iso()
        kind_value = kind if kind in {"project", "guest"} else ("guest" if not project_id else "project")
        doc = {
            "session_id": session_id,
            "project_id": project_id,
            "title": title or "Refinement Chat",
            "created_at": now,
            "updated_at": now,
            "created_by": created_by,
            "persona": persona,
            "kind": kind_value,
        }
        try:
            self._run(self._sessions.insert_one(doc))  # type: ignore[arg-type]
        except Exception:
            return self._fallback.create_session(project_id, created_by, title=title, persona=persona, kind=kind)
        return self._to_session(doc)

    # --- v1.0 update ---
    def list_sessions(self, project_id: str) -> List[ChatSession]:
        if self._use_fallback():
            return self._fallback.list_sessions(project_id)
        try:
            cursor = self._sessions.find({"project_id": project_id}).sort("updated_at", -1)  # type: ignore[arg-type]
            docs = self._run(cursor.to_list(length=200))
            return [self._to_session(doc) for doc in docs]
        except Exception:
            return self._fallback.list_sessions(project_id)

    # --- v1.0 update ---
    def list_recent_sessions(self, limit: int = 10) -> List[ChatSession]:
        if self._use_fallback():
            return self._fallback.list_recent_sessions(limit)
        try:
            cursor = self._sessions.find({}).sort("updated_at", -1).limit(limit)  # type: ignore[arg-type]
            docs = self._run(cursor.to_list(length=limit))
            return [self._to_session(doc) for doc in docs]
        except Exception:
            return self._fallback.list_recent_sessions(limit)

    # --- v1.0 update ---
    def list_guest_sessions(self) -> List[ChatSession]:
        if self._use_fallback():
            return self._fallback.list_guest_sessions()
        try:
            cursor = self._sessions.find({"project_id": None}).sort("updated_at", -1)  # type: ignore[arg-type]
            docs = self._run(cursor.to_list(length=200))
            return [self._to_session(doc) for doc in docs]
        except Exception:
            return self._fallback.list_guest_sessions()

    # --- v1.0 update ---
    def count_sessions(self) -> int:
        if self._use_fallback():
            return self._fallback.count_sessions()
        try:
            return int(self._run(self._sessions.count_documents({})))  # type: ignore[call-arg]
        except Exception:
            return self._fallback.count_sessions()

    # --- v1.0 update ---
    def get_session(self, session_id: str) -> Optional[ChatSession]:
        if self._use_fallback():
            return self._fallback.get_session(session_id)
        try:
            doc = self._run(self._sessions.find_one({"session_id": session_id}))  # type: ignore[arg-type]
            if not doc:
                return None
            return self._to_session(doc)
        except Exception:
            return self._fallback.get_session(session_id)

    # --- v1.0 update ---
    def update_session_persona(self, session_id: str, persona: Optional[str]) -> ChatSession:
        if self._use_fallback():
            return self._fallback.update_session_persona(session_id, persona)
        try:
            updated = self._run(
                self._sessions.find_one_and_update(  # type: ignore[call-arg]
                    {"session_id": session_id},
                    {"$set": {"persona": persona, "updated_at": self._now_iso()}},
                    return_document=True,
                )
            )
            if not updated:
                raise KeyError("Session not found")
            return self._to_session(updated)
        except KeyError:
            raise
        except Exception:
            return self._fallback.update_session_persona(session_id, persona)

    # --- v1.0 update ---
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ChatMessage:
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
                self._sessions.update_one(  # type: ignore[call-arg]
                    {"session_id": session_id},
                    {"$set": {"updated_at": now}},
                )
            )
            return self._to_message(doc)
        except KeyError:
            raise
        except Exception:
            return self._fallback.add_message(session_id, role, content, metadata=metadata)

    # --- v1.0 update ---
    def list_messages(self, session_id: str) -> List[ChatMessage]:
        if self._use_fallback():
            return self._fallback.list_messages(session_id)
        try:
            cursor = self._messages.find({"session_id": session_id}).sort("created_at", 1)  # type: ignore[arg-type]
            docs = self._run(cursor.to_list(length=1000))
            return [self._to_message(doc) for doc in docs]
        except Exception:
            return self._fallback.list_messages(session_id)

    # --- v1.0 update ---
    def search_messages(
        self,
        query: str,
        project_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Tuple[ChatSession, ChatMessage, str]]:
        if self._use_fallback():
            return self._fallback.search_messages(query, project_id=project_id, limit=limit)
        needle = (query or "").strip().lower()
        if not needle:
            return []
        try:
            sessions = []
            if project_id:
                cursor = self._sessions.find({"project_id": project_id})  # type: ignore[arg-type]
                sessions = self._run(cursor.to_list(length=500))
            else:
                cursor = self._sessions.find({})  # type: ignore[arg-type]
                sessions = self._run(cursor.to_list(length=500))
            session_map = {doc.get("session_id"): self._to_session(doc) for doc in sessions}
            matches: List[Tuple[ChatSession, ChatMessage, str]] = []
            for sid, session_model in session_map.items():
                cursor = self._messages.find({"session_id": sid}).sort("created_at", -1).limit(100)  # type: ignore[arg-type]
                docs = self._run(cursor.to_list(length=100))
                for doc in docs:
                    content = str(doc.get("content", ""))
                    if needle in content.lower():
                        message_model = self._to_message(doc)
                        snippet = self._build_snippet(content, needle)
                        matches.append((session_model, message_model, snippet))
                        if len(matches) >= limit:
                            return matches
            return matches
        except Exception:
            return self._fallback.search_messages(query, project_id=project_id, limit=limit)

    # --- v1.0 update ---
    def _use_fallback(self) -> bool:
        return self._sessions is None or self._messages is None

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

    # --- v1.0 update ---
    def _now_iso(self) -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    # --- v1.0 update ---
    def _to_session(self, doc: Dict[str, Any]) -> ChatSession:
        data = dict(doc)
        return ChatSession(
            session_id=str(data.get("session_id")),
            project_id=data.get("project_id"),
            title=str(data.get("title", "Refinement Chat")),
            created_at=str(data.get("created_at", self._now_iso())),
            updated_at=str(data.get("updated_at", self._now_iso())),
            created_by=str(data.get("created_by", "unknown@opnxt.local")),
            persona=data.get("persona"),
            kind="guest" if data.get("kind") == "guest" or not data.get("project_id") else "project",
        )

    # --- v1.0 update ---
    def _to_message(self, doc: Dict[str, Any]) -> ChatMessage:
        data = dict(doc)
        return ChatMessage(
            message_id=str(data.get("message_id")),
            session_id=str(data.get("session_id")),
            role=str(data.get("role", "assistant")),
            content=str(data.get("content", "")),
            created_at=str(data.get("created_at", self._now_iso())),
            metadata=data.get("metadata") or {},
        )

    # --- v1.0 update ---
    def _build_snippet(self, text: str, needle: str, radius: int = 60) -> str:
        lowered = text.lower()
        idx = lowered.find(needle)
        if idx == -1:
            snippet = text[: radius * 2].strip()
            return snippet + ("…" if len(text) > len(snippet) else "")
        start = max(0, idx - radius)
        end = min(len(text), idx + len(needle) + radius)
        snippet = text[start:end].strip()
        if start > 0:
            snippet = "…" + snippet
        if end < len(text):
            snippet += "…"
        return snippet
