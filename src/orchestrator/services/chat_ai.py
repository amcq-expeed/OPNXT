from __future__ import annotations

from typing import List, Dict, Optional
import os

# Optional import: langchain-openai
try:
    from langchain_openai import ChatOpenAI  # type: ignore
except Exception:  # pragma: no cover - optional import
    ChatOpenAI = None  # type: ignore


def _has_api_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("XAI_API_KEY"))


def _get_llm():
    if not ChatOpenAI or not _has_api_key():
        raise RuntimeError("LLM not configured")
    api_key = os.getenv("XAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = (
        os.getenv("XAI_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    )
    model = os.getenv("OPNXT_LLM_MODEL") or os.getenv("OPENAI_MODEL") or os.getenv("XAI_MODEL") or "gpt-4o-mini"
    return ChatOpenAI(api_key=api_key, base_url=base_url, model=model, temperature=0.2)


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


def reply_with_chat_ai(project_name: str, user_message: str, history: List[Dict[str, str]] | None = None, attachments: Optional[Dict[str, str]] = None) -> str:
    """Return assistant reply using LLM if configured; otherwise a helpful deterministic fallback.

    history: list of {role, content} where role in {system,user,assistant}
    attachments: mapping of filename->content (markdown) to provide context from generated docs
    """
    history = history or []

    # Try LLM
    try:
        llm = _get_llm()
        sys = (
            "You are OPNXT's SDLC refinement assistant. Your goal is to conduct a short, focused conversation to clarify and improve the user's idea before any documents are generated. "
            "Ground responses in attached documents if present. Each reply should: (1) briefly reflect your understanding; (2) ask 2-3 targeted questions focusing on missing areas (stakeholders, scope/objectives, NFRs, constraints, interfaces, data, testing). "
            "Do not expose canonical SHALL phrasing directly to the user; capture requirements implicitly so the system can use them later. Keep responses concise (<= 8 sentences). Do not suggest generating documents; wait until the user explicitly asks or enough detail has been captured."
        )
        msgs = [{"role": "system", "content": sys}]
        if attachments:
            att = _attachment_block(attachments)
            if att:
                msgs.append({"role": "system", "content": "ATTACHED DOCUMENTS AS CONTEXT:\n" + att})
        # include prior turns
        for m in history:
            r = m.get("role") or "user"
            c = m.get("content") or ""
            if r not in ("system", "user", "assistant"):
                r = "user"
            msgs.append({"role": r, "content": c})
        msgs.append({"role": "user", "content": user_message})
        res = llm.invoke(msgs)
        return res.content if hasattr(res, "content") else str(res)
    except Exception:
        # Fallback: deterministic, conversational-first reply
        text = (user_message or "").strip()
        lines: List[str] = []
        if text:
            # Simple reflection of intent (first sentence)
            first_line = text.splitlines()[0].strip()
            lines.append(f"I understand you want to: {first_line[:180]}")
        # Targeted questions
        qs = _suggest_questions(text)
        lines.append("To refine this, a few quick questions:")
        for i, q in enumerate(qs, 1):
            lines.append(f"{i}) {q}")
        # Candidate SHALLs only if the user included bullet/imperative content
        if attachments:
            lines.append("I'll also consider any attached docs for continuity.")
        return "\n".join(lines)
