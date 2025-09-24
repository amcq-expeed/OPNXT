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
            "You are OPNXT's SDLC refinement assistant. Help the user clarify, correct, and improve requirements and design before stories are created. "
            "Ground responses in attached documents if present. When you propose requirement changes, produce canonical SHALL statements. Be concise."
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
        # Fallback: deterministic helpful reply
        tips: List[str] = []
        text = (user_message or "").strip()
        if len(text) < 10:
            tips.append("Please provide more detail so I can refine the requirement into SHALL form.")
        # Turn bullet-like lines into SHALL statements
        shall_lines: List[str] = []
        for ln in text.splitlines():
            s = ln.strip().lstrip("-•*").strip()
            if not s:
                continue
            if not s.lower().startswith("the system shall"):
                if not s.endswith('.'):
                    s += '.'
                s = "The system SHALL " + s[0].upper() + s[1:]
            shall_lines.append(s)
        if shall_lines:
            tips.insert(0, "Converted to canonical SHALL requirements:")
            for i, s in enumerate(shall_lines, 1):
                tips.append(f"{i}. {s}")
        if attachments:
            tips.append("I'll consider the existing docs when refining. After you confirm, regenerate documents to apply changes.")
        return "\n".join(tips) or "I can help refine your idea into clear requirements. Describe the outcome you need, key users, and constraints."
