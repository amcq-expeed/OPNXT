from __future__ import annotations

from typing import List, Dict, Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query

from ...security.rbac import require_permission, Permission
from ...security.auth import User
from ...domain.chat_models import (
    ChatSessionCreate,
    GuestChatSessionCreate,
    ChatSession,
    ChatMessageCreate,
    ChatMessage,
    ChatSessionWithMessages,
    ChatModelOption,
    ChatSearchHit,
    ChatTemplate,
)
from ...infrastructure.chat_store import get_chat_store
from ...infrastructure.repository import get_repo
from ...infrastructure.doc_store import get_doc_store
from ...services.chat_ai import reply_with_chat_ai
from ...services.model_router import ModelRouter


def _unique_models(values: List[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        if not value:
            continue
        trimmed = value.strip()
        if not trimmed or trimmed in seen:
            continue
        seen.add(trimmed)
        ordered.append(trimmed)
    return ordered


def _provider_label(name: str) -> str:
    if name == "local":
        return "Local cluster"
    if name == "openai":
        return "OpenAI (Hosted)"
    if name == "gemini":
        return "Gemini (Hosted)"
    if name == "xai":
        return "xAI (Hosted)"
    return name.capitalize()


def _build_model_catalog() -> List[ChatModelOption]:
    router = ModelRouter()
    catalog: List[ChatModelOption] = [
        ChatModelOption(
            provider="adaptive",
            model="auto",
            label="Adaptive model: Auto (OPNXT)",
            description="Let OPNXT choose the best model per request.",
            available=True,
            adaptive=True,
        )
    ]
    env = router._env  # type: ignore[attr-defined]
    for provider_name, cfg in router.PROVIDER_CONFIG.items():
        if provider_name in ("search", "adaptive"):
            continue
        try:
            available = router.provider_available(provider_name)
        except Exception:
            available = False

        model_env_values: List[str] = []
        model_env_key = cfg.get("model_env")
        if model_env_key:
            raw = env.get(str(model_env_key), "")
            if raw:
                model_env_values.extend(raw.split(","))

        fallbacks_env_key = cfg.get("fallbacks_env")
        if fallbacks_env_key:
            raw = env.get(str(fallbacks_env_key), "")
            if raw:
                model_env_values.extend(raw.split(","))

        if provider_name == "local":
            fallback_cfg = cfg.get("model_fallbacks")
            if isinstance(fallback_cfg, (list, tuple)):
                model_env_values.extend(str(m) for m in fallback_cfg)

        default_model = cfg.get("default_model")
        if default_model:
            model_env_values.append(str(default_model))

        models = _unique_models(model_env_values)
        if not models:
            continue

        base_label = _provider_label(provider_name)
        description = None
        if provider_name == "local":
            description = "Uses on-prem LLM host." if available else "Local host unavailable."

        for idx, model_name in enumerate(models):
            label = base_label
            if provider_name == "local" or len(models) > 1:
                label = f"{base_label} — {model_name}"
            catalog.append(
                ChatModelOption(
                    provider=provider_name,
                    model=model_name,
                    label=label,
                    description=description if idx == 0 else None,
                    available=available,
                    adaptive=False,
                )
            )

    return catalog

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/models", response_model=List[ChatModelOption])
def list_models(user: User = Depends(require_permission(Permission.PROJECT_READ))) -> List[ChatModelOption]:
    return _build_model_catalog()


_CHAT_CAPABILITY_TEMPLATES: List[ChatTemplate] = [
    ChatTemplate(
        template_id="requirements-refinement",
        title="Requirements Refinement",
        description="Drive deeper requirement discovery with focused prompts across stakeholders, scope, risks, and acceptance criteria.",
        prompt="Let's refine the requirements. Who are the key stakeholders, what scenarios should we support, and what success metrics or KPIs will prove we solved their problem?",
        tags=["requirements", "discovery", "stakeholders"],
    ),
    ChatTemplate(
        template_id="nfr-scan",
        title="NFR Scan",
        description="Assess performance, availability, security, and compliance expectations before committing to design.",
        prompt="Audit the current plan for non-functional requirements. Capture latency, throughput, availability/SLA, security/compliance, and observability expectations.",
        tags=["nfr", "quality", "risk"],
    ),
    ChatTemplate(
        template_id="release-readiness",
        title="Release Readiness",
        description="Validate scope, approvals, and testing plans before advancing phases.",
        prompt="Confirm we are ready for release. Summarize scope, open risks, approvals, outstanding work, and recommended test coverage.",
        tags=["release", "phase-gate", "readiness"],
    ),
]


@router.get("/templates", response_model=List[ChatTemplate])
def list_templates(user: User = Depends(require_permission(Permission.PROJECT_READ))) -> List[ChatTemplate]:
    return _CHAT_CAPABILITY_TEMPLATES


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
        kind="project",
    )
    return sess


@router.post("/guest/sessions", response_model=ChatSessionWithMessages, status_code=status.HTTP_201_CREATED)
def create_guest_session(
    req: GuestChatSessionCreate,
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
) -> ChatSessionWithMessages:
    store = get_chat_store()
    title = req.title or "Quick Start Chat"
    sess = store.create_session(
        project_id=None,
        created_by=user.email,
        title=title,
        persona=req.persona,
        kind="guest",
    )

    messages: List[ChatMessage] = []
    initial = (req.initial_message or "").strip()
    if initial:
        user_msg = store.add_message(sess.session_id, role="user", content=initial)
        messages.append(user_msg)
        assistant_provider = None
        assistant_model = None
        try:
            assistant_reply = reply_with_chat_ai(
                project_name=sess.title,
                user_message=initial,
                history=[{"role": "user", "content": initial}],
                attachments=None,
                persona=req.persona,
                provider=None if req.provider in (None, "adaptive", "auto") else req.provider,
                model=req.model,
            )
            if isinstance(assistant_reply, dict):
                assistant_text = str(assistant_reply.get("text", ""))
                assistant_provider = assistant_reply.get("provider")
                assistant_model = assistant_reply.get("model")
            else:
                assistant_text = str(assistant_reply)
        except Exception as e:
            assistant_text = f"I'm having trouble generating a response: {e}. Please try again."
        assistant_msg = store.add_message(
            sess.session_id,
            role="assistant",
            content=assistant_text,
            metadata={
                "provider": assistant_provider,
                "model": assistant_model,
            },
        )
        messages.append(assistant_msg)

    return ChatSessionWithMessages(session=sess, messages=messages or store.list_messages(sess.session_id))


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


@router.get("/search", response_model=List[ChatSearchHit])
def search_messages(
    q: str = Query(..., min_length=2, alias="query"),
    project_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
) -> List[ChatSearchHit]:
    store = get_chat_store()
    results = store.search_messages(q, project_id=project_id, limit=limit)
    return [
        ChatSearchHit(session=session, message=message, snippet=snippet)
        for session, message, snippet in results
    ]


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
def post_message(
    session_id: str,
    msg: ChatMessageCreate,
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
) -> ChatMessage:
    store = get_chat_store()
    sess = store.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    repo = get_repo()
    proj = repo.get(sess.project_id) if sess.project_id else None
    if sess.project_id:
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")
        # Ensure caller has write access for project-backed chat
        require_permission(Permission.PROJECT_WRITE)(user)

    # Record user message
    user_msg = store.add_message(session_id, role="user", content=msg.content)

    if not sess.persona:
        inferred = _infer_persona(msg.content)
        if inferred:
            try:
                sess = store.update_session_persona(session_id, inferred)
            except KeyError:
                pass

    attachments: Dict[str, str] = {}
    if sess.project_id:
        try:
            doc_store = get_doc_store()
            listing = doc_store.list_documents(sess.project_id) or {}
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
    assistant_provider = None
    assistant_model = None
    try:
        assistant_reply = reply_with_chat_ai(
            project_name=proj.name if proj else sess.title,
            user_message=msg.content,
            history=history,
            attachments=attachments,
            persona=sess.persona,
            provider=None if msg.provider in (None, "adaptive", "auto") else msg.provider,
            model=msg.model,
        )
        if isinstance(assistant_reply, dict):
            assistant_text = str(assistant_reply.get("text", ""))
            assistant_provider = assistant_reply.get("provider")
            assistant_model = assistant_reply.get("model")
        else:
            assistant_text = str(assistant_reply)
    except Exception as e:
        # Shouldn't happen; fallback handles it, but guard just in case
        assistant_text = f"I'm having trouble generating a response: {e}. Please try again."

    assistant_msg = store.add_message(
        session_id,
        role="assistant",
        content=assistant_text,
        metadata={
            "provider": assistant_provider,
            "model": assistant_model,
        },
    )
    return assistant_msg
