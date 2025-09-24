"""Document validation utilities for OPNXT.

Checks generated Markdown docs for completeness against adapted IEEE-style
section lists and suggests follow-up questions to fill gaps.

Extended to integrate per-phase checklist validation from phase guide Markdown
files in ``docs/``. During/after each phase, this module can parse a guide's
checklist, auto-tick items that can be inferred programmatically (e.g., docs
exist and meet minimum section standards), and produce prompts for remaining
items for the user to address via chat or forms.
"""
from __future__ import annotations

from typing import Dict, List, Tuple, Any, Optional
import re
from dataclasses import dataclass
from pathlib import Path

# Phase guides integration
try:
    from .phase_guides import (
        DEFAULT_CHECKLISTS,
        REQUIRED_DOCS,
        load_phase_guide,
        generate_phase_guides,
        get_phase_filename,
    )
except Exception:  # pragma: no cover — allow standalone import use
    DEFAULT_CHECKLISTS = {}
    REQUIRED_DOCS = {}
    def load_phase_guide(phase_key: str, docs_dir: Path | str = "docs") -> Tuple[Optional[Path], str]:
        return None, ""
    def generate_phase_guides(progress: Dict[str, Dict[str, bool]] | None = None, out_dir: Path | str = "docs") -> Dict[str, Path]:
        return {}
    def get_phase_filename(phase_key: str) -> str:
        return f"{phase_key.lower().replace(' ', '-')}__guide.md"

# ---------- Helpers ----------

def parse_headings(md: str) -> List[str]:
    pattern = re.compile(r"^(#+)\s+(.*)$", re.MULTILINE)
    return [m.group(2).strip().lower() for m in pattern.finditer(md)]


@dataclass
class DocSpec:
    filename: str
    required_sections: List[str]
    phase_hint: str  # phase most likely to provide missing info


SPECS: List[DocSpec] = [
    DocSpec(
        filename="ProjectCharter.md",
        required_sections=[
            "project overview",
            "purpose",
            "objectives",
            "stakeholders",
            "timeline",
            "success criteria",
            "risks",
        ],
        phase_hint="Planning",
    ),
    DocSpec(
        filename="SRS.md",
        required_sections=[
            "introduction",
            "overall description",
            "external interface requirements",
            "system features",
            "nonfunctional requirements",
            "other requirements",
        ],
        phase_hint="Requirements",
    ),
    DocSpec(
        filename="SDD.md",
        required_sections=[
            "introduction",
            "system overview",
            "detailed design",
            "quality attributes",
        ],
        phase_hint="Design",
    ),
    DocSpec(
        filename="TestPlan.md",
        required_sections=[
            "introduction",
            "test items",
            "features to be tested",
            "approach",
            "pass/fail criteria",
            "responsibilities",
            "schedule",
            "risks",
        ],
        phase_hint="Testing",
    ),
]


def validate_all(rendered_docs: Dict[str, str]) -> Dict[str, List[str]]:
    """Return mapping of filename -> list of missing required sections (lowercase)."""
    issues: Dict[str, List[str]] = {}
    for spec in SPECS:
        content = rendered_docs.get(spec.filename)
        if not content:
            issues[spec.filename] = ["document missing"]
            continue
        headings = parse_headings(content)
        missing = []
        for req in spec.required_sections:
            if not any(req in h for h in headings):
                missing.append(req)
        if missing:
            issues[spec.filename] = missing
    return issues


def followup_questions(issues: Dict[str, List[str]]) -> List[Tuple[str, str, str]]:
    """Produce targeted follow-up questions.

    Returns a list of tuples: (filename, section, question)
    """
    q: List[Tuple[str, str, str]] = []
    for spec in SPECS:
        missing = issues.get(spec.filename, [])
        for sec in missing:
            if sec == "document missing":
                continue
            question = (
                f"Provide content for '{sec.title()}' to complete {spec.filename}. "
                f"Focus on concrete details relevant to the {spec.phase_hint} phase."
            )
            q.append((spec.filename, sec, question))
    return q


