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
    chat_sessions = chat_store.count_sessions()

    accelerator_store = get_accelerator_store()
    accelerator_sessions = accelerator_store.count_sessions()
    sessions = accelerator_store.list_sessions()
    accelerator_artifacts = 0
    for session in sessions:
        artifacts = session.metadata.get("artifacts", []) if session.metadata else []
        accelerator_artifacts += len(artifacts)

    return WorkspaceSummaryResponse(
        projects=len(projects),
        documents=total_documents,
        chat_sessions=chat_sessions,
        accelerator_sessions=accelerator_sessions,
        accelerator_artifacts=accelerator_artifacts,
    )


@router.get("/workspace/chats/recent", response_model=List[ChatSession])
def workspace_recent_chat_sessions(
    limit: int = Query(10, ge=1, le=50),
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
) -> List[ChatSession]:
    store = get_chat_store()
    return store.list_recent_sessions(limit)
