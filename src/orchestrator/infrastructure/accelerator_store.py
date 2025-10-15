from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Dict, List, Optional
import uuid

from ..domain.accelerator_session import AcceleratorSession, AcceleratorMessage


@dataclass
class _Session:
    accelerator_id: str
    session_id: str
    created_by: str
    created_at: str
    persona: Optional[str]
    project_id: Optional[str]
    promoted_at: Optional[str]
    metadata: Dict


@dataclass
class _Message:
    message_id: str
    session_id: str
    role: str
    content: str
    created_at: str


class InMemoryAcceleratorStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, _Session] = {}
        self._messages: Dict[str, List[_Message]] = {}
        self._lock = RLock()

    def _now_iso(self) -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    def create_session(
        self,
        accelerator_id: str,
        created_by: str,
        persona: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> AcceleratorSession:
        with self._lock:
            sid = uuid.uuid4().hex
            now = self._now_iso()
            session = _Session(
                accelerator_id=accelerator_id,
                session_id=sid,
                created_by=created_by,
                created_at=now,
                persona=persona,
                project_id=None,
                promoted_at=None,
                metadata=metadata or {},
            )
            self._sessions[sid] = session
            self._messages[sid] = []
            return AcceleratorSession(
                accelerator_id=session.accelerator_id,
                session_id=session.session_id,
                created_by=session.created_by,
                created_at=session.created_at,
                persona=session.persona,
                project_id=session.project_id,
                promoted_at=session.promoted_at,
                metadata=dict(session.metadata),
            )

    def get_session(self, session_id: str) -> Optional[AcceleratorSession]:
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                return None
            return AcceleratorSession(
                accelerator_id=sess.accelerator_id,
                session_id=sess.session_id,
                created_by=sess.created_by,
                created_at=sess.created_at,
                persona=sess.persona,
                project_id=sess.project_id,
                promoted_at=sess.promoted_at,
                metadata=dict(sess.metadata),
            )

    def add_message(self, session_id: str, role: str, content: str) -> AcceleratorMessage:
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError("Session not found")
            mid = uuid.uuid4().hex
            now = self._now_iso()
            message = _Message(
                message_id=mid,
                session_id=session_id,
                role=role,
                content=content,
                created_at=now,
            )
            self._messages.setdefault(session_id, []).append(message)
            return AcceleratorMessage(
                message_id=message.message_id,
                session_id=message.session_id,
                role=message.role,
                content=message.content,
                created_at=message.created_at,
            )

    def list_messages(self, session_id: str) -> List[AcceleratorMessage]:
        with self._lock:
            out: List[AcceleratorMessage] = []
            for msg in self._messages.get(session_id, []):
                out.append(
                    AcceleratorMessage(
                        message_id=msg.message_id,
                        session_id=msg.session_id,
                        role=msg.role,
                        content=msg.content,
                        created_at=msg.created_at,
                    )
                )
            return out

    def promote_session(self, session_id: str, project_id: str) -> Optional[AcceleratorSession]:
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                return None
            sess.project_id = project_id
            sess.promoted_at = self._now_iso()
            self._sessions[session_id] = sess
            return AcceleratorSession(
                accelerator_id=sess.accelerator_id,
                session_id=sess.session_id,
                created_by=sess.created_by,
                created_at=sess.created_at,
                persona=sess.persona,
                project_id=sess.project_id,
                promoted_at=sess.promoted_at,
                metadata=dict(sess.metadata),
            )

    def update_persona(self, session_id: str, persona: Optional[str]) -> AcceleratorSession:
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                raise KeyError("Session not found")
            sess.persona = persona
            self._sessions[session_id] = sess
            return AcceleratorSession(
                accelerator_id=sess.accelerator_id,
                session_id=sess.session_id,
                created_by=sess.created_by,
                created_at=sess.created_at,
                persona=sess.persona,
                project_id=sess.project_id,
                promoted_at=sess.promoted_at,
                metadata=dict(sess.metadata),
            )


_store: InMemoryAcceleratorStore | None = None


def get_accelerator_store() -> InMemoryAcceleratorStore:
    global _store
    if _store is None:
        _store = InMemoryAcceleratorStore()
    return _store