SECTION_TO_PHASE = {
    # Charter
    ("ProjectCharter.md", "project overview"): "Planning",
    ("ProjectCharter.md", "purpose"): "Planning",
    ("ProjectCharter.md", "objectives"): "Planning",
    ("ProjectCharter.md", "stakeholders"): "Planning",
    ("ProjectCharter.md", "timeline"): "Planning",
    ("ProjectCharter.md", "success criteria"): "Requirements",
    ("ProjectCharter.md", "risks"): "Planning",
    # SRS
    ("SRS.md", "external interface requirements"): "Design",
    ("SRS.md", "system features"): "Requirements",
    ("SRS.md", "nonfunctional requirements"): "Requirements",
    ("SRS.md", "overall description"): "Design",
    ("SRS.md", "other requirements"): "Requirements",
    ("SRS.md", "introduction"): "Planning",
    # SDD
    ("SDD.md", "system overview"): "Design",
    ("SDD.md", "detailed design"): "Design",
    ("SDD.md", "quality attributes"): "Requirements",
    ("SDD.md", "introduction"): "Design",
    # Test Plan
    ("TestPlan.md", "test items"): "Testing",
    ("TestPlan.md", "features to be tested"): "Testing",
    ("TestPlan.md", "approach"): "Testing",
    ("TestPlan.md", "pass/fail criteria"): "Testing",
    ("TestPlan.md", "responsibilities"): "Implementation",
    ("TestPlan.md", "schedule"): "Planning",
    ("TestPlan.md", "risks"): "Testing",
    ("TestPlan.md", "introduction"): "Testing",
}


def map_section_to_phase(filename: str, section: str) -> str:
    return SECTION_TO_PHASE.get((filename, section), "Planning")


def build_report(rendered_docs: Dict[str, str]) -> Dict[str, Any]:
    """Create a structured report including issues and follow-up questions."""
    issues = validate_all(rendered_docs)
    followups = followup_questions(issues)
    return {
        "issues": issues,
        "followups": [
            {"filename": f, "section": s, "question": q}
            for (f, s, q) in followups
        ],
    }


# ---------- Phase Checklist Parsing & Validation ----------

CHECKBOX_RE = re.compile(r"^\s*- \[(?P<mark>[ xX])\] (?P<text>.+)$")


def parse_phase_checklist(md: str) -> Dict[str, bool]:
    """Parse a phase guide Markdown checklist into a mapping of item -> checked.

    The function scans for Markdown checkboxes under any section, without
    requiring the caller to segment by headings.
    """
    results: Dict[str, bool] = {}
    for line in md.splitlines():
        m = CHECKBOX_RE.match(line)
        if m:
            text = m.group("text").strip()
            checked = m.group("mark").lower() == "x"
            results[text] = checked
    return results


def _infer_doc_tied_items(phase_key: str, docs_dir: Path, rendered_docs: Dict[str, str], issues: Dict[str, List[str]]) -> Dict[str, bool]:
    """Infer auto-checkable items for a phase by looking at docs presence and quality.

    Rules:
    - If a checklist item contains "docs/<FILENAME>", mark it checked when that
      file exists in ``docs_dir`` AND either the doc is not in SPECS (no required
      sections defined) or it has no missing sections according to ``issues``.
    - Non doc-tied items are left unchanged here.
    """
    inferred: Dict[str, bool] = {}
    checklist_items = DEFAULT_CHECKLISTS.get(phase_key, [])
    for item in checklist_items:
        inferred[item] = False
        # Find reference to a specific doc file
        m = re.search(r"docs/([A-Za-z0-9_.-]+)", item)
        if not m:
            continue
        fname = m.group(1)
        path = docs_dir / fname
        if not path.exists():
            continue
        # If we have issue data, ensure the doc is considered valid (no missing sections)
        missing = issues.get(fname, [])
        if missing:
            inferred[item] = False
        else:
            inferred[item] = True
    return inferred


