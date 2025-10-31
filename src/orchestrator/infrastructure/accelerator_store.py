from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Dict, List, Optional, Any, Tuple
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
    metadata: Dict[str, Any] | None = None


class InMemoryAcceleratorStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, _Session] = {}
        self._messages: Dict[str, List[_Message]] = {}
        self._artifacts: Dict[str, List[Dict[str, Any]]] = {}
        self._artifact_revisions: Dict[str, int] = {}
        self._attachments: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._assets: Dict[str, Dict[str, bytes]] = {}
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
            self._artifacts[sid] = []
            self._artifact_revisions[sid] = 0
            self._attachments.setdefault(sid, {})
            self._assets.setdefault(sid, {})
            return self._serialize_session(session)

    def get_session(self, session_id: str) -> Optional[AcceleratorSession]:
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                return None
            return self._serialize_session(sess)

    def list_sessions(self, limit: Optional[int] = None) -> List[AcceleratorSession]:
        with self._lock:
            sessions = [self._serialize_session(sess) for sess in self._sessions.values()]
            sessions.sort(key=lambda s: s.created_at, reverse=True)
            if limit is not None:
                sessions = sessions[: max(0, limit)]
            return sessions

    def list_recent_sessions(self, limit: Optional[int] = None) -> List[AcceleratorSession]:
        with self._lock:
            sessions = [self._serialize_session(sess) for sess in self._sessions.values()]

            def sort_key(accel_session: AcceleratorSession) -> str:
                meta = accel_session.metadata or {}
                last_activity = meta.get("last_activity")
                if isinstance(last_activity, str) and last_activity:
                    return last_activity
                return accel_session.created_at

            sessions.sort(key=sort_key, reverse=True)
            if limit is not None:
                sessions = sessions[: max(0, limit)]
            return sessions

    def count_sessions(self) -> int:
        with self._lock:
            return len(self._sessions)

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AcceleratorMessage:
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
                metadata=dict(metadata) if metadata else None,
            )
            self._messages.setdefault(session_id, []).append(message)
            return AcceleratorMessage(
                message_id=message.message_id,
                session_id=message.session_id,
                role=message.role,
                content=message.content,
                created_at=message.created_at,
                metadata=metadata,
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
                        metadata=dict(msg.metadata) if msg.metadata else None,
                    )
                )
            return out

    def add_artifact(self, session_id: str, filename: str, project_id: Optional[str], meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError("Session not found")
            existing = self._artifacts.setdefault(session_id, [])
            sentinel = meta or {}
            for artifact in existing:
                if artifact["filename"] == filename and artifact["meta"].get("version") == sentinel.get("version"):
                    return artifact
            entry = {
                "filename": filename,
                "project_id": project_id,
                "meta": sentinel,
                "created_at": self._now_iso(),
            }
            existing.append(entry)
            sess = self._sessions[session_id]
            sess.metadata.setdefault("artifacts", [])
            sess.metadata["artifacts"] = existing.copy()
            self._sessions[session_id] = sess
            self._artifact_revisions[session_id] = self._artifact_revisions.get(session_id, 0) + 1
            return entry

    def save_asset(self, session_id: str, filename: str, content: bytes) -> None:
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError("Session not found")
            assets = self._assets.setdefault(session_id, {})
            assets[filename] = content

    def get_asset(self, session_id: str, filename: str) -> Optional[bytes]:
        with self._lock:
            return self._assets.get(session_id, {}).get(filename)

    def list_assets(self, session_id: str) -> List[str]:
        with self._lock:
            return list(self._assets.get(session_id, {}).keys())

    def list_artifacts(self, session_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._artifacts.get(session_id, []))

    def artifact_snapshot(self, session_id: str) -> Tuple[List[Dict[str, Any]], int]:
        with self._lock:
            artifacts = list(self._artifacts.get(session_id, []))
            revision = self._artifact_revisions.get(session_id, 0)
            return artifacts, revision

    def update_session_metadata(self, session_id: str, metadata: Dict[str, Any]) -> AcceleratorSession:
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                raise KeyError("Session not found")
            sess.metadata = dict(metadata)
            self._sessions[session_id] = sess
            self._artifact_revisions.setdefault(session_id, 0)
            return self._serialize_session(sess)

    def promote_session(self, session_id: str, project_id: str) -> Optional[AcceleratorSession]:
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                return None
            sess.project_id = project_id
            sess.promoted_at = self._now_iso()
            self._sessions[session_id] = sess
            return self._serialize_session(sess)

    def update_persona(self, session_id: str, persona: Optional[str]) -> AcceleratorSession:
        with self._lock:
            sess = self._sessions.get(session_id)
            if not sess:
                raise KeyError("Session not found")
            sess.persona = persona
            self._sessions[session_id] = sess
            return self._serialize_session(sess)

    def add_attachment(self, session_id: str, attachment: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError("Session not found")
            attachments = self._attachments.setdefault(session_id, {})
            attachments[attachment["id"]] = attachment
            self._refresh_attachment_metadata(session_id)
            return self._public_attachment(attachment)

    def get_attachment(self, session_id: str, attachment_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            att = self._attachments.get(session_id, {}).get(attachment_id)
            return self._public_attachment(att) if att else None

    def list_attachments(self, session_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._public_attachment(att) for att in self._attachments.get(session_id, {}).values()]

    def attachment_count(self, session_id: str) -> int:
        with self._lock:
            return len(self._attachments.get(session_id, {}))

    def remove_attachment(self, session_id: str, attachment_id: str) -> None:
        with self._lock:
            attachments = self._attachments.get(session_id)
            if not attachments or attachment_id not in attachments:
                return
            attachments.pop(attachment_id, None)
            self._refresh_attachment_metadata(session_id)

    def _refresh_attachment_metadata(self, session_id: str) -> None:
        sess = self._sessions.get(session_id)
        if not sess:
            return
        snapshot = [self._public_attachment(att) for att in self._attachments.get(session_id, {}).values()]
        if snapshot:
            sess.metadata.setdefault("attachments", snapshot)
        else:
            sess.metadata.pop("attachments", None)
        self._sessions[session_id] = sess

    def _serialize_session(self, sess: _Session) -> AcceleratorSession:
        metadata = dict(sess.metadata)
        attachments = self._attachments.get(sess.session_id)
        if attachments:
            metadata["attachments"] = [self._public_attachment(att) for att in attachments.values()]
        return AcceleratorSession(
            accelerator_id=sess.accelerator_id,
            session_id=sess.session_id,
            created_by=sess.created_by,
            created_at=sess.created_at,
            persona=sess.persona,
            project_id=sess.project_id,
            promoted_at=sess.promoted_at,
            metadata=metadata,
        )

    def attachment_text_map(self, session_id: str) -> Dict[str, str]:
        with self._lock:
            attachments = self._attachments.get(session_id, {})
            mapping: Dict[str, str] = {}
            for att in attachments.values():
                text = att.get("text")
                if not text:
                    continue
                name = (att.get("filename") or att.get("id") or "attachment").strip() or att.get("id")
                mapping[str(name)] = str(text)
            return mapping

    def _public_attachment(self, attachment: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not attachment:
            return {}
        public = dict(attachment)
        public.pop("text", None)
        return public


_store: InMemoryAcceleratorStore | None = None


def get_accelerator_store() -> InMemoryAcceleratorStore:
    global _store
    if _store is None:
        _store = InMemoryAcceleratorStore()
    return _store
