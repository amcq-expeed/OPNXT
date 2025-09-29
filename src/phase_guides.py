"""Phase Guides Generator for OPNXT

Creates Markdown guides for each SDLC phase with:
- Guidelines section (aligned to IEEE/ISO standards where applicable)
- Checklist section (checkboxes). Some items are tied to required docs.

Files are written to docs/<slug>_guide.md. Slugs map to the 7 phases:
- planning-requirements
- requirements-definition
- system-design
- implementation
- testing-integration
- deployment
- maintenance-support

The short phase keys map to the app flow phases in main.py:
Planning -> Planning & Requirement Analysis
Requirements -> Requirements Definition
Design -> System & Software Design
Implementation -> Implementation
Testing -> Testing & Integration
Deployment -> Deployment
Maintenance -> Maintenance & Support
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass
from datetime import UTC, datetime


# Short app phase -> formal title and slug
FORMAL_PHASE_TITLES: Dict[str, str] = {
    "Planning": "Planning & Requirement Analysis",
    "Requirements": "Requirements Definition",
    "Design": "System & Software Design",
    "Implementation": "Implementation",
    "Testing": "Testing & Integration",
    "Deployment": "Deployment",
    "Maintenance": "Maintenance & Support",
}

PHASE_SLUGS: Dict[str, str] = {
    "Planning": "planning-requirements",
    "Requirements": "requirements-definition",
    "Design": "system-design",
    "Implementation": "implementation",
    "Testing": "testing-integration",
    "Deployment": "deployment",
    "Maintenance": "maintenance-support",
}

# Required primary docs per phase (to auto-check if present)
REQUIRED_DOCS: Dict[str, List[str]] = {
    "Planning": ["ProjectCharter.md"],
    "Requirements": ["SRS.md"],
    "Design": ["SDD.md"],
    "Testing": ["TestPlan.md"],
    # Others typically do not produce a core doc in our bundle, but you may extend
    "Implementation": [],
    "Deployment": [],
    "Maintenance": [],
}

# Default checklist items per phase (human-readable)
DEFAULT_CHECKLISTS: Dict[str, List[str]] = {
    "Planning": [
        "Project goals and success criteria captured",
        "Stakeholders and users identified",
        "Risks, assumptions, and constraints documented",
        "Project Charter drafted (docs/ProjectCharter.md)",
    ],
    "Requirements": [
        "Functional requirements drafted",
        "Non-functional requirements (ISO/IEC 25010) documented",
        "Requirements uniquely identified and prioritized (ISO/IEC/IEEE 29148)",
        "SRS produced (docs/SRS.md)",
    ],
    "Design": [
        "Architecture views and interfaces described (IEEE 1016)",
        "Data model and key entities defined",
        "Design rationale and trade-offs captured",
        "SDD produced (docs/SDD.md)",
    ],
    "Implementation": [
        "Coding standards and secure coding practices defined (OWASP/ISO 27001)",
        "MVP scope and sequencing agreed",
        "Code reviews and CI configured",
    ],
    "Testing": [
        "Test strategy levels and coverage targets set (ISO/IEC/IEEE 29119)",
        "Test environments and data management defined",
        "Traceability to requirements established",
        "Test Plan produced (docs/TestPlan.md)",
    ],
    "Deployment": [
        "Release strategy defined (blue/green, canary, rollback)",
        "Target environments and IaC prepared",
        "Operational readiness checks (monitoring, logging, security) completed",
    ],
    "Maintenance": [
        "Monitoring/observability SLOs defined",
        "Incident response and support processes documented",
        "Change management and configuration management in place",
    ],
}

# Guidelines text leveraging standards (concise)
GUIDELINES: Dict[str, str] = {
    "Planning": (
        "Follow ISO/IEC/IEEE 12207 planning principles. Clarify goals, constraints, "
        "stakeholders, milestones, risks, and success criteria."
    ),
    "Requirements": (
        "Use ISO/IEC/IEEE 29148 guidance (formerly IEEE 830): requirements should be unique, "
        "verifiable, unambiguous, and prioritized. Include NFRs aligned to ISO/IEC 25010 quality attributes."
    ),
    "Design": (
        "Apply IEEE 1016 for software design descriptions: architecture views, interfaces, data models, "
        "patterns, constraints, and rationale."
    ),
    "Implementation": (
        "Map design to modules with clear responsibilities and definition of done. Apply secure coding practices "
        "(e.g., OWASP Top 10) and ISO 27001-aligned controls."
    ),
    "Testing": (
        "Align with ISO/IEC/IEEE 29119 principles: define levels (unit/integration/e2e), coverage targets, environments, "
        "test data, and acceptance criteria with traceability to requirements."
    ),
    "Deployment": (
        "Plan release strategies (staged/blue-green/canary), environments, change control, and rollback. Ensure operational "
        "readiness (monitoring/logging/security baselines)."
    ),
    "Maintenance": (
        "Define SLOs and observability, incident response, support processes, and update cadence. Maintain change logs and "
        "configuration management per ISO/IEC/IEEE 12207."
    ),
}


@dataclass
class Guide:
    phase_key: str  # e.g., "Planning"
    title: str      # e.g., "Planning & Requirement Analysis"
    slug: str       # e.g., "planning-requirements"
    guidelines: str
    checklist: List[str]


def get_phase_filename(phase_key: str) -> str:
    slug = PHASE_SLUGS.get(phase_key, phase_key.lower().replace(" ", "-"))
    return f"{slug}_guide.md"


def _detect_doc_presence(docs_dir: Path, filename: str) -> bool:
    return (docs_dir / filename).exists()


def _render_markdown(guide: Guide, checks: Dict[str, bool]) -> str:
    # YAML frontmatter for provenance and audit
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    frontmatter = [
        "---",
        f"phase_key: {guide.phase_key}",
        f"formal_phase_title: {guide.title}",
        "version: 1.0",
        f"generated_at: {generated_at}",
        "standards_refs:",
        "  - ISO/IEC/IEEE 12207",
        "  - ISO/IEC/IEEE 29148",
        "  - IEEE 1016",
        "  - ISO/IEC/IEEE 29119",
        "  - ISO/IEC 25010",
        "generator: opnxt.phase_guides v1",
        "---",
        "",
    ]
    lines: List[str] = []
    lines.extend(frontmatter)
    lines.append(f"# {guide.title} — Phase Guide")
    lines.append("")
    lines.append("## Guidelines")
    lines.append(guide.guidelines)
    lines.append("")
    lines.append("## Checklist")
    for item in guide.checklist:
        checked = checks.get(item, False)
        box = "[x]" if checked else "[ ]"
        lines.append(f"- {box} {item}")
    lines.append("")
    lines.append(
        "> Note: Checklist items referencing docs/ will be auto-checked when those files exist."
    )
    lines.append("")
    lines.append("## Changelog")
    lines.append(f"- {generated_at}: Generated/updated by OPNXT phase guides.")
    return "\n".join(lines)


def _initial_checks(phase_key: str, docs_dir: Path) -> Dict[str, bool]:
    """Derive initial checks from file presence for doc-tied items."""
    checks: Dict[str, bool] = {item: False for item in DEFAULT_CHECKLISTS.get(phase_key, [])}
    for req in REQUIRED_DOCS.get(phase_key, []):
        # Find the corresponding checklist item text that mentions this doc
        for item in checks.keys():
            if req in item and _detect_doc_presence(docs_dir, req):
                checks[item] = True
    return checks


def build_guides() -> List[Guide]:
    guides: List[Guide] = []
    for phase_key, title in FORMAL_PHASE_TITLES.items():
        guides.append(
            Guide(
                phase_key=phase_key,
                title=title,
                slug=PHASE_SLUGS[phase_key],
                guidelines=GUIDELINES[phase_key],
                checklist=DEFAULT_CHECKLISTS[phase_key],
            )
        )
    return guides


def generate_phase_guides(progress: Dict[str, Dict[str, bool]] | None = None, out_dir: Path | str = "docs") -> Dict[str, Path]:
    """Generate or update all phase guides.

    Args:
        progress: optional mapping phase_key -> {checklist_item_text: bool}
        out_dir: output directory to write guides

    Returns:
        Mapping of phase_key -> written file path
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    written: Dict[str, Path] = {}
    guides = build_guides()
    for g in guides:
        existing = _initial_checks(g.phase_key, out_path)
        if progress and g.phase_key in progress:
            # user progress overrides initial detection for shared keys
            existing.update(progress[g.phase_key])
        text = _render_markdown(g, existing)
        target = out_path / get_phase_filename(g.phase_key)
        target.write_text(text, encoding="utf-8")
        written[g.phase_key] = target
    return written


