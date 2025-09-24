from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple, Optional
import json
import os
import re
import logging

# Optional import as in doc_ai
try:
    from langchain_openai import ChatOpenAI  # type: ignore
except Exception:  # pragma: no cover - optional import
    ChatOpenAI = None  # type: ignore


def _is_placeholder_key(k: Optional[str]) -> bool:
    if not k:
        return True
    val = k.strip()
    if not val:
        return True
    return val in {"__REDACTED__", "__REPLACE_WITH_YOUR_KEY__", "changeme", "change-me-in-dev", "your_api_key_here", "placeholder"}


def _has_api_key() -> bool:
    key = os.getenv("XAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    return bool(key) and not _is_placeholder_key(key)


def _get_llm() -> object:
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


def _load_master_prompt() -> str:
    # Resolve repo root (two parents up from services/)
    here = Path(__file__).resolve()
    repo_root = here.parents[3]
    mp = repo_root / "Master_Prompt_Interactive_SDLC_Doc_Generator.md"
    if not mp.exists():
        raise FileNotFoundError(str(mp))
    return mp.read_text(encoding="utf-8")


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            raise
        return json.loads(m.group(0))


def generate_with_master_prompt(project_name: str, input_text: str, doc_types: List[str] | None = None, attachments: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Call the LLM with the Master Prompt to produce full Markdown docs.

    Returns mapping filename -> markdown.
    """
    master_prompt = _load_master_prompt()

    def _normalize_doc_types(dts: Optional[List[str]]) -> List[str]:
        raw = [str(x) for x in (dts or []) if str(x).strip()]
        out: List[str] = []
        seen: set[str] = set()
        for dt in raw:
            key = dt.strip().lower().replace("_", " ").replace("-", " ")
            # Backlog is handled in a separate second pass by the caller
            if "backlog" in key:
                continue
            norm = None
            if key in ("project charter", "projectcharter", "charter"):
                norm = "Project Charter"
            elif key in ("srs", "software requirements specification"):
                norm = "SRS"
            elif key in ("sdd", "system design document", "technical design document", "tdd"):
                norm = "SDD"
            elif key in ("test plan", "testplan", "test strategy", "test strategy/plan"):
                norm = "Test Plan"
            else:
                # Unknown types are ignored for this pass
                norm = None
            if norm and norm not in seen:
                seen.add(norm)
                out.append(norm)
        if not out:
            out = ["Project Charter", "SRS", "SDD", "Test Plan"]
        return out

    doc_types = _normalize_doc_types(doc_types)

    try:
        llm = _get_llm()
    except Exception:
        # If LLM unavailable, return empty mapping so caller can fall back
        return {}

    guides = {
        "Project Charter": (
            "Include: Purpose, Scope, Objectives, Stakeholders, Risks, Success Criteria, Assumptions, Open Questions. "
            "Add metadata (Project, Version, Date, Author, Approval)."
        ),
        "SRS": (
            "Follow IEEE 29148 style. Include: Introduction (Purpose, Scope, Definitions), Overall Description, Product Functions, "
            "Nonfunctional Requirements, Constraints, Personas, Acceptance Criteria, Assumptions & Open Questions, Traceability notes. "
            "Functional requirements should be SHALL statements."
        ),
        "SDD": (
            "Include: Architecture Overview, Modules/Components, Sequence/Flow, Integrations/APIs, Data Model, Error Handling, Security, Deployment."
        ),
        "Test Plan": (
            "Include: Test Objectives, In/Out of Scope, Test Types (unit, integration, e2e, performance, security), Environments, Roles, Schedule, Metrics, Risks, Entry/Exit criteria."
        ),
    }

    # Build a compact doc-type instruction block
    guide_lines = []
    for dt in doc_types:
        g = guides.get(dt, "Provide a comprehensive, professional document.")
        guide_lines.append(f"- {dt}: {g}")
    guide_block = "\n".join(guide_lines)

    system = (
        master_prompt
        + "\n\nIMPORTANT: Generate complete, professional documents per the guidance below. "
        + "Re-use any attached prior docs for consistency. Do not include code fences or backticks. Use GitHub-flavored Markdown. "
        + "Always include metadata (Project, Version, Date, Author, Approval). Append 'Assumptions & Open Questions'. "
        + "If the user content includes a section labeled 'STRUCTURED CONTEXT (answers/summaries as JSON):', parse it and use it to ground the content; "
        + "treat entries under 'Requirements' as canonical SHALL statements to ensure traceability. "
        + "If any conflicts exist between the structured context and attached prior documents or free text, ALWAYS prefer the structured context and the latest chat details; "
        + "use attachments only as historical reference for tone/formatting and continuity. Ensure every SHALL from the structured context appears in the SRS and is traceable in SDD and Test Plan.\n\n"
        + "Document Guidance:\n"
        + guide_block
        + "\n\nOUTPUT SPEC: Return ONLY valid JSON with keys: ProjectCharter, SRS, SDD, TestPlan. Each value MUST be a Markdown string for that document."
    )

    # Attach previously generated docs if provided
    attachments = attachments or {}
    attach_lines = []
    for fname, content in attachments.items():
        # Keep each attachment relatively short to avoid excessive tokens; truncate if huge
        snippet = content if len(content) <= 16000 else content[:16000] + "\n\n[truncated]"
        attach_lines.append(f"--- BEGIN {fname} ---\n{snippet}\n--- END {fname} ---")
    attach_block = "\n\n".join(attach_lines)

    user = (
        "PROJECT NAME: " + project_name + "\n\n"
        "USER INPUT (description/requirements):\n" + (input_text or "") + "\n\n"
        + ("ATTACHED DOCS:\n" + attach_block + "\n\n" if attach_block else "")
        + "DOC TYPES: " + ", ".join(doc_types)
    )

    try:
        res = llm.invoke([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        text = res.content if hasattr(res, "content") else str(res)
        data = _extract_json(text)
    except Exception as e:
        try:
            logging.getLogger(__name__).warning("master_prompt_ai: LLM invoke failed; falling back. %s", str(e))
        except Exception:
            pass
        return {}

    out: Dict[str, str] = {}
    mapping = {
        "ProjectCharter": "ProjectCharter.md",
        "SRS": "SRS.md",
        "SDD": "SDD.md",
        "TestPlan": "TestPlan.md",
    }
    for k, fname in mapping.items():
        val = data.get(k)
        if isinstance(val, str) and val.strip():
            out[fname] = val
    return out


def generate_backlog_with_master_prompt(project_name: str, attachments: Dict[str, str]) -> Dict[str, str]:
    """Generate backlog artifacts (Markdown, CSV, JSON) from SRS/BRD using the Master Prompt.

    Returns mapping filename -> content.
    """
    master_prompt = _load_master_prompt()
    try:
        llm = _get_llm()
    except Exception:
        return {}

    # Build attachments block (SRS, BRD, Charter, etc.)
    attach_lines: list[str] = []
    for fname, content in attachments.items():
        snippet = content if len(content) <= 20000 else content[:20000] + "\n\n[truncated]"
        attach_lines.append(f"--- BEGIN {fname} ---\n{snippet}\n--- END {fname} ---")
    attach_block = "\n\n".join(attach_lines)

    system = (
        master_prompt
        + "\n\nFOCUS: Generate a professional backlog derived from the attached SRS/BRD. "
        + "Follow INVEST and include Gherkin acceptance criteria (>=4 per story covering happy/alt/error/NFR). "
        + "Include Epics -> Features -> User Stories. Provide outputs strictly as JSON with keys: BacklogMarkdown, BacklogCSV, BacklogJSON."
    )

    user = (
        "PROJECT NAME: " + project_name + "\n\n"
        + ("ATTACHED DOCS:\n" + attach_block + "\n\n" if attach_block else "")
        + "OUTPUT SPEC: Return ONLY valid JSON."
    )

    try:
        res = llm.invoke([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        text = res.content if hasattr(res, "content") else str(res)
        data = _extract_json(text)
    except Exception as e:
        try:
            logging.getLogger(__name__).warning("master_prompt_ai: backlog LLM invoke failed; falling back. %s", str(e))
        except Exception:
            pass
        return {}

    out: Dict[str, str] = {}
    md = data.get("BacklogMarkdown")
    csv = data.get("BacklogCSV")
    jsn = data.get("BacklogJSON")
    if isinstance(md, str) and md.strip():
        out["Backlog.md"] = md
    if isinstance(csv, str) and csv.strip():
        out["Backlog.csv"] = csv
    if isinstance(jsn, (str, dict, list)):
        out["Backlog.json"] = jsn if isinstance(jsn, str) else json.dumps(jsn, indent=2)
    return out
