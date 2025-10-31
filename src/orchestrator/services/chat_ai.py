from __future__ import annotations

from typing import List, Dict, Optional, Tuple
import os
import re
import requests
import logging
import time  # --- mcp-fix-2 ---
# --- mcp-fix ---
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
# --- opnxt-stream ---
import json
from typing import Iterator, Any

from .model_router import ModelRouter, ProviderSelection

# Optional import: langchain-openai
try:
    from langchain_openai import ChatOpenAI  # type: ignore
except Exception:  # pragma: no cover - optional import
    ChatOpenAI = None  # type: ignore


# --- mcp-fix ---
logger = logging.getLogger(__name__)
LOG = logging.getLogger("opnxt.llm")


# --- mcp-fix-2 ---
_BREAKER_STATE = {"fails": 0, "opened_at": 0.0}
_BREAKER_THRESHOLD = int(os.getenv("OPNXT_LLM_BREAKER_THRESHOLD", "2"))
_BREAKER_COOLDOWN = float(os.getenv("OPNXT_LLM_BREAKER_COOLDOWN", "120.0"))
_BREAKER_PROBE_INTERVAL = float(os.getenv("OPNXT_LLM_BREAKER_PROBE_INTERVAL", "15.0"))
_LAST_BREAKER_PROBE = {"t": 0.0}
# --- opnxt-stream ---
_STREAM_TIMEOUT = (int(os.getenv("OPNXT_LLM_CONNECT_TIMEOUT", "3")), int(os.getenv("OPNXT_LLM_READ_TIMEOUT", "15")))


def _breaker_open() -> bool:
    opened = _BREAKER_STATE["opened_at"]
    if opened == 0.0:
        return False
    if time.time() - opened < _BREAKER_COOLDOWN:
        return True
    _BREAKER_STATE["fails"] = 0
    _BREAKER_STATE["opened_at"] = 0.0
    return False


def _record_fail() -> None:
    _BREAKER_STATE["fails"] += 1
    if _BREAKER_STATE["fails"] >= _BREAKER_THRESHOLD and _BREAKER_STATE["opened_at"] == 0.0:
        _BREAKER_STATE["opened_at"] = time.time()
        LOG.warning(
            "llm_breaker_opened",
            extra={"fails": _BREAKER_STATE["fails"], "cooldown_s": _BREAKER_COOLDOWN},
        )


def _record_success() -> None:
    if _BREAKER_STATE["fails"] or _BREAKER_STATE["opened_at"]:
        LOG.info("llm_breaker_closed")
    _BREAKER_STATE["fails"] = 0
    _BREAKER_STATE["opened_at"] = 0.0