def generate_guides_index(out_dir: Path | str = "docs") -> Path:
    """Generate an index of all phase guides with last updated timestamps."""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    rows: List[str] = []
    rows.append("# SDLC Phase Guides Index")
    rows.append("")
    rows.append("This index lists all phase guides with last updated timestamps.")
    rows.append("")
    for phase_key, title in FORMAL_PHASE_TITLES.items():
        fname = get_phase_filename(phase_key)
        fpath = root / fname
        ts = "N/A"
        if fpath.exists():
            try:
                ts = datetime.fromtimestamp(fpath.stat().st_mtime, tz=UTC).isoformat().replace("+00:00", "Z")
            except Exception:
                pass
        rows.append(f"- [{title}]({fname}) — last updated: {ts}")
    rows.append("")
    out = root / "guides_index.md"
    out.write_text("\n".join(rows), encoding="utf-8")
    return out


def load_phase_guide(phase_key: str, docs_dir: Path | str = "docs") -> Tuple[Path | None, str]:
    p = Path(docs_dir) / get_phase_filename(phase_key)
    if p.exists():
        try:
            return p, p.read_text(encoding="utf-8")
        except Exception:
            return p, ""
    return None, ""


def ensure_guides_exist(docs_dir: Path | str = "docs") -> Dict[str, Path]:
    """Create guides if missing. Returns paths (phase_key -> file)."""
    docs = Path(docs_dir)
    docs.mkdir(parents=True, exist_ok=True)
    results: Dict[str, Path] = {}
    for phase_key in FORMAL_PHASE_TITLES.keys():
        p = docs / get_phase_filename(phase_key)
        if not p.exists():
            # generate with default inferred checks
            progress: Dict[str, Dict[str, bool]] = {}
            generate_phase_guides(progress=progress, out_dir=docs)
            break
    # Populate mapping
    for phase_key in FORMAL_PHASE_TITLES.keys():
        results[phase_key] = docs / get_phase_filename(phase_key)
    return results
