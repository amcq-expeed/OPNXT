"""SDLC document generator using Jinja2.

Generates IEEE-aligned Markdown documents from chat-extracted data.
Optionally renders PDFs if WeasyPrint is available.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import json

from jinja2 import Environment, FileSystemLoader, select_autoescape

try:
    # Optional dependency for PDF export
    from weasyprint import HTML  # type: ignore
    _HAS_WEASYPRINT = True
except BaseException:
    # WeasyPrint may raise SystemExit on missing native deps (Windows/Mac).
    # Catch BaseException so the app can run without PDF support.
    _HAS_WEASYPRINT = False


@dataclass
class Artifact:
    name: str
    filename: str
    template: str


ARTIFACTS: List[Artifact] = [
    Artifact(name="Project Charter", filename="ProjectCharter.md", template="project_charter.md.j2"),
    Artifact(name="Software Requirements Specification (SRS)", filename="SRS.md", template="srs.md.j2"),
    Artifact(name="Software Design Description (SDD)", filename="SDD.md", template="sdd.md.j2"),
    Artifact(name="Test Plan", filename="TestPlan.md", template="test_plan.md.j2"),
]


def _build_env(templates_dir: Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(enabled_extensions=(".html", ".xml"), default_for_string=False),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals.update(now=lambda: datetime.utcnow().isoformat() + "Z")
    return env


def _ensure_out_dir(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)


def generate_all_docs(data: Dict[str, Any], templates_root: Path | None = None, out_dir: Path | None = None) -> Dict[str, str]:
    """Render all SDLC documents using Jinja2 templates.

    Args:
        data: JSON-like structure with keys such as 'answers', 'summaries', 'project'.
        templates_root: path to templates/sdlc directory.
        out_dir: output docs directory. If provided, files are written to disk.

    Returns:
        Mapping of filename -> rendered Markdown content
    """
    if templates_root is None:
        # Resolve templates relative to project root to avoid dependency on CWD
        here = Path(__file__).resolve()
        project_root = here.parent.parent  # repo root (.. from src/)
        templates_root = project_root / "templates" / "sdlc"
    env = _build_env(templates_root)

    rendered: Dict[str, str] = {}

    context = {
        "project": data.get("project", {}),
        "answers": data.get("answers", {}),
        "summaries": data.get("summaries", {}),
        "phases": data.get("phases", []),
        "request": data.get("request", ""),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

    for art in ARTIFACTS:
        template = env.get_template(art.template)
        content = template.render(**context)
        rendered[art.filename] = content

    if out_dir:
        _ensure_out_dir(out_dir)
        for fname, text in rendered.items():
            (out_dir / fname).write_text(text, encoding="utf-8")

    return rendered


def write_json_bundle(data: Dict[str, Any], rendered: Dict[str, str], out_path: Path) -> Path:
    """Write a single JSON bundle containing inputs and rendered artifacts.

    The bundle includes:
      - meta: timestamp and generator info
      - input: the data dict (answers, summaries, etc.)
      - artifacts: mapping filename -> markdown content
    """
    bundle = {
        "meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "generator": "OPNXT sdlc_generator.py",
            "artifacts_count": len(rendered),
        },
        "input": data,
        "artifacts": rendered,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return out_path


def markdown_to_pdf(markdown_text: str, output_pdf: Path) -> bool:
    """Optionally render a PDF from Markdown using WeasyPrint.

    Converts Markdown -> basic HTML -> PDF if WeasyPrint is installed.
    Returns True on success, False otherwise.
    """
    if not _HAS_WEASYPRINT:
        return False
    try:
        # Basic markdown -> HTML conversion; minimal styling.
        try:
            import markdown as md  # type: ignore
        except Exception:
            return False
        html = md.markdown(markdown_text, extensions=["extra", "tables", "toc"])  # type: ignore
        HTML(string=f"<html><body>{html}</body></html>").write_pdf(str(output_pdf))
        return True
    except Exception:
        return False