# --- mcp-fix ---
def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["POST", "GET"]),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


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
    # --- mcp-fix ---
    def __init__(self, base_url: str, model: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = os.getenv("OPNXT_LLM_LOCAL_MODEL", model)
        self._timeout = (_STREAM_TIMEOUT if isinstance(_STREAM_TIMEOUT, tuple) else (3, int(timeout)))  # --- opnxt-stream ---
        self._session = _build_session()
        self.api_style = (os.getenv("OPNXT_LLM_LOCAL_API") or "auto").lower()  # --- opnxt-stream ---

    def invoke(self, messages: List[Dict[str, str]]):
        # --- mcp-fix ---
        if self.api_style == "ollama":  # --- opnxt-stream ---
            return self._invoke_ollama(messages)
        if self.api_style == "openai":  # --- opnxt-stream ---
            return self._invoke_openai(messages)
        try:
            return self._invoke_openai(messages)
        except requests.exceptions.RequestException as exc:
            LOG.warning(
                "local_llm_openai_failed_switching_to_ollama",
                extra={"base_url": self.base_url, "model": self.model, "err": str(exc)},
            )
            self.api_style = "ollama"
            return self._invoke_ollama(messages)

    def stream(self, messages: List[Dict[str, str]]) -> Iterator[Dict[str, Any]]:  # --- opnxt-stream ---
        if self.api_style == "ollama":  # --- opnxt-stream ---
            yield from self._stream_ollama(messages)
            return
        if self.api_style == "openai":  # --- opnxt-stream ---
            yield from self._stream_openai(messages)
            return
        try:
            yield from self._stream_openai(messages)
        except requests.exceptions.RequestException as exc:
            LOG.warning(
                "local_llm_stream_openai_failed_switching_to_ollama",
                extra={"base_url": self.base_url, "model": self.model, "err": str(exc)},
            )
            self.api_style = "ollama"
            yield from self._stream_ollama(messages)

    # --- opnxt-stream ---
    def _invoke_openai(self, messages: List[Dict[str, str]]):
        LOG.debug("local_llm_invoke", extra={"model": self.model, "base_url": self.base_url})
        resp = self._session.post(
            f"{self.base_url}/v1/chat/completions",
            json={"model": self.model, "messages": messages, "stream": False},
            timeout=(2, 90),
        )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content")
            if content:
                return content
        return data.get("response") or data.get("text") or ""

    # --- opnxt-stream ---
    def _stream_openai(self, messages: List[Dict[str, str]]) -> Iterator[Dict[str, Any]]:
        LOG.debug(
            "local_llm_stream",
            extra={"model": self.model, "base_url": self.base_url, "timeout": self._timeout},
        )
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        with self._session.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            timeout=(self._timeout[0], max(self._timeout[1], 60)),  # type: ignore[arg-type]
            stream=True,
        ) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    parsed = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = (parsed.get("choices") or [{}])[0].get("delta") or {}
                token = delta.get("content") or ""
                if token:
                    yield {"token": token}

    # --- opnxt-stream ---
    def _invoke_ollama(self, messages: List[Dict[str, str]]) -> str:
        url = f"{self.base_url}/api/generate"
        prompt = self._messages_to_prompt(messages)
        resp = self._session.post(url, json={"model": self.model, "prompt": prompt, "stream": False}, timeout=(2, 90))
        resp.raise_for_status()
        data = resp.json()
        return data.get("response") or data.get("text") or ""

    # --- opnxt-stream ---
    def _stream_ollama(self, messages: List[Dict[str, str]]) -> Iterator[Dict[str, Any]]:
        prompt = self._messages_to_prompt(messages)
        LOG.debug(
            "local_llm_stream_ollama",
            extra={"model": self.model, "base_url": self.base_url},
        )
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
        }
        with self._session.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=(2, 120),
            stream=True,
        ) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                try:
                    data = json.loads(raw_line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                token = data.get("response") or ""
                if token:
                    yield {"token": token}
                if data.get("done"):
                    break

    # --- opnxt-stream ---
    @staticmethod
    def _messages_to_prompt(messages: List[Dict[str, str]]) -> str:
        parts: List[str] = []
        for msg in messages:
            role = (msg.get("role") or "user").strip().upper()
            content = msg.get("content") or ""
            parts.append(f"{role}: {content}")
        parts.append("ASSISTANT:")
        return "\n".join(parts)


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
        if (os.getenv("OPNXT_DISABLE_LOCAL_LLM") or "").strip() == "1":  # --- opnxt-stream ---
            raise RuntimeError("Local LLM disabled via OPNXT_DISABLE_LOCAL_LLM")
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
    persona_lookup = {
        "pm": "product manager",
        "product": "product manager",
        "analyst": "business analyst",
        "engineer": "engineering lead",
        "architect": "solutions architect",
        "qa": "quality partner",
        "approver": "governance approver",
        "executive": "executive sponsor",
        "operations": "operations lead",
    }
    persona_label = None
    if persona:
        key = persona.lower()
        persona_label = persona_lookup.get(key) or persona.replace("_", " ").strip().lower()

    opening = f"I'm hearing that {summary_line}."
    if persona_label:
        opening = f"I'm hearing that {summary_line}. I'll partner with you in the {persona_label} seat so the briefing lands the right way."
    lines.append(opening)

    if attachments:
        lines.append("I've reviewed what you dropped in so the narrative can reference the specifics already captured.")

    if gaps:
        focus_targets = ", ".join(gaps[:2])
        lines.append(f"To get us to a signable draft, let's close the gaps around {focus_targets}. Once those are settled, the deliverables come together fast.")
    else:
        lines.append("The foundations look solid—I'll translate this into the right executive materials while you confirm any final guardrails.")

    lines.append("Next moves I'm ready to drive:")
    lines.append("• Lock in the headline success metrics and hard constraints so every decision stays anchored.")
    lines.append("• Turn today's notes into draft requirements and coaching prompts the broader team can run with.")
    lines.append("• Surface the early risks or dependencies we should brief before the stakeholder walk-through.")

    if questions:
        lines.append("Before I stitch the draft, could you clarify:")
        for q in questions[:2]:
            lines.append(f"- {q}")
    else:
        lines.append("Let me know if there are executive expectations or solution boundaries we still need on paper.")

    lines.append("Reply with any missing context—or just tell me to draft—and I'll spin up the kickoff packet immediately.")
    return "\n".join(lines)


def reply_with_chat_ai(
    project_name: str,
    user_message: str,
    history: List[Dict[str, str]] | None = None,
    attachments: Optional[Dict[str, str]] = None,
    persona: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    streaming_aware: bool = False,  # --- opnxt-stream ---
    intent_override: Optional[str] = None,
    purpose_override: Optional[str] = None,
) -> Dict[str, Optional[str] | str]:
    """Return assistant reply using LLM if configured; otherwise a helpful deterministic fallback.

    history: list of {role, content} where role in {system,user,assistant}
    attachments: mapping of filename->content (markdown) to provide context from generated docs
    """
    history = history or []

    detected_intent = intent_override or detect_user_intent(user_message, history)
    force_non_troubleshooting = bool(intent_override and intent_override != "troubleshooting")
    if detected_intent == "troubleshooting" and not force_non_troubleshooting:
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

    purpose = purpose_override or _determine_purpose(user_message)

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
        # --- mcp-fix ---
        preferred_local_fallback = os.getenv("OPNXT_LLM_LOCAL_FALLBACK_MODEL", "mixtral:8x22b")
        cloud_provider_override = os.getenv("OPNXT_LLM_CLOUD_PROVIDER")
        cloud_model_override = os.getenv("OPNXT_LLM_CLOUD_MODEL")
        res = None
        primary_error: Optional[Exception] = None
        current_provider = selected_provider
        current_model = selected_model
        breaker_skipped = isinstance(llm, LocalLLMClient) and _breaker_open()
        if breaker_skipped:
            now = time.time()
            if now - _LAST_BREAKER_PROBE["t"] < _BREAKER_PROBE_INTERVAL:
                primary_error = RuntimeError("llm_circuit_open")
                LOG.info("llm_skipped_due_to_breaker", extra={"cooldown_s": _BREAKER_COOLDOWN})
            else:
                _LAST_BREAKER_PROBE["t"] = now
                try:
                    if streaming_aware and isinstance(llm, LocalLLMClient):
                        res = {"probe": True}
                    else:
                        res = llm.invoke(msgs)
                    _record_success()
                    LOG.info("llm_breaker_probe_succeeded")
                    breaker_skipped = False
                except Exception as probe_err:
                    _record_fail()
                    LOG.warning("llm_breaker_probe_failed", extra={"err": str(probe_err)})
                    primary_error = RuntimeError("llm_circuit_open")
        if not breaker_skipped:
            try:
                if streaming_aware and isinstance(llm, LocalLLMClient):  # --- opnxt-stream ---
                    _record_success()  # --- opnxt-stream ---
                    return {
                        "text": "",  # Placeholder; streaming caller handles tokens.
                        "provider": selected_provider,
                        "model": selected_model,
                        "stream": llm,  # --- opnxt-stream ---
                        "messages": msgs,  # --- opnxt-stream ---
                    }

                res = llm.invoke(msgs)
                _record_success()
            except Exception as first_err:
                primary_error = first_err
                LOG.warning("llm_primary_failed", extra={"err": str(first_err)})
                _record_fail()
                if isinstance(llm, LocalLLMClient) and preferred_local_fallback and preferred_local_fallback != llm.model:
                    try:
                        llm.model = preferred_local_fallback
                        LOG.info("llm_try_alt_local", extra={"alt_model": llm.model})
                        res = llm.invoke(msgs)
                        current_model = llm.model
                        _record_success()
                        LOG.info("llm_alt_local_success", extra={"model": current_model})
                    except Exception as second_err:
                        LOG.warning("llm_alt_failed", extra={"err": str(second_err)})
                        _record_fail()
                        res = None
                if res is None and cloud_provider_override:
                    try:
                        LOG.info(
                            "llm_try_cloud",
                            extra={"provider": cloud_provider_override, "model": cloud_model_override},
                        )
                        cloud_llm, cloud_provider, cloud_model = _get_llm(
                            purpose,
                            provider=cloud_provider_override,
                            model_hint=cloud_model_override,
                        )
                        res = cloud_llm.invoke(msgs)
                        current_provider = cloud_provider
                        current_model = cloud_model
                        _record_success()
                        LOG.info(
                            "llm_cloud_success",
                            extra={"provider": current_provider, "model": current_model},
                        )
                    except Exception as cloud_err:
                        LOG.warning("llm_cloud_failed", extra={"err": str(cloud_err)})
                        _record_fail()
                        res = None
                        if primary_error is None:
                            primary_error = cloud_err
        if not res:
            if primary_error:
                raise primary_error
            raise RuntimeError("llm_no_response")
        text = res.content if hasattr(res, "content") else str(res)
        if not text:
            raise RuntimeError("llm_empty_response")
        return {
            "text": text,
            "provider": current_provider,
            "model": current_model,
        }
    except Exception as exc:
        # --- mcp-fix ---
        LOG.info("llm_fallback_deterministic", extra={"err": str(exc)})
        logger.exception("LLM invocation failed; falling back to deterministic prompts")
        return {
            "text": _fallback_structured_reply(user_message, history, persona, attachments),
            "provider": None,
            "model": None,
        }