def _merge_check_status(current: Dict[str, bool], updates: Dict[str, bool]) -> Dict[str, bool]:
    merged = dict(current)
    for k, v in updates.items():
        if v is True:
            merged[k] = True
        else:
            merged.setdefault(k, False)
    return merged


def apply_checklist_updates(phase_key: str, new_status: Dict[str, bool], docs_dir: Path) -> Dict[str, bool]:
    """Apply checklist status updates for a single phase, writing back to MD via generator.

    Returns the final status mapping actually written.
    """
    # Load existing parsed status from the current guide file (if present)
    _, md = load_phase_guide(phase_key, docs_dir)
    existing = parse_phase_checklist(md) if md else {item: False for item in DEFAULT_CHECKLISTS.get(phase_key, [])}
    final = _merge_check_status(existing, new_status)
    try:
        generate_phase_guides(progress={phase_key: final}, out_dir=docs_dir)
    except Exception:
        # Best-effort: still return the computed mapping
        pass
    return final


def validate_phase(phase_key: str, docs_dir: Path | str, rendered_docs: Dict[str, str]) -> Dict[str, Any]:
    """Validate a single phase against its guide checklist and known documents.

    - Parses the current checklist from ``docs/<phase>_guide.md``
    - Auto-checks doc-tied items if their referenced docs exist and validate cleanly
      per ``validate_all`` rules (no missing required sections)
    - Writes updated checkboxes back to the guide via ``generate_phase_guides``

    Returns a dict with keys:
    - phase: phase_key
    - checklist_before: {item -> bool}
    - checklist_after: {item -> bool}
    - newly_checked: [items flipped to True]
    - outstanding: [items still False]
    - doc_issues: filtered issues relevant to this phase's required docs
    """
    docs_path = Path(docs_dir)
    # Compute doc issues once using the provided rendered_docs map
    all_issues = validate_all(rendered_docs)

    # Parse current checklist
    _, md = load_phase_guide(phase_key, docs_path)
    before = parse_phase_checklist(md) if md else {item: False for item in DEFAULT_CHECKLISTS.get(phase_key, [])}

    # Infer doc-tied updates
    inferred = _infer_doc_tied_items(phase_key, docs_path, rendered_docs, all_issues)
    after = _merge_check_status(before, inferred)

    # Write back to disk (auto-tick)
    written = apply_checklist_updates(phase_key, after, docs_path)

    newly_checked = [k for k, v in written.items() if v and not before.get(k, False)]
    outstanding = [k for k, v in written.items() if not v]

    # Limit doc issues to this phase's directly required docs (if any)
    relevant_docs = set(REQUIRED_DOCS.get(phase_key, []))
    doc_issues = {fn: miss for fn, miss in all_issues.items() if fn in relevant_docs and miss}

    return {
        "phase": phase_key,
        "checklist_before": before,
        "checklist_after": written,
        "newly_checked": newly_checked,
        "outstanding": outstanding,
        "doc_issues": doc_issues,
    }


def prompts_for_outstanding(phase_key: str, validation_result: Dict[str, Any]) -> List[str]:
    """Produce user-facing prompts for any outstanding checklist items or doc issues."""
    prompts: List[str] = []
    for item in validation_result.get("outstanding", []):
        # Provide concise, phase-aware prompts
        prompts.append(f"[{phase_key}] Please provide details to complete: '{item}'.")
    for fn, miss in validation_result.get("doc_issues", {}).items():
        if not miss:
            continue
        # Map each missing section to follow-up questions
        for sec in miss:
            if sec == "document missing":
                prompts.append(f"[{phase_key}] The required document {fn} is missing. Generate it or upload content.")
            else:
                prompts.append(f"[{phase_key}] {fn}: Provide content for '{sec.title()}' to meet standards.")
    return prompts
