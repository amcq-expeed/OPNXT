from __future__ import annotations

from collections import Counter, defaultdict
import json
import asyncio
import logging
import textwrap
import time
from threading import Thread
from typing import Optional, Tuple, List, Dict, Any, AsyncGenerator

from ..domain.chat_intents import ChatIntent
from ..domain.accelerator_session import AcceleratorSession, AcceleratorMessage
from ..domain.models import ProjectCreate, Project
from ..infrastructure.accelerator_store import get_accelerator_store
from ..infrastructure.repository import get_repo
from ..services.catalog_service import get_intent
from ..services.chat_ai import reply_with_chat_ai
from ..services.telemetry_sink import record_event, TelemetryEvent, record_metric
from ..security.auth import User
from ..infrastructure.doc_store import get_doc_store


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


def _collect_workspace_snapshot() -> Dict[str, Any]:
    repo = get_repo()
    doc_store = get_doc_store()
    projects: List[Dict[str, Any]] = []
    try:
        project_list = repo.list()
    except Exception:  # pragma: no cover - defensive
        project_list = []

    for project in project_list[:5]:
        try:
            docs = doc_store.list_documents(project.project_id) or {}
        except Exception:  # pragma: no cover - defensive
            docs = {}
        recent_docs: List[Dict[str, Any]] = []
        for fname, versions in list(docs.items())[:5]:
            if not versions:
                continue
            latest = versions[-1]
            recent_docs.append(
                {
                    "filename": fname,
                    "version": latest.get("version"),
                    "created_at": latest.get("created_at"),
                }
            )
        projects.append(
            {
                "project_id": project.project_id,
                "name": project.name,
                "documents": recent_docs,
            }
        )
    return {"projects": projects}


def _default_api_templates(intent: ChatIntent) -> List[Dict[str, Any]]:
    examples = [
        {
            "label": "Order validation (SAP ERP)",
            "description": "Validates proof-of-purchase details and returns eligibility flags.",
            "example": textwrap.dedent(
                """
{
  "method": "POST",
  "url": "https://sap.example.com/api/v1/claims/validate",
  "headers": {
    "Authorization": "Bearer <client-credential-token>",
    "Content-Type": "application/json"
  },
  "body": {
    "receiptNumber": "A1234-5678",
    "sku": "TV-55-UHD",
    "purchaseDate": "2025-02-10",
    "channel": "in-store"
  }
}
                """
            ).strip(),
        },
        {
            "label": "Shipping label creation (FedEx API)",
            "description": "Creates a prepaid label and returns tracking details.",
            "example": textwrap.dedent(
                """
{
  "method": "POST",
  "url": "https://apis.fedex.com/ship/v21/shipments",
  "headers": {
    "X-FedEx-Api-Key": "<key>",
    "X-FedEx-Api-Secret": "<secret>",
    "Content-Type": "application/json"
  },
  "body": {
    "serviceType": "FEDEX_GROUND",
    "shipper": {"postalCode": "43004", "countryCode": "US"},
    "recipient": {"postalCode": "78701", "countryCode": "US"},
    "packages": [{"weight": {"units": "LB", "value": 8}}]
  }
}
                """
            ).strip(),
        },
        {
            "label": "Refund settlement (Stripe)",
            "description": "Issues a partial refund tied to the original payment.",
            "example": textwrap.dedent(
                """
{
  "method": "POST",
  "url": "https://api.stripe.com/v1/refunds",
  "headers": {
    "Authorization": "Bearer sk_live_xxx",
    "Content-Type": "application/x-www-form-urlencoded"
  },
  "form": {
    "payment_intent": "pi_3P123456",
    "amount": 12999,
    "metadata[claim_id]": "RET-2048"
  }
}
                """
            ).strip(),
        },
    ]

    if intent and intent.deliverables:
        deliverable_preview = "\n".join(f"- {d}" for d in intent.deliverables)
        examples.append(
            {
                "label": "Deliverable checklist",
                "description": "Catalog deliverables referenced in this accelerator.",
                "example": deliverable_preview,
            }
        )

    return examples


