from __future__ import annotations

from typing import List, Dict, Optional, Tuple
import os
import re
import requests
import logging

from .model_router import ModelRouter, ProviderSelection

# Optional import: langchain-openai
try:
    from langchain_openai import ChatOpenAI  # type: ignore
except Exception:  # pragma: no cover - optional import
    ChatOpenAI = None  # type: ignore


logger = logging.getLogger(__name__)


DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "xai": "https://api.x.ai/v1",
    "local": "http://127.0.0.1:11434",
}


def _determine_purpose(user_message: str) -> str:
    if user_message.strip().lower() == "approve":
        return "governance_artifact"
    return "conversation"


def detect_user_intent(user_message: str, history: Optional[List[Dict[str, str]]] = None) -> str:
    """Classify incoming request intent.

    Returns one of ``{"troubleshooting", "documentation", "idea"}`` using simple
    keyword heuristics anchored in leadership requirements. Defaults to ``"idea"``
    when no signal is present so the discovery/charter paths still engage.
    """

    history = history or []
    text_parts: List[str] = []
    if user_message:
        text_parts.append(str(user_message))
    for turn in history[-6:]:
        if not isinstance(turn, dict):
            continue
        content = turn.get("content")
        if isinstance(content, str):
            text_parts.append(content)
    haystack = " ".join(text_parts).lower()

    troubleshooting_terms = (
        "password",
        "reset",
        "forgot",
        "can't log",
        "cannot log",
        "error",
        "stack trace",
        "bug",
        "issue",
        "not working",
        "troubleshoot",
        "support ticket",
        "service desk",
        "outage",
        "incident",
    )
    for term in troubleshooting_terms:
        if term in haystack:
            return "troubleshooting"

    documentation_terms = (
        "project charter",
        "charter",
        "brd",
        "srs",
        "sdd",
        "test plan",
        "documentation",
        "requirements",
        "specification",
        "scope document",
        "business case",
    )
    for term in documentation_terms:
        if term in haystack:
            return "documentation"

    question_match = re.search(r"how do i .*?\?", haystack)
    if question_match:
        return "troubleshooting"

    return "idea"


