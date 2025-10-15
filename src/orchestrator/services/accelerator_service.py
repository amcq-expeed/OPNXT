from __future__ import annotations

from collections import Counter, defaultdict
import logging
from typing import Optional, Tuple, List

from ..domain.chat_intents import ChatIntent
from ..domain.accelerator_session import AcceleratorSession, AcceleratorMessage
from ..domain.models import ProjectCreate, Project
from ..infrastructure.accelerator_store import get_accelerator_store
from ..infrastructure.repository import get_repo
from ..services.catalog_service import get_intent
from ..services.chat_ai import reply_with_chat_ai
from ..services.telemetry_sink import record_event, TelemetryEvent
from ..security.auth import User


logger = logging.getLogger("opnxt.accelerator")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("[OPNXT][%(levelname)s] %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def _get_first_name(user: Optional[User]) -> str:
    if not user or not user.name:
        return "there"
    return user.name.split()[0]


def _build_intro_message(intent: ChatIntent, user: Optional[User], persona: Optional[str]) -> str:
    first_name = _get_first_name(user)
    deliverables = ", ".join(intent.deliverables) if intent.deliverables else None
    focus = intent.requirement_area or intent.group or "this initiative"

    lines: List[str] = []
    lines.append(f"{intent.title} — Document Readiness Kickoff")
    lines.append("")
    lines.append("What we'll assemble:")
    if deliverables:
        lines.append(f"- {deliverables}")
    else:
        lines.append("- Charter, requirements outline, draft solution notes, and a test readiness checklist")
    if intent.opnxt_benefit:
        lines.append(f"- Why it matters: {intent.opnxt_benefit}")

    lines.append("")
    lines.append("To start drafting immediately, help us confirm:")
    lines.append(f"- Core problem and desired outcomes for {focus.lower()}.")
    lines.append("- Primary personas/stakeholders and how success will be measured.")
    lines.append("- Critical constraints, dependencies, and timelines we must respect.")
    if persona:
        lines.append(f"- Any {persona.title()}-specific considerations we should keep front and center.")

    lines.append("")
    lines.append("Once these are captured, we can:")
    lines.append("- Draft the full document set for your review.")
    lines.append("- Highlight risk areas and propose delivery checkpoints to keep scope controlled.")

    lines.append("")
    lines.append(f"Ready when you are, {first_name}. Share what you already know, even if it's rough notes — we'll organize it and generate the artifacts.")

    return "\n".join(lines)


def _infer_persona(text: str) -> Tuple[Optional[str], List[str]]:
    haystack = (text or "").lower()
    if not haystack:
        return None, []

    persona_keywords = {
        "architect": {"architecture", "system design", "architect", "solution", "platform", "integration", "systems"},
        "product": {"roadmap", "product", "portfolio", "market", "persona", "feature", "launch", "backlog", "customer", "self-service", "dashboard", "adoption", "experience"},
        "qa": {"testing", "qa", "quality assurance", "defect", "test plan", "test case", "acceptance", "validation"},
        "developer": {"code", "api", "implementation", "dev", "sdk", "repository", "deployment", "integration"},
        "executive": {"vision", "strategy", "executive", "roi", "budget", "c-suite", "board", "investment"},
        "operations": {"support", "operations", "runbook", "incident", "uptime", "monitoring", "service desk", "ticket"},
        "people": {"employee", "hr", "human resources", "people", "talent", "payroll", "benefits", "onboarding", "retention"},
    }

    scores = Counter()
    matched = defaultdict(set)
    for persona, keywords in persona_keywords.items():
        for word in keywords:
            if word in haystack:
                scores[persona] += 1
                matched[persona].add(word)

    if not scores:
        return None, []

    best_persona, best_score = scores.most_common(1)[0]
    strong_triggers = {
        "roadmap",
        "payroll",
        "benefits",
        "runbook",
        "architecture",
        "roi",
        "employee",
        "dashboard",
        "self-service",
        "experience",
    }
    if best_score >= 2:
        return best_persona, sorted(matched[best_persona])

    for persona, hits in matched.items():
        if strong_triggers & hits:
            return persona, sorted(hits)

    return best_persona, sorted(matched[best_persona])


def launch_accelerator_session(intent_id: str, user: User, persona: Optional[str] = None) -> Tuple[AcceleratorSession, List[AcceleratorMessage], ChatIntent]:
    intent = get_intent(intent_id)
    if not intent:
        raise ValueError("Unknown accelerator intent")

    store = get_accelerator_store()
    metadata = {
        "intent_id": intent.intent_id,
        "intent_title": intent.title,
        "requirement_area": intent.requirement_area,
        "core_functionality": intent.core_functionality,
        "opnxt_benefit": intent.opnxt_benefit,
    }
    session = store.create_session(
        accelerator_id=intent.intent_id,
        created_by=user.email,
        persona=persona,
        metadata=metadata,
    )

    prefill = (intent.prefill_prompt or "").strip()
    message_batch: List[AcceleratorMessage] = []

    if prefill:
        synthetic_prompt = prefill
        user_message = store.add_message(session.session_id, role="user", content=synthetic_prompt)
        message_batch.append(user_message)
        assistant_text = reply_with_chat_ai(
            project_name=intent.title,
            user_message=synthetic_prompt,
            history=[{"role": "user", "content": synthetic_prompt}],
            attachments=None,
            persona=persona,
        )
        if not assistant_text.strip():
            assistant_text = _build_intro_message(intent, user, persona)
        intro_message = store.add_message(session.session_id, role="assistant", content=assistant_text)
        message_batch.append(intro_message)
    else:
        intro = _build_intro_message(intent, user, persona)
        intro_message = store.add_message(session.session_id, role="assistant", content=intro)
        message_batch.append(intro_message)

    record_event(
        TelemetryEvent(
            name="accelerator_session_started",
            actor=user.email,
            properties={
                "intent_id": intent.intent_id,
                "persona": persona,
            },
        )
    )

    return session, message_batch, intent


def load_accelerator_context(session_id: str) -> Tuple[AcceleratorSession, ChatIntent, List[AcceleratorMessage]]:
    store = get_accelerator_store()
    session = store.get_session(session_id)
    if not session:
        raise ValueError("Session not found")
    metadata = session.metadata or {}
    intent_id = metadata.get("intent_id") or session.accelerator_id
    intent = get_intent(intent_id)
    if not intent:
        raise ValueError("Accelerator intent metadata missing")
    messages = store.list_messages(session_id)
    return session, intent, messages


def post_accelerator_message(session_id: str, content: str, user: User) -> AcceleratorMessage:
    if not content or not content.strip():
        raise ValueError("Message content required")
    store = get_accelerator_store()
    session = store.get_session(session_id)
    if not session:
        raise ValueError("Session not found")

    trimmed = content.strip()
    store.add_message(session_id, role="user", content=trimmed)
    metadata = session.metadata or {}
    title = metadata.get("intent_title") or metadata.get("intent_id") or "Accelerator"

    inferred, matched_keywords = _infer_persona(trimmed)
    logger.info(
        "accelerator_persona_inference session=%s existing=%s candidate=%s keywords=%s",
        session_id,
        session.persona,
        inferred,
        matched_keywords,
    )
    if inferred and inferred != session.persona:
        try:
            old_persona = session.persona
            session = store.update_persona(session_id, inferred)
            logger.info(
                "accelerator_persona_updated session=%s old=%s new=%s keywords=%s",
                session_id,
                old_persona,
                inferred,
                matched_keywords,
            )
        except KeyError:
            pass

    history = [
        {"role": msg.role, "content": msg.content}
        for msg in store.list_messages(session_id)[-8:]
    ]
    assistant_text = reply_with_chat_ai(
        project_name=title,
        user_message=trimmed,
        history=history,
        attachments=None,
        persona=session.persona,
    )
    assistant = store.add_message(session_id, role="assistant", content=assistant_text)

    record_event(
        TelemetryEvent(
            name="accelerator_message_posted",
            actor=user.email,
            properties={
                "session_id": session_id,
                "intent_id": metadata.get("intent_id"),
                "persona": session.persona,
            },
        )
    )

    return assistant


def promote_accelerator_session(
    session_id: str,
    user: User,
    *,
    project_id: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Tuple[AcceleratorSession, Project]:
    store = get_accelerator_store()
    session = store.get_session(session_id)
    if not session:
        raise ValueError("Session not found")

    metadata = session.metadata or {}
    intent = get_intent(metadata.get("intent_id") or session.accelerator_id)

    repo = get_repo()
    project: Optional[Project] = None
    if project_id:
        project = repo.get(project_id)
        if not project:
            raise ValueError("Project not found")
    else:
        default_name = name or (intent.title if intent else "Accelerator Project")
        default_description = description or (intent.description if intent else "")
        payload = ProjectCreate(
            name=default_name[:120],
            description=default_description[:1000],
            type=metadata.get("requirement_area"),
            methodology=None,
            features=f"Accelerator:{metadata.get('intent_id', session.accelerator_id)}",
        )
        project = repo.create(payload)

    promoted_session = store.promote_session(session_id, project.project_id)
    if not promoted_session:
        raise ValueError("Unable to promote session")

    record_event(
        TelemetryEvent(
            name="accelerator_session_promoted",
            actor=user.email,
            properties={
                "session_id": session_id,
                "project_id": project.project_id,
                "intent_id": promoted_session.metadata.get("intent_id") if promoted_session.metadata else None,
            },
        )
    )

    return promoted_session, project