def _suggested_prompts(intent: ChatIntent, snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
    prompts: List[Dict[str, str]] = []
    focus = intent.requirement_area or intent.title
    prompts.append(
        {
            "id": "flows",
            "label": "Outline customer & associate flows",
            "body": textwrap.dedent(
                f"""
Here are the journeys to cover for {focus}:
• Customer submits request, uploads proof, selects pickup/drop-off, tracks approval
• Associate triages eligibility, issues instant credit, prints shipping label
• Finance & merchandising teams review dashboards for trends, fraud, SLA compliance
Flag any corrections or extra steps we should capture.
                """
            ).strip(),
        }
    )
    prompts.append(
        {
            "id": "nfr",
            "label": "Confirm non-functional guardrails",
            "body": textwrap.dedent(
                """
Non-functional targets we plan to bake into the docs:
• Availability 99.7% with Azure Front Door active-active failover
• Performance <2s median API latency, <3s p95 page load @ 400 sessions
• Compliance: PCI-DSS for refunds, SOC2 logging, encrypted PII at rest, Azure AD SSO with MFA
• Observability: OpenTelemetry tracing, Azure Monitor dashboards, synthetic probes every 5 minutes
Let us know if these align or require adjustments.
                """
            ).strip(),
        }
    )

    if snapshot.get("projects"):
        prompts.append(
            {
                "id": "reuse",
                "label": "Reuse existing artifacts",
                "body": textwrap.dedent(
                    """
We spotted existing workspace documents. Highlight anything we should repurpose so the new drafts stay aligned with prior deliverables.
                    """
                ).strip(),
            }
        )
    return prompts


def _schedule_background_generation(session_id: str, intent: ChatIntent, latest_input: str) -> None:
    store = get_accelerator_store()
    doc_store = get_doc_store()

    def worker():
        time.sleep(1.0)
        try:
            start = time.perf_counter()
            session = store.get_session(session_id)
            if not session:
                return
            artifacts, revision = store.artifact_snapshot(session_id)
            version = revision + 1
            history = [
                {"role": msg.role, "content": msg.content}
                for msg in store.list_messages(session_id)[-12:]
            ]
            prompt = textwrap.dedent(
                f"""
Draft a concise documentation snippet for the accelerator "{intent.title}" based on the latest discussion.
Include key requirements, assumptions, and next steps in markdown.
Latest user input:
{latest_input}
                """
            ).strip()
            draft = reply_with_chat_ai(
                project_name=intent.title,
                user_message=prompt,
                history=history,
                attachments=None,
                persona=session.persona,
            )
            filename = f"{intent.title.lower().replace(' ', '-')}-draft-v{version}.md"
            store.add_artifact(
                session_id,
                filename=filename,
                project_id=session.project_id,
                meta={
                    "version": version,
                    "summary": draft[:240],
                },
            )
            doc_store.save_accelerator_preview(session_id, filename, draft)
            metadata = session.metadata or {}
            metadata.setdefault("artifacts", store.list_artifacts(session_id))
            metadata["last_generated_at"] = time.time()
            store.update_session_metadata(session_id, metadata)
            duration_ms = (time.perf_counter() - start) * 1000.0
            record_metric(
                name="accelerator_artifact_generation_ms",
                value=duration_ms,
                properties={
                    "intent_id": intent.intent_id,
                    "session_id": session_id,
                },
            )
        except Exception:  # pragma: no cover - background guard
            logger.exception("background_generation_failed session=%s", session_id)

    Thread(target=worker, daemon=True).start()


async def stream_accelerator_artifacts(session_id: str, start_revision: int = 0) -> AsyncGenerator[Dict[str, Any], None]:
    store = get_accelerator_store()
    active_counter_name = "accelerator_artifact_stream_active"
    record_metric(
        name=active_counter_name,
        value=1,
        properties={
            "session_id": session_id,
        },
        metric_type="gauge_delta",
    )
    try:
        artifacts, revision = store.artifact_snapshot(session_id)
        yield {
            "revision": revision,
            "artifacts": artifacts,
        }
        while True:
            await asyncio.sleep(1.0)
            artifacts, current_revision = store.artifact_snapshot(session_id)
            if current_revision > revision:
                revision = current_revision
                yield {
                    "revision": revision,
                    "artifacts": artifacts,
                }
    finally:
        record_metric(
            name=active_counter_name,
            value=-1,
            properties={
                "session_id": session_id,
            },
            metric_type="gauge_delta",
        )

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
    snapshot = _collect_workspace_snapshot()
    metadata = {
        "intent_id": intent.intent_id,
        "intent_title": intent.title,
        "requirement_area": intent.requirement_area,
        "core_functionality": intent.core_functionality,
        "opnxt_benefit": intent.opnxt_benefit,
        "workspace_snapshot": snapshot,
        "api_templates": _default_api_templates(intent),
        "suggested_prompts": _suggested_prompts(intent, snapshot),
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
        assistant_reply = reply_with_chat_ai(
            project_name=intent.title,
            user_message=synthetic_prompt,
            history=[{"role": "user", "content": synthetic_prompt}],
            attachments=None,
            persona=persona,
        )
        if isinstance(assistant_reply, dict):
            assistant_text = str(assistant_reply.get("text", ""))
            assistant_provider = assistant_reply.get("provider")
            assistant_model = assistant_reply.get("model")
        else:
            assistant_text = str(assistant_reply)
            assistant_provider = None
            assistant_model = None
        if not assistant_text.strip():
            assistant_text = _build_intro_message(intent, user, persona)
        intro_message = store.add_message(
            session.session_id,
            role="assistant",
            content=assistant_text,
            metadata={
                "provider": assistant_provider,
                "model": assistant_model,
            },
        )
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
    assistant_reply = reply_with_chat_ai(
        project_name=title,
        user_message=trimmed,
        history=history,
        attachments=None,
        persona=session.persona,
    )
    if isinstance(assistant_reply, dict):
        assistant_text = str(assistant_reply.get("text", ""))
        assistant_provider = assistant_reply.get("provider")
        assistant_model = assistant_reply.get("model")
    else:
        assistant_text = str(assistant_reply)
        assistant_provider = None
        assistant_model = None
    assistant = store.add_message(
        session_id,
        role="assistant",
        content=assistant_text,
        metadata={
            "provider": assistant_provider,
            "model": assistant_model,
        },
    )

    doc_store = get_doc_store()
    project_id = session.project_id
    if project_id:
        listing = doc_store.list_documents(project_id)
        latest_artifacts = []
        for fname, versions in listing.items():
            if not versions:
                continue
            latest = versions[-1]
            latest_artifacts.append({
                "filename": fname,
                "version": latest.get("version"),
                "created_at": latest.get("created_at"),
            })
        metadata = session.metadata or {}
        metadata["artifacts"] = latest_artifacts
        store.update_session_metadata(session_id, metadata)

    intent = get_intent(metadata.get("intent_id") or session.accelerator_id)
    if intent:
        _schedule_background_generation(session_id, intent, trimmed)

    record_event(
        TelemetryEvent(
            name="accelerator_message_posted",
            actor=user.email,
            properties={
                "session_id": session_id,
                "intent_id": metadata.get("intent_id"),
                "persona": session.persona,
                "model_provider": assistant_provider,
                "model_name": assistant_model,
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
