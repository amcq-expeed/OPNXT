"""
Headless SDLC simulation for OPNXT.

This script simulates a user describing a simple web app project, then runs the
full OPNXT pipeline:
- Generate SDLC docs from a synthetic dataset using the Jinja2 templates
- Validate docs and save a JSON report
- Generate code (fallback Scaffold includes a runnable Streamlit app)
- Generate pytest scaffolds
- Scaffold GitHub Actions CI

Run:
  python scripts/simulate_sdlc.py
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import sys

# Ensure repository root is on sys.path so 'src' package can be imported when
# executing this script from the scripts/ directory.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import OPNXT modules
from src.sdlc_generator import generate_all_docs, write_json_bundle
from src import validate_docs as vdoc
from src.codegen import generate_code_from_sdd, write_generated_files
from test_automation import generate_pytests, write_tests
from deploy import scaffold_github_actions


def synthetic_dataset() -> dict:
    """Return a deterministic, simple dataset representing SDLC chat outcomes.

    This pretends to be the user's answers across SDLC phases for a simple
    "Feature Voting" web app.
    """
    answers = {
        "Planning": [
            "Build a simple web app where users can propose features and upvote them.",
            "Stakeholders: PM, small dev team, early adopters.",
            "Timeline: MVP in 2 weeks, public beta in 1 month.",
        ],
        "Requirements": [
            "MVP features: create feature, upvote, list sorted by votes, delete feature (admin).",
            "Non-functional: fast page load (<1s), no PII, persistence not required in MVP.",
            "KPI: number of submitted features, vote activity per day, retention week-1.",
        ],
        "Design": [
            "Tech: Python Streamlit for UI; optional FastAPI backend; in-memory store for MVP.",
            "No external integrations MVP. Future: auth provider, DB.",
            "Data model: Feature {id, title, votes}. Simple REST-like ops for future.",
        ],
        "Implementation": [
            "Agile, 1 dev + 1 reviewer. Prioritize MVP features first.",
            "Branch strategy: main + feature branches; PR + CI on push.",
        ],
        "Testing": [
            "Unit tests for business rules; smoke tests for web app endpoints (where applicable).",
            "No external QA env needed; use local run and CI.",
        ],
        "Deployment": [
            "CI on GitHub Actions to run pytest.",
            "Later: deploy to Streamlit Cloud or containerize for cloud run.",
        ],
        "Maintenance": [
            "Basic logs; no paging/on-call. Track issues via GitHub.",
            "Manual monitoring of KPIs weekly.",
        ],
    }
    summaries = {p: f"Summary for {p}:\n- " + "\n- ".join(items) for p, items in answers.items()}
    data = {
        "project": {"title": "Feature Voting Web App"},
        "answers": answers,
        "summaries": summaries,
        "phases": [
            "Planning",
            "Requirements",
            "Design",
            "Implementation",
            "Testing",
            "Deployment",
            "Maintenance",
        ],
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    return data


def main() -> int:
    project_root = Path('.')
    out_dir = project_root / 'docs'
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Generate SDLC Docs
    data = synthetic_dataset()
    rendered = generate_all_docs(data, templates_root=Path('templates')/ 'sdlc', out_dir=out_dir)

    # 2) Persist JSON bundle
    bundle_path = out_dir / 'sdlc_bundle.json'
    write_json_bundle(data, rendered, bundle_path)

    # 3) Validate
    report = vdoc.build_report(rendered)
    (out_dir / 'validation_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')

    # 4) Codegen from SDD (fallback will always produce runnable scaffold)
    sdd_md = rendered.get('SDD.md', '')
    mapping = generate_code_from_sdd(sdd_md, project_root=project_root, llm=None)
    written, skipped = write_generated_files(mapping, project_root=project_root)

    # 5) Generate pytest scaffolds
    srs_md = rendered.get('SRS.md', '')
    tplan_md = rendered.get('TestPlan.md', '')
    tests_map = generate_pytests(srs_md=srs_md, testplan_md=tplan_md, llm=None)
    t_written, t_skipped = write_tests(tests_map, project_root=project_root)

    # 6) Scaffold CI
    wf_path, created = scaffold_github_actions(project_root)

    # 7) Guidance output
    summary = {
        "docs": list(rendered.keys()),
        "bundle": str(bundle_path),
        "validation_report": str(out_dir / 'validation_report.json'),
        "generated_files": sorted(list(mapping.keys())),
        "generated_files_written": written,
        "generated_files_skipped": skipped,
        "tests_generated": sorted(list(tests_map.keys())),
        "tests_written": t_written,
        "tests_skipped": t_skipped,
        "ci_workflow": str(wf_path),
        "ci_created": created,
        "next_steps": [
            "Run the generated Streamlit app:",
            "  streamlit run generated_code/webapp/streamlit_app.py",
            "Run tests locally:",
            "  pytest -q",
        ],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
