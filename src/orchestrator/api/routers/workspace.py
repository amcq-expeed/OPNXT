from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ...domain.chat_models import ChatSession
from ...infrastructure.accelerator_store import get_accelerator_store
from ...infrastructure.chat_store import get_chat_store
from ...infrastructure.doc_store import get_doc_store
from ...infrastructure.repository import get_repo
from ...security.auth import User
from ...security.rbac import Permission, require_permission

router = APIRouter(tags=["workspace"])


class WorkspaceSummaryResponse(BaseModel):
    projects: int
    documents: int
    chat_sessions: int
    accelerator_sessions: int
    accelerator_artifacts: int
    accelerator_messages: int
    chat_sessions_raw: int | None = None


class AcceleratorSessionSummary(BaseModel):
    session_id: str
    intent_id: str
    intent_title: str
    created_at: str
    last_activity: str
    persona: str | None
    message_count: int
    artifact_count: int


@router.get("/workspace/summary", response_model=WorkspaceSummaryResponse)
def workspace_summary(
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
) -> WorkspaceSummaryResponse:
    repo = get_repo()
    projects = repo.list()

    doc_store = get_doc_store()
    total_documents = 0
    for project in projects:
        try:
            listing = doc_store.list_documents(project.project_id) or {}
        except Exception:
            listing = {}
        total_documents += len(listing)

    chat_store = get_chat_store()
    chat_sessions_raw = chat_store.count_sessions()

    accelerator_store = get_accelerator_store()
    sessions = accelerator_store.list_sessions()
    accelerator_sessions = len(sessions)
    accelerator_artifacts = 0
    accelerator_messages = 0
    for session in sessions:
        artifacts = session.metadata.get("artifacts", []) if session.metadata else []
        accelerator_artifacts += len(artifacts)
        message_count = session.metadata.get("message_count") if session.metadata else None
        if isinstance(message_count, int):
            accelerator_messages += message_count
        else:
            accelerator_messages += len(accelerator_store.list_messages(session.session_id))

    return WorkspaceSummaryResponse(
        projects=len(projects),
        documents=total_documents,
        chat_sessions=chat_sessions_raw + accelerator_sessions,
        accelerator_sessions=accelerator_sessions,
        accelerator_artifacts=accelerator_artifacts,
        accelerator_messages=accelerator_messages,
        chat_sessions_raw=chat_sessions_raw,
    )


@router.get("/workspace/chats/recent", response_model=List[ChatSession])
def workspace_recent_chat_sessions(
    limit: int = Query(10, ge=1, le=50),
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
) -> List[ChatSession]:
    store = get_chat_store()
    return store.list_recent_sessions(limit)


@router.get("/workspace/accelerators/recent", response_model=List[AcceleratorSessionSummary])
def workspace_recent_accelerator_sessions(
    limit: int = Query(10, ge=1, le=50),
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
) -> List[AcceleratorSessionSummary]:
    store = get_accelerator_store()
    sessions = store.list_recent_sessions(limit)
    summaries: List[AcceleratorSessionSummary] = []
    for session in sessions:
        metadata = session.metadata or {}
        intent_id = metadata.get("intent_id") or session.accelerator_id
        intent_title = metadata.get("intent_title") or intent_id
        last_activity = metadata.get("last_activity") or session.created_at
        message_count = metadata.get("message_count")
        if not isinstance(message_count, int):
            message_count = len(store.list_messages(session.session_id))
        artifacts = metadata.get("artifacts") or []
        summaries.append(
            AcceleratorSessionSummary(
                session_id=session.session_id,
                intent_id=intent_id,
                intent_title=intent_title,
                created_at=session.created_at,
                last_activity=last_activity,
                persona=session.persona,
                message_count=message_count,
                artifact_count=len(artifacts),
            )
        )
    return summaries
