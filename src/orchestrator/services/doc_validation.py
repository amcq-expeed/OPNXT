from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

SUPPLEMENT_HEADING = "## LLM Draft Supplement"

REQUIRED_SECTIONS: Dict[str, Tuple[str, ...]] = {
    "ProjectCharter.md": (
        "## 1. Purpose and Background",
        "## 2. Objectives & Success Criteria",
        "## 3. Scope",
        "## 4. Stakeholders and Roles",
        "## 5. High-Level Timeline & Milestones",
        "## 6. Budget Overview",
        "## 7. Risks, Issues, and Mitigations",
        "## 8. Assumptions & Dependencies",
        "## 9. Governance & Approvals",
        "## 10. Sign-off",
    ),
    "SRS.md": (
        "## 1. Introduction",
        "## 2. Overall Description",
        "## 3. Specific Requirements",
        "## 4. Verification",
        "## 5. Appendices",
    ),
    "SDD.md": (
        "## 1. Introduction",
        "## 2. Architectural Overview",
        "## 3. Detailed Design",
        "## 4. Deployment Architecture",
        "## 5. Operational Considerations",
        "## 6. Traceability",
        "## 7. Appendices",
    ),
    "TestPlan.md": (
        "## 1. Introduction",
        "## 2. Test Items",
        "## 3. Test Objectives",
        "## 4. Test Scope",
        "## 5. Test Approach",
        "## 6. Test Environment",
        "## 7. Test Deliverables",
        "## 8. Schedule & Milestones",
        "## 9. Roles & Responsibilities",
        "## 10. Risks & Contingencies",
        "## 11. Metrics & Reporting",
        "## 12. Approvals",
    ),
}


def find_missing_sections(filename: str, content: str) -> List[str]:
    required = REQUIRED_SECTIONS.get(filename, ())
    if not required:
        return []
    haystack = content or ""
    return [section for section in required if section not in haystack]


def _merge_with_baseline(baseline: str, generated: str) -> str:
    base = (baseline or "").strip()
    draft = (generated or "").strip()
    if not base:
        return draft
    if not draft:
        return base
    if SUPPLEMENT_HEADING in base or SUPPLEMENT_HEADING in draft:
        # Already merged earlier
        return base if SUPPLEMENT_HEADING in base else f"{base}\n\n{draft}"
    return f"{base}\n\n---\n\n{SUPPLEMENT_HEADING}\n\n{draft}"


def enforce_document_compliance(
    generated: Dict[str, str],
    baseline: Dict[str, str],
) -> Tuple[Dict[str, str], Dict[str, bool]]:
    """Ensure generated docs include required sections, falling back to baseline if needed.

    Returns a tuple of (normalized_docs, fallback_flags) where fallback_flags maps
    filename -> True when baseline content was merged in.
    """
    normalized: Dict[str, str] = {}
    fallback_flags: Dict[str, bool] = {}

    for filename, sections in REQUIRED_SECTIONS.items():
        generated_content = generated.get(filename, "")
        baseline_content = baseline.get(filename, "")
        use_fallback = False

        if not generated_content.strip():
            use_fallback = True
            merged = _merge_with_baseline(baseline_content, "")
        else:
            missing = find_missing_sections(filename, generated_content)
            if missing:
                use_fallback = True
                merged = _merge_with_baseline(baseline_content, generated_content)
            else:
                merged = generated_content

        normalized[filename] = merged
        fallback_flags[filename] = use_fallback

    # Preserve any additional documents that were generated (e.g., backlog)
    for filename, content in generated.items():
        if filename not in normalized:
            normalized[filename] = content
            fallback_flags.setdefault(filename, False)

    return normalized, fallback_flags
