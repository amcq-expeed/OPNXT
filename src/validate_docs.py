"""Document validation utilities for OPNXT.

Checks generated Markdown docs for completeness against adapted IEEE-style
section lists and suggests follow-up questions to fill gaps.
"""
from __future__ import annotations

from typing import Dict, List, Tuple, Any
import re
from dataclasses import dataclass

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
