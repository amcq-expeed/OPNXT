from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Dict, List, Optional
import uuid

from ..domain.chat_models import ChatSession, ChatMessage


@dataclass
class _Session:
    session_id: str
    project_id: str
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


class InMemoryChatStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, _Session] = {}
        self._by_project: Dict[str, List[str]] = {}
        self._messages: Dict[str, List[_Message]] = {}
        self._lock = RLock()

    def _now_iso(self) -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    def create_session(
        self,
        project_id: str,
        created_by: str,
        title: Optional[str] = None,
        persona: Optional[str] = None,
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
            self._by_project.setdefault(project_id, []).append(sid)
            self._messages[sid] = []
            return ChatSession(**sess.__dict__)

    def list_sessions(self, project_id: str) -> List[ChatSession]:
        with self._lock:
            out: List[ChatSession] = []
            for sid in self._by_project.get(project_id, []):
                sess = self._sessions.get(sid)
                if not sess:
                    continue
                out.append(ChatSession(**sess.__dict__))
            # Newest first
            return out

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        with self._lock:
            sess = self._sessions.get(session_id)
            return ChatSession(**sess.__dict__) if sess else None

    def update_session_persona(self, session_id: str, persona: Optional[str]) -> ChatSession:
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                raise KeyError("Session not found")
            sess.persona = persona
            self._sessions[session_id] = sess
            return ChatSession(**sess.__dict__)

    def add_message(self, session_id: str, role: str, content: str) -> ChatMessage:
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError("Session not found")
            mid = uuid.uuid4().hex
            now = self._now_iso()
            msg = _Message(message_id=mid, session_id=session_id, role=role, content=content, created_at=now)
            self._messages.setdefault(session_id, []).append(msg)
            # bump session updated_at
            self._sessions[session_id].updated_at = now
            return ChatMessage(**msg.__dict__)

    def list_messages(self, session_id: str) -> List[ChatMessage]:
        with self._lock:
            out: List[ChatMessage] = []
            for m in self._messages.get(session_id, []):
                out.append(ChatMessage(**m.__dict__))
            return out


_store: InMemoryChatStore | None = None


def get_chat_store() -> InMemoryChatStore:
    global _store
    if _store is None:
        _store = InMemoryChatStore()
    return _store
