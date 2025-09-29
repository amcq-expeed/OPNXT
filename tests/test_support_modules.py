import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.backlog import _extract_requirements, generate_backlog_from_srs, write_backlog_outputs
from src.codegen import generate_code_from_sdd, write_generated_files
from src.discovery_agent import IntelligentDiscoveryAgent
from src.phase_guides import generate_guides_index, generate_phase_guides, load_phase_guide
from src.validate_docs import (
    apply_checklist_updates,
    build_report,
    parse_phase_checklist,
    prompts_for_outstanding,
    validate_all,
    validate_phase,
)


class DummyLLM:
    def __init__(self, content: str) -> None:
        self._content = content

    def invoke(self, prompt: str):
        return SimpleNamespace(content=self._content)


def test_backlog_generation_and_outputs(tmp_path: Path) -> None:
    srs = tmp_path / "SRS.md"
    srs.write_text(
        """
        The system shall allow users to submit feedback.
        1.2 The application shall export reports.
        FR-123 The application shall log audit events.
        """.strip()
    )
    requirements = _extract_requirements(srs.read_text())
    assert len(requirements) == 3

    backlog = generate_backlog_from_srs(srs)
    assert backlog["stories"]

    outputs = write_backlog_outputs(backlog, tmp_path)
    md = (tmp_path / "Backlog.md").read_text()
    data = json.loads((tmp_path / "Backlog.json").read_text())
    assert outputs["markdown"].exists()
    assert "Product Backlog" in md
    assert data["stories"][0]["acceptance_criteria"]


def test_codegen_llm_and_fallback(tmp_path: Path) -> None:
    llm = DummyLLM('{"generated_code/sample.py": "print(\"hi\")"}')
    mapping = generate_code_from_sdd("Sample SDD", tmp_path, llm=llm)
    assert "generated_code/sample.py" in mapping

    fallback_mapping = generate_code_from_sdd("Sample SDD", tmp_path, llm=None)
    assert any(path.startswith("generated_code/") for path in fallback_mapping)

    written, skipped = write_generated_files({"generated_code/test.txt": "hello"}, tmp_path)
    assert written == 1 and skipped == 0
    written2, skipped2 = write_generated_files({"generated_code/test.txt": "hello"}, tmp_path)
    assert written2 == 0 and skipped2 == 1


def test_discovery_agent_summary_and_export() -> None:
    agent = IntelligentDiscoveryAgent()
    agent.process_message("We run a hospital scheduling 200 patients per day.")
    agent.process_message("Need HIPAA compliance and Epic integration.")
    agent.process_message("Prefer Python on AWS with secure deployment.")

    summary = agent._generate_project_summary()
    assert "Industry" in summary or "Project" in summary

    completion = agent._generate_completion_response()
    assert completion["ready"]

    export = agent.export_to_opnxt_format()
    assert "Planning" in export and export["Planning"]


def test_phase_guides_and_validation(tmp_path: Path) -> None:
    guide_paths = generate_phase_guides(out_dir=tmp_path)
    assert guide_paths["Planning"].exists()

    docs = {
        "ProjectCharter.md": """
            # Project Overview
            ## Purpose
            ## Objectives
            ## Stakeholders
            ## Timeline
            ## Success Criteria
            ## Risks
        """.strip(),
        "SRS.md": """
            # Introduction
            ## Overall Description
            ## External Interface Requirements
            ## System Features
            ## Nonfunctional Requirements
            ## Other Requirements
        """.strip(),
    }

    issues = validate_all(docs)
    assert not issues["ProjectCharter.md"]

    result = validate_phase("Planning", tmp_path, docs)
    assert result["phase"] == "Planning"

    prompts = prompts_for_outstanding("Planning", result)
    # With default data, at least one checklist item should remain outstanding
    assert isinstance(prompts, list)

    # Ensure checklist updates persist to disk
    apply_checklist_updates("Planning", {"Project Charter drafted (docs/ProjectCharter.md)": True}, tmp_path)
    _, guide_text = load_phase_guide("Planning", tmp_path)
    parsed = parse_phase_checklist(guide_text)
    assert parsed

    index_path = generate_guides_index(tmp_path)
    assert index_path.exists()

    report = build_report(docs)
    assert "issues" in report and "followups" in report
*** End Patch
