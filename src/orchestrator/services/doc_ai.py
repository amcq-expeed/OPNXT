from __future__ import annotations

"""AI enrichment for SDLC documents.

If an API key is available (OPENAI_API_KEY or XAI_API_KEY), we will call an LLM
via langchain-openai to turn a plain-English description into structured
'answers' and 'summaries' expected by the Jinja templates.

If no API key is configured, we return a deterministic fallback that still
improves on the empty defaults.
"""

from typing import Dict, Tuple, List
import os
import json
import re

# langchain-openai is optional in CI; import guarded
try:
    from langchain_openai import ChatOpenAI  # type: ignore
except Exception:  # pragma: no cover - optional import
    ChatOpenAI = None  # type: ignore


def _has_api_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("XAI_API_KEY"))


essential_system_prompt = (
    "You are an SDLC assistant. Given a short project description, return a concise "
    "JSON object with keys: planning_summary (string), requirements (list of 3-8 clear SHALL-style items), "
    "design_notes (list of 1-5 short sentences). Keep content grounded in the description without fabricating details."
)


def _llm_enrich(description: str) -> Tuple[Dict, Dict]:
    if not ChatOpenAI or not _has_api_key():
        raise RuntimeError("LLM not configured")

    # Prefer XAI via OpenAI-compatible endpoint if provided
    api_key = os.getenv("XAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    # Allow XAI_BASE_URL override; otherwise use OPENAI_BASE_URL; default to OpenAI endpoint
    base_url = (
        os.getenv("XAI_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    )
    # Allow a single override knob
    model = os.getenv("OPNXT_LLM_MODEL") or os.getenv("XAI_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    llm = ChatOpenAI(api_key=api_key, base_url=base_url, model=model, temperature=0.2)

    user_prompt = (
        "PROJECT DESCRIPTION:\n" + (description or "") + "\n\n"
        "Return ONLY valid JSON like:\n"
        "{\n  \"planning_summary\": \"...\",\n  \"requirements\": [\"The system SHALL ...\", ...],\n  \"design_notes\": [\"...\"]\n}"
    )

    try:
        res = llm.invoke([{"role": "system", "content": essential_system_prompt}, {"role": "user", "content": user_prompt}])
        text = res.content if hasattr(res, "content") else str(res)
        # Try direct JSON parse first
        try:
            data = json.loads(text)
        except Exception:
            # Extract the first JSON object from the text as a fallback
            m = re.search(r"\{[\s\S]*\}", text)
            if not m:
                raise
            data = json.loads(m.group(0))
        planning_summary = str(data.get("planning_summary", description or "Project summary"))
        raw_reqs: List[str] = [str(x) for x in (data.get("requirements") or []) if str(x).strip()]
        design = [str(x) for x in (data.get("design_notes") or []) if str(x).strip()]
    except Exception:
        # If parsing fails, fall back to deterministic enrichment
        return _fallback_enrich(description)

    def _normalize_req(s: str) -> str | None:
        # Remove leading 'The system SHALL' duplication variants first
        s = re.sub(r"^(?i)(?:the\s+system\s+shall\s+)+", "", s, flags=re.IGNORECASE)
        # Then remove leading list markers, bullets, and numbering
        s = re.sub(r"^\s*(?:[-*•\u2022\u2023\u25E6\u2043–—]|\d+[\.)])\s*", "", s)
        s = s.strip()
        # Capitalize first letter
        if s and not s[0].isupper():
            s = s[0].upper() + s[1:]
        # Ensure period at end
        if not s.endswith(('.', '!', '?')):
            s = s + '.'
        # Drop lines that are still too short (likely headings)
        if len(s.split()) < 3:
            return None
        # Prepend canonical SHALL form
        return f"The system SHALL {s}"

    # Normalize and deduplicate requirements
    normalized: List[str] = []
    seen = set()
    for r in raw_reqs:
        t = _normalize_req(r)
        if not t:
            continue
        if t not in seen:
            seen.add(t)
            normalized.append(t)
    if not normalized:
        normalized = [f"The system SHALL address: {planning_summary}."]
    normalized = normalized[:12]

    # Design notes and summary
    design_notes = design[:5] or [
        "Architecture: FastAPI backend + Next.js frontend; document generation pipeline.",
    ]
    design_summary = design_notes[0]

    answers = {
        "Planning": [f"Goal: {planning_summary}", "Stakeholders: Engineering, Product, QA", "MVP timeline TBD"],
        "Requirements": normalized,
        "Design": design_notes,
    }
    summaries = {"Planning": planning_summary, "Design": design_summary}
    return answers, summaries


def _fallback_enrich(description: str) -> Tuple[Dict, Dict]:
    # Deterministic enhancement using just the description
    planning = description.strip() or "Project purpose"
    answers = {
        "Planning": [f"Goal: {planning}", "Stakeholders: Engineering, Product, QA", "MVP timeline TBD"],
        "Requirements": [f"The system SHALL address: {planning}."],
        "Design": [
            "Architecture: FastAPI backend + Next.js frontend; document generation pipeline.",
        ],
    }
    summaries = {"Planning": planning}
    return answers, summaries


def enrich_answers_with_ai(description: str) -> Tuple[Dict, Dict]:
    """Return (answers, summaries) using LLM if configured, else deterministic fallback."""
    try:
        return _llm_enrich(description)
    except Exception:
        return _fallback_enrich(description)
