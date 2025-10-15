from __future__ import annotations

from typing import List, Dict, Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query

from ...security.rbac import require_permission, Permission
from ...security.auth import User
from ...domain.chat_models import (
    ChatSessionCreate,
    ChatSession,
    ChatMessageCreate,
    ChatMessage,
    ChatSessionWithMessages,
)
from ...infrastructure.chat_store import get_chat_store
from ...infrastructure.repository import get_repo
from ...infrastructure.doc_store import get_doc_store
from ...services.chat_ai import reply_with_chat_ai

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/sessions", response_model=ChatSession, status_code=status.HTTP_201_CREATED)
def create_session(req: ChatSessionCreate, user: User = Depends(require_permission(Permission.PROJECT_WRITE))) -> ChatSession:
    repo = get_repo()
    proj = repo.get(req.project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    store = get_chat_store()
    sess = store.create_session(
        project_id=req.project_id,
        created_by=user.email,
        title=req.title,
        persona=req.persona,
    )
    return sess


@router.get("/sessions", response_model=List[ChatSession])
def list_sessions(project_id: str = Query(...), user: User = Depends(require_permission(Permission.PROJECT_READ))) -> List[ChatSession]:
    repo = get_repo()
    proj = repo.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    store = get_chat_store()
    return store.list_sessions(project_id)


@router.get("/sessions/{session_id}", response_model=ChatSessionWithMessages)
def get_session(session_id: str, user: User = Depends(require_permission(Permission.PROJECT_READ))) -> ChatSessionWithMessages:
    store = get_chat_store()
    sess = store.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    msgs = store.list_messages(session_id)
    return ChatSessionWithMessages(session=sess, messages=msgs)


@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessage])
def list_messages(session_id: str, user: User = Depends(require_permission(Permission.PROJECT_READ))) -> List[ChatMessage]:
    store = get_chat_store()
    sess = store.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return store.list_messages(session_id)


def _infer_persona(text: str) -> Optional[str]:
    haystack = (text or "").lower()
    persona_keywords = {
        "architect": {"architecture", "system design", "architect", "solution"},
        "product": {"product", "roadmap", "market", "customer"},
        "qa": {"testing", "qa", "quality assurance", "defect"},
        "developer": {"code", "api", "implementation", "dev"},
        "executive": {"vision", "strategy", "executive", "roi"},
    }
    for persona, keywords in persona_keywords.items():
        if any(word in haystack for word in keywords):
            return persona
    return None


@router.post("/sessions/{session_id}/messages", response_model=ChatMessage)
def post_message(session_id: str, msg: ChatMessageCreate, user: User = Depends(require_permission(Permission.PROJECT_WRITE))) -> ChatMessage:
    store = get_chat_store()
    sess = store.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    # Verify project exists and user has access (already enforced by permission, but double-check)
    repo = get_repo()
    proj = repo.get(sess.project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    # Record user message
    user_msg = store.add_message(session_id, role="user", content=msg.content)

    if not sess.persona:
        inferred = _infer_persona(msg.content)
        if inferred:
            try:
                sess = store.update_session_persona(session_id, inferred)
            except KeyError:
                pass

    # Prepare attachments from latest documents for context
    attachments: Dict[str, str] = {}
    try:
        doc_store = get_doc_store()
        listing = doc_store.list_documents(sess.project_id) or {}
        # Prefer core docs first
        preferred = {"ProjectCharter.md", "SRS.md", "SDD.md", "TestPlan.md"}
        candidates = list(listing.keys())
        for fname in sorted(candidates, key=lambda f: (f not in preferred, f)):
            vers = listing.get(fname) or []
            if not vers:
                continue
            last_ver = int(vers[-1].get("version", 0))
            dv = doc_store.get_document(sess.project_id, fname, version=last_ver)
            if dv and isinstance(dv.content, str) and dv.content.strip():
                attachments[fname] = dv.content
    except Exception:
        attachments = {}

    # Build short chat history (last 8 messages)
    hist_msgs = store.list_messages(session_id)[-8:]
    history = [{"role": m.role, "content": m.content} for m in hist_msgs]

    # Generate assistant reply (LLM or fallback)
    try:
        assistant_text = reply_with_chat_ai(
            project_name=proj.name,
            user_message=msg.content,
            history=history,
            attachments=attachments,
            persona=sess.persona,
        )
    except Exception as e:
        # Shouldn't happen; fallback handles it, but guard just in case
        assistant_text = f"I'm having trouble generating a response: {e}. Please try again."

    assistant_msg = store.add_message(session_id, role="assistant", content=assistant_text)
    return assistant_msg
