from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple, Protocol
import os
import uuid

from ..domain.chat_models import ChatSession, ChatMessage


# --- v1.0 update ---
class ChatStore(Protocol):
    def create_session(self, project_id: Optional[str], created_by: str, title: Optional[str] = None, persona: Optional[str] = None, kind: str = "project") -> ChatSession: ...

    def list_sessions(self, project_id: str) -> List[ChatSession]: ...

    def list_recent_sessions(self, limit: int = 10) -> List[ChatSession]: ...

    def list_guest_sessions(self) -> List[ChatSession]: ...

    def count_sessions(self) -> int: ...

    def get_session(self, session_id: str) -> Optional[ChatSession]: ...

    def update_session_persona(self, session_id: str, persona: Optional[str]) -> ChatSession: ...

    def add_message(self, session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> ChatMessage: ...

    def list_messages(self, session_id: str) -> List[ChatMessage]: ...

    def search_messages(self, query: str, project_id: Optional[str] = None, limit: int = 20) -> List[Tuple[ChatSession, ChatMessage, str]]: ...


@dataclass
class _Session:
    session_id: str
    project_id: Optional[str]
    title: str
    created_at: str
    updated_at: str
    created_by: str
    persona: Optional[str]


@dataclass
class _Message:
    message_id: str
    session_id: str
    role: str
    content: str
    created_at: str
    metadata: Dict[str, Any] | None = None


class InMemoryChatStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, _Session] = {}
        self._by_project: Dict[str, List[str]] = {}
        self._guest_sessions: List[str] = []
        self._messages: Dict[str, List[_Message]] = {}
        self._lock = RLock()

    def _now_iso(self) -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    def _session_kind(self, sess: _Session) -> str:
        return "guest" if not sess.project_id else "project"

    def _session_model(self, sess: _Session) -> ChatSession:
        return ChatSession(**sess.__dict__, kind=self._session_kind(sess))

    def _message_model(self, message: _Message) -> ChatMessage:
        return ChatMessage(**message.__dict__)

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

    def create_session(
        self,
        project_id: Optional[str],
        created_by: str,
        title: Optional[str] = None,
        persona: Optional[str] = None,
        kind: str = "project",
    ) -> ChatSession:
        with self._lock:
            sid = uuid.uuid4().hex
            now = self._now_iso()
            sess = _Session(
                session_id=sid,
                project_id=project_id,
                title=title or "Refinement Chat",
                created_at=now,
                updated_at=now,
                created_by=created_by,
                persona=persona,
            )
            self._sessions[sid] = sess
            if project_id:
                self._by_project.setdefault(project_id, []).append(sid)
            else:
                self._guest_sessions.append(sid)
            self._messages[sid] = []
            return self._session_model(sess)

    def list_sessions(self, project_id: str) -> List[ChatSession]:
        with self._lock:
            out: List[ChatSession] = []
            for sid in self._by_project.get(project_id, []):
                sess = self._sessions.get(sid)
                if not sess:
                    continue
                out.append(self._session_model(sess))
            # Newest first
            return sorted(out, key=lambda s: s.updated_at, reverse=True)

    def list_recent_sessions(self, limit: int = 10) -> List[ChatSession]:
        with self._lock:
            sessions = [
                self._session_model(sess)
                for sess in self._sessions.values()
            ]
            sessions.sort(key=lambda s: s.updated_at, reverse=True)
            return sessions[: max(0, limit)]

    def list_guest_sessions(self) -> List[ChatSession]:
        with self._lock:
            out: List[ChatSession] = []
            for sid in self._guest_sessions:
                sess = self._sessions.get(sid)
                if not sess:
                    continue
                out.append(self._session_model(sess))
            return sorted(out, key=lambda s: s.updated_at, reverse=True)

    def count_sessions(self) -> int:
        with self._lock:
            return len(self._sessions)

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                return None
            return self._session_model(sess)

    def update_session_persona(self, session_id: str, persona: Optional[str]) -> ChatSession:
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                raise KeyError("Session not found")
            sess.persona = persona
            self._sessions[session_id] = sess
            kind = "guest" if not sess.project_id else "project"
            return ChatSession(**sess.__dict__, kind=kind)

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ChatMessage:
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError("Session not found")
            mid = uuid.uuid4().hex
            now = self._now_iso()
            msg = _Message(
                message_id=mid,
                session_id=session_id,
                role=role,
                content=content,
                created_at=now,
                metadata=dict(metadata) if metadata else None,
            )
            self._messages.setdefault(session_id, []).append(msg)
            # bump session updated_at
            self._sessions[session_id].updated_at = now
            return self._message_model(msg)

    def list_messages(self, session_id: str) -> List[ChatMessage]:
        with self._lock:
            out: List[ChatMessage] = []
            for m in self._messages.get(session_id, []):
                out.append(self._message_model(m))
            return out

    def search_messages(
        self,
        query: str,
        project_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Tuple[ChatSession, ChatMessage, str]]:
        needle = query.strip().lower()
        if not needle:
            return []
        capped = max(1, min(limit, 50))
        with self._lock:
            matches: List[Tuple[ChatSession, ChatMessage, str]] = []
            if project_id:
                session_ids = list(self._by_project.get(project_id, []))
            else:
                session_ids = list(self._messages.keys())
            for sid in session_ids:
                sess_obj = self._sessions.get(sid)
                if not sess_obj:
                    continue
                msgs = self._messages.get(sid, [])
                for message in reversed(msgs):
                    if needle in message.content.lower():
                        session_model = self._session_model(sess_obj)
                        message_model = self._message_model(message)
                        snippet = self._build_snippet(message.content, needle)
                        matches.append((session_model, message_model, snippet))
                        if len(matches) >= capped:
                            return matches
            return matches


_store: ChatStore | None = None

# --- v1.0 update ---
_db_mode = os.getenv("DB_MODE", "").lower()
_mongo_chat_store_cls = None
if _db_mode == "mongo":
    try:
        from .chat_store_mongo import MongoChatStore as _MongoChatStore  # type: ignore

        _mongo_chat_store_cls = _MongoChatStore
    except Exception:
        _mongo_chat_store_cls = None
_db_mode_mongo_chat_enabled = _db_mode == "mongo" and _mongo_chat_store_cls is not None


def get_chat_store() -> ChatStore:
    global _store
    if _store is not None:
        return _store
    impl = os.getenv("OPNXT_CHAT_STORE_IMPL", "memory").lower()
    if _db_mode_mongo_chat_enabled:
        _store = _mongo_chat_store_cls()  # type: ignore[operator]
        return _store
    if impl == "mongo":
        try:
            from .chat_store_mongo import MongoChatStore  # type: ignore

            _store = MongoChatStore()
            return _store
        except Exception:
            _store = None
    if _store is None:
        _store = InMemoryChatStore()
    return _store