class LocalLLMClient:
    def __init__(self, base_url: str, model: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def invoke(self, messages: List[Dict[str, str]]):
        logger.debug("LocalLLMClient invoking model=%s base_url=%s", self._model, self._base_url)
        prompt_parts: List[str] = []
        for msg in messages:
            role = msg.get("role", "user").lower()
            content = msg.get("content", "")
            if not content:
                continue
            if role == "system":
                prompt_parts.append(f"[INSTRUCTION]\n{content}\n")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}\n")
            else:
                prompt_parts.append(f"User: {content}\n")
        prompt = "\n".join(prompt_parts).strip()
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }
        try:
            resp = requests.post(
                f"{self._base_url}/api/generate",
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.debug("LocalLLMClient received keys=%s", list(data.keys()))
            return data.get("response") or data.get("text") or ""
        except Exception as exc:  # pragma: no cover - diagnostic path
            logger.exception("LocalLLMClient request failed: base_url=%s model=%s", self._base_url, self._model)
            raise


def _get_llm(
    purpose: str,
    provider: Optional[str] = None,
    model_hint: Optional[str] = None,
) -> Tuple[object, str, str]:
    router = ModelRouter()
    if provider:
        try:
            selection = router.resolve_provider(provider)
        except KeyError:
            raise RuntimeError(f"Unknown provider override: {provider}")
        if model_hint:
            selection = ProviderSelection(
                name=selection.name,
                model=model_hint,
                api_key_env=selection.api_key_env,
                base_url_env=selection.base_url_env,
                default_base_url=selection.default_base_url,
                requires_api_key=selection.requires_api_key,
            )
    else:
        selection = router.select_provider(purpose)

    if selection.name == "search":
        raise RuntimeError("Search provider cannot handle conversational responses")

    if selection.name == "local":
        base_url = DEFAULT_BASE_URLS.get("local") or "http://127.0.0.1:11434"
        if selection.base_url_env:
            base_url = os.getenv(selection.base_url_env, base_url)
        elif selection.default_base_url:
            base_url = selection.default_base_url
        logger.info("Using local LLM provider base_url=%s model=%s", base_url, selection.model)
        return LocalLLMClient(base_url=base_url, model=selection.model), selection.name, selection.model

    if not ChatOpenAI:
        raise RuntimeError("LLM client not available")

    api_key = os.getenv(selection.api_key_env) if selection.api_key_env else None
    if selection.requires_api_key and not api_key:
        raise RuntimeError("LLM not configured")

    base_url = DEFAULT_BASE_URLS.get(selection.name)
    if selection.base_url_env:
        base_url = os.getenv(selection.base_url_env, base_url)
    elif selection.default_base_url:
        base_url = selection.default_base_url

    logger.info(
        "Using remote LLM provider name=%s model=%s base_url=%s",
        selection.name,
        selection.model,
        base_url,
    )
    client = ChatOpenAI(api_key=api_key, base_url=base_url, model=selection.model, temperature=0.2)
    return client, selection.name, selection.model


def _attachment_block(attachments: Optional[Dict[str, str]]) -> str:
    attachments = attachments or {}
    parts: List[str] = []
    for fname, content in attachments.items():
        if not isinstance(content, str) or not content.strip():
            continue
        snippet = content if len(content) <= 12000 else content[:12000] + "\n\n[truncated]"
        parts.append(f"--- BEGIN {fname} ---\n{snippet}\n--- END {fname} ---")
    return "\n\n".join(parts)


def _diagnose_gaps(text: str) -> List[str]:
    """Very simple keyword heuristics to identify missing coverage areas."""
    t = (text or "").lower()
    gaps: List[str] = []
    if not any(k in t for k in ("stakeholder", "user", "persona", "customer", "admin", "operator")):
        gaps.append("stakeholders/users")
    if not any(k in t for k in ("scope", "objective", "goal", "outcome", "success", "kpi", "metric")):
        gaps.append("scope/objectives")
    if not any(k in t for k in ("nfr", "non-functional", "performance", "latency", "throughput", "availability", "reliability", "security", "compliance", "gdpr", "hipaa")):
        gaps.append("non-functional requirements (e.g., performance/security)")
    if not any(k in t for k in ("constraint", "assumption", "risk", "limitation", "budget", "timeline", "deadline")):
        gaps.append("constraints/assumptions/risks")
    if not any(k in t for k in (" ui ", " ux ", "screen", "page", "api", "endpoint", "integration", "webhook")):
        gaps.append("interfaces (UI/API/integrations)")
    if not any(k in t for k in ("test", "qa", "acceptance criteria", "traceability")):
        gaps.append("testing/acceptance criteria")
    if not any(k in t for k in ("data model", "schema", "database", "storage", "retention", "index")):
        gaps.append("data model/retention")
    return gaps


def _suggest_questions(text: str, max_q: int = 3) -> List[str]:
    """Return up to max_q targeted questions based on detected gaps."""
    gaps = _diagnose_gaps(text)
    templates = {
        "stakeholders/users": "Who are the primary users or stakeholders, and what are their goals?",
        "scope/objectives": "What is the main objective and what is explicitly in or out of scope?",
        "non-functional requirements (e.g., performance/security)": "Are there key NFRs (e.g., performance targets, availability, security/compliance)?",
        "constraints/assumptions/risks": "Any constraints, assumptions, or known risks (e.g., budget, timeline, regulations)?",
        "interfaces (UI/API/integrations)": "What interfaces are expected (screens, APIs, integrations, webhooks)?",
        "testing/acceptance criteria": "What acceptance criteria or test scenarios would confirm success?",
        "data model/retention": "What data is involved, and are there storage, schema, or retention needs?",
    }
    out: List[str] = []
    for g in gaps:
        q = templates.get(g)
        if q:
            out.append(q)
        if len(out) >= max_q:
            break
    # If everything seems covered, ask an open-ended refinement question
    if not out:
        out.append("Is there anything about stakeholders, constraints, or success metrics we haven't discussed yet?")
    return out


def _summarize_from_conversation(user_message: str, history: Optional[List[Dict[str, str]]] = None) -> str:
    """Return first-line summary drawn from user content."""

    history = history or []
    text = (user_message or "").strip()
    if not text:
        for turn in reversed(history):
            if (turn.get("role") or "user") == "user":
                content = (turn.get("content") or "").strip()
                if content:
                    text = content
                    break
    if not text:
        return "Capture the core objectives, stakeholders, and success criteria."
    first_line = text.splitlines()[0].strip()
    if len(first_line) > 220:
        first_line = first_line[:217] + "…"
    return first_line


def _fallback_structured_reply(
    user_message: str,
    history: Optional[List[Dict[str, str]]],
    persona: Optional[str],
    attachments: Optional[Dict[str, str]],
) -> str:
    all_turns = history or []
    convo_text_parts = [user_message or ""]
    for turn in all_turns[-6:]:
        content = turn.get("content") if isinstance(turn, dict) else None
        if content:
            convo_text_parts.append(str(content))
    convo_text = "\n".join(filter(None, convo_text_parts))

    summary_line = _summarize_from_conversation(user_message, history)
    gaps = _diagnose_gaps(convo_text)
    questions = _suggest_questions(convo_text)

    lines: List[str] = []
    summary_intro = f"I'm hearing that {summary_line}."
    if gaps:
        summary_intro += f" To refine this and sharpen the vision, let's fill in details on {', '.join(gaps[:2])}."
    lines.append(summary_intro)

    engineering_sentence = "From an engineering standpoint, let's keep feasibility clear and phase the build sensibly."
    if persona:
        engineering_sentence += f" We'll keep the `{persona}` perspective in mind as we shape interfaces and flows."
    if attachments:
        engineering_sentence += " I reviewed the material you shared and will weave any hard constraints into the plan."
    if not gaps:
        engineering_sentence += " Technically this seems on-track; let's validate integrations and data paths next."
    lines.append(engineering_sentence)

    delivery_sentence = "On delivery, I'll map the next moves so we keep momentum without overloading the first release."
    lines.append(delivery_sentence)

    if questions:
        lines.append("Questions we're holding:")
        for i, q in enumerate(questions[:2], 1):
            lines.append(f"{i}) {q}")
    else:
        lines.append("Just confirm what success looks like and we'll press ahead.")

    lines.append("Whenever you're ready, let us know and we'll start drafting the right artifacts—PRDs, requirement sets, or delivery roadmaps.")
    return "\n".join(lines)


def reply_with_chat_ai(
    project_name: str,
    user_message: str,
    history: List[Dict[str, str]] | None = None,
    attachments: Optional[Dict[str, str]] = None,
    persona: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Optional[str] | str]:
    """Return assistant reply using LLM if configured; otherwise a helpful deterministic fallback.

    history: list of {role, content} where role in {system,user,assistant}
    attachments: mapping of filename->content (markdown) to provide context from generated docs
    """
    history = history or []

    intent = detect_user_intent(user_message, history)
    if intent == "troubleshooting":
        try:
            selection = _get_llm("conversation", provider=provider, model_hint=model)
            llm, selected_provider, selected_model = selection
            sys = (
                "You are the OPNXT Support Guide. Provide clear, concise troubleshooting steps. "
                "Acknowledge the issue, outline 2-3 actionable recommendations, and note any risks or escalation paths. "
                "If you need more detail, ask one focused follow-up question. Keep responses under 6 sentences."
            )
            msgs = [{"role": "system", "content": sys}]
            for m in history[-4:]:
                r = m.get("role") or "user"
                c = m.get("content") or ""
                if r not in ("system", "user", "assistant"):
                    r = "user"
                msgs.append({"role": r, "content": c})
            msgs.append({"role": "user", "content": user_message})
            res = llm.invoke(msgs)
            text = res.content if hasattr(res, "content") else str(res)
            return {
                "text": text,
                "provider": selected_provider,
                "model": selected_model,
            }
        except Exception:
            text = (user_message or "").strip()
            lines = ["Let’s tackle this issue step-by-step."]
            if text:
                lines.append(f"I’m hearing: {text.splitlines()[0][:180]}")
            lines.append("Try these next actions:")
            lines.append("1) Reproduce the issue and capture any exact error messages or codes.")
            lines.append("2) Check recent changes (deploys, password updates, configuration tweaks).")
            lines.append("3) If the problem persists, open a support ticket with logs/screenshots for escalation.")
            return {
                "text": "\n".join(lines),
                "provider": None,
                "model": None,
            }

    purpose = _determine_purpose(user_message)

    try:
        selection = _get_llm(purpose, provider=provider, model_hint=model)
        llm, selected_provider, selected_model = selection
        support_mode = persona == "support"
        if support_mode:
            sys_lines = [
                "You are Ava, a friendly OPNXT support specialist. Speak in the first person as a real teammate who is genuinely ready to help.",
                "Start with a warm acknowledgement that mirrors the user's request and show empathy for their situation.",
                "Respond in short paragraphs (2-3 sentences each) with natural phrasing—no headings, no numbered sections, and no corporate jargon.",
                "Offer to partner on the next step, call out what you can do immediately, and invite the user to share any context you still need.",
                "Keep the reply under 6 sentences, mix reassurance with clear actions, and end with an encouraging question to keep the chat going.",
            ]
        else:
            persona_line = (
                f"The primary stakeholder persona is `{persona}`. Tailor tone and guidance to help this persona make confident decisions. "
                if persona
                else ""
            )
            sys_lines = [
                "You are the OPNXT Expert Circle: a collaborative trio of specialists (Maya – Product Strategy, Priya – Engineering Lead, Luis – Delivery Coach).",
                "Respond like a cohesive roundtable, weaving short contributions from each expert so the user feels supported by a team rather than an automated script.",
                "Open with a warm acknowledgement of the user's intent and reflect back the most relevant details they shared.",
                "Anchor every reply in helping the user produce concrete SDLC artifacts (charters, BRDs, SRS, test plans, delivery roadmaps, or implementation builds).",
                "State clearly what artifacts you can draft now, what information is missing, and how close the conversation is to document-ready.",
                "Offer balanced guidance that blends product vision, technical feasibility, and delivery execution while highlighting gaps that would block artifact creation.",
                "When prior context or attachments exist, reference the most pertinent insights and explain how they shape the upcoming documents.",
                "Format every response using Markdown with the following sections in order: '### Executive Summary', '### Readiness & Gaps', '### Recommended Actions', and '### Questions for You'.",
                "Within each section, use concise bullet lists (or numbered lists for questions) and keep sentences crisp and professional.",
                "Do not prefix bullet items with individual persona names; speak as the Expert Circle collectively while indicating which capability is covering each point when relevant.",
                "Each response must summarize what new information the user provided, update the document-readiness status, and either (a) commit to drafting specific artifacts or (b) request the precise next inputs needed.",
                "Make explicit offers to generate the required documents or begin build scaffolding once the user confirms readiness.",
                "Close with an inviting next action plus one or two focused questions that either capture missing requirements or confirm that you should start drafting. Always remind the user they can ask you to generate the documents or proceed to build support.",
                "Avoid rigid templates—use natural paragraphs with short bullet lists when helpful—and keep the entire response under 12 sentences.",
                "Maintain an expert, optimistic, and collaborative tone. Do not use canonical SHALL phrasing; keep it conversational.",
            ]
            if persona_line:
                sys_lines.append(persona_line.strip())
        sys = "\n".join(sys_lines)
        msgs = [{"role": "system", "content": sys}]
        if attachments:
            att = _attachment_block(attachments)
            if att:
                msgs.append({"role": "system", "content": "ATTACHED DOCUMENTS AS CONTEXT:\n" + att})
        for m in history:
            r = m.get("role") or "user"
            c = m.get("content") or ""
            if r not in ("system", "user", "assistant"):
                r = "user"
            msgs.append({"role": r, "content": c})
        msgs.append({"role": "user", "content": user_message})
        res = llm.invoke(msgs)
        text = res.content if hasattr(res, "content") else str(res)
        return {
            "text": text,
            "provider": selected_provider,
            "model": selected_model,
        }
    except Exception as exc:
        logger.exception("LLM invocation failed; falling back to deterministic prompts")
        return {
            "text": _fallback_structured_reply(user_message, history, persona, attachments),
            "provider": None,
            "model": None,
        }
