"""Backlog generation utilities.

Parses SRS.md to generate Epics/Stories and Gherkin Acceptance Criteria.
This is a heuristic, template-based generator intended as a baseline.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Tuple
import csv
import json
import re


@dataclass
class Story:
    id: str
    epic: str
    title: str
    as_a: str
    i_want: str
    so_that: str
    acceptance_criteria: List[str]


def _extract_requirements(srs_md: str) -> List[Tuple[str, str]]:
    """Extract simple functional requirements from SRS Markdown.

    Returns a list of (req_id, text).
    Heuristic: lines containing "shall" or starting with a numbered requirement pattern.
    """
    reqs: List[Tuple[str, str]] = []
    lines = srs_md.splitlines()
    req_id_pattern = re.compile(r"\b([A-Z]{2,4}-?\d{2,4}|F-?\d{2,4}|REQ-?\d{2,4})\b", re.IGNORECASE)
    for line in lines:
        t = line.strip()
        if not t:
            continue
        if " shall " in t.lower() or t.lower().startswith("the system shall"):
            # Try to find an inline ID
            m = req_id_pattern.search(t)
            rid = (m.group(1).upper() if m else "REQ-")
            reqs.append((rid, t))
        elif re.match(r"^\s*\d+\.\d+\s+", t):
            # Numbered list style
            m = req_id_pattern.search(t)
            rid = (m.group(1).upper() if m else "REQ-")
            reqs.append((rid, t))
    # Deduplicate by text
    seen = set()
    uniq: List[Tuple[str, str]] = []
    for rid, text in reqs:
        if text not in seen:
            uniq.append((rid, text))
            seen.add(text)
    return uniq


def _to_story(req_id: str, text: str, idx: int) -> Story:
    """Convert a requirement sentence into a Story with default Gherkin templates."""
    # Simple NLP-ish splits
    # Try to extract an action
    action = text
    # Clean prefixes like "The system shall"
    action = re.sub(r"^\s*[-*]?\s*The system shall\s*", "", action, flags=re.IGNORECASE)
    action = re.sub(r"^\s*[-*]?\s*The application shall\s*", "", action, flags=re.IGNORECASE)
    action = action.strip().rstrip(".")

    as_a = "user"
    i_want = action
    so_that = "achieve the intended outcome"

    story_id = f"US-{idx:03d}"
    title = f"{i_want[:1].upper() + i_want[1:]}"
    epic = "Core Functionality"

    ac = [
        f"Given a valid context, when the user performs '{i_want}', then the operation succeeds.",
        f"Given an alternate context, when the user performs '{i_want}', then the system handles the edge case gracefully.",
        f"Given invalid inputs, when the user performs '{i_want}', then the system returns a clear validation error.",
        f"Given normal load, when the user performs '{i_want}', then the response time meets performance targets.",
    ]

    return Story(
        id=story_id,
        epic=epic,
        title=title,
        as_a=as_a,
        i_want=i_want,
        so_that=so_that,
        acceptance_criteria=ac,
    )


def generate_backlog_from_srs(srs_path: Path) -> Dict[str, List[Dict]]:
    """Generate a backlog from an SRS.md file.

    Returns a dict with keys: stories (list of dicts), epics (list of str)
    """
    if not srs_path.exists():
        return {"stories": [], "epics": []}
    srs_md = srs_path.read_text(encoding="utf-8", errors="ignore")
    reqs = _extract_requirements(srs_md)
    stories: List[Story] = []
    for idx, (rid, text) in enumerate(reqs, start=1):
        story = _to_story(rid, text, idx)
        stories.append(story)
    epics = sorted({s.epic for s in stories})
    return {"stories": [asdict(s) for s in stories], "epics": epics}


def write_backlog_outputs(backlog: Dict[str, List[Dict]], out_dir: Path) -> Dict[str, Path]:
    """Write Backlog.md, Backlog.csv, Backlog.json to out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: Dict[str, Path] = {}

    # Markdown
    md_lines: List[str] = []
    md_lines.append("# Product Backlog")
    md_lines.append("")
    if backlog.get("epics"):
        md_lines.append("## Epics")
        for e in backlog["epics"]:
            md_lines.append(f"- {e}")
        md_lines.append("")
    md_lines.append("## User Stories")
    for s in backlog.get("stories", []):
        md_lines.append(f"### {s['id']}: {s['title']}")
        md_lines.append(f"As a {s['as_a']}, I want {s['i_want']} so that {s['so_that']}.")
        md_lines.append("")
        md_lines.append("Acceptance Criteria (Gherkin):")
        for i, ac in enumerate(s.get("acceptance_criteria", []), start=1):
            md_lines.append(f"- Scenario {i}: {ac}")
        md_lines.append("")
    md_text = "\n".join(md_lines)
    md_path = out_dir / "Backlog.md"
    md_path.write_text(md_text, encoding="utf-8")
    paths["markdown"] = md_path

    # CSV
    csv_path = out_dir / "Backlog.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Epic", "Title", "As a", "I want", "So that", "Acceptance Criteria (pipe-separated)"])
        for s in backlog.get("stories", []):
            writer.writerow([
                s["id"], s["epic"], s["title"], s["as_a"], s["i_want"], s["so_that"], " | ".join(s.get("acceptance_criteria", []))
            ])
    paths["csv"] = csv_path

    # JSON
    json_path = out_dir / "Backlog.json"
    json_path.write_text(json.dumps(backlog, indent=2), encoding="utf-8")
    paths["json"] = json_path

    return paths
