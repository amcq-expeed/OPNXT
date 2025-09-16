"""Automated pytest generation for OPNXT.

Creates pytest test files from Requirements (SRS) and/or Test Plan using
an LLM if available, with a deterministic fallback generator.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple
import json


def _llm_generate_tests(llm, prompt: str) -> Optional[Dict[str, str]]:
    """Ask LLM to return JSON mapping of file_path -> pytest file content."""
    if not llm:
        return None
    try:
        res = llm.invoke(prompt)
        content = getattr(res, "content", None) or str(res)
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            obj = json.loads(content[start : end + 1])
            if isinstance(obj, dict):
                return {str(k): str(v) for k, v in obj.items()}
    except Exception:
        return None
    return None


essentials = """
- Use pytest style tests (functions with `test_...`).
- Avoid external network or file system side effects.
- If implementation functions are not available yet, write tests against the
  generated scaffolds or mark with `@pytest.mark.skip(reason=...)`.
- Output ONLY a JSON object: {"tests/generated_tests/test_x.py": "..."}.
""".strip()


def _build_prompt_from_docs(srs_md: str, testplan_md: str) -> str:
    return (
        "You are a senior QA engineer. Generate pytest tests based on the SRS and Test Plan.\n\n"
        f"SRS (Markdown):\n{srs_md[:12000]}\n\n"
        f"Test Plan (Markdown):\n{testplan_md[:12000]}\n\n"
        f"Constraints:\n{essentials}\n"
    )


def generate_pytests(srs_md: str = "", testplan_md: str = "", llm=None) -> Dict[str, str]:
    mapping = _llm_generate_tests(llm, _build_prompt_from_docs(srs_md, testplan_md))
    if mapping:
        # ensure all files under tests/generated_tests
        fixed: Dict[str, str] = {}
        for p, content in mapping.items():
            rel = Path(p)
            if rel.is_absolute():
                rel = Path("tests") / "generated_tests" / rel.name
            if not str(rel).startswith("tests\\generated_tests") and not str(rel).startswith("tests/generated_tests"):
                rel = Path("tests") / "generated_tests" / rel.name
            fixed[str(rel)] = content
        return fixed

    # Fallback deterministic tests
    content = (
        "import pytest\n\n"
        "# Fallback generated tests based on high-level requirements.\n"
        "# Replace these with more specific tests once implementation stabilizes.\n\n"
        "def test_placeholder_healthcheck():\n"
        "    assert True  # Application basic placeholder test\n\n"
        "@pytest.mark.skip(reason='Waiting for implementation to be generated')\n"
        "def test_example_business_rule():\n"
        "    # TODO: assert expected behavior per SRS section 3.x\n"
        "    assert 1 + 1 == 2\n"
    )
    return {str(Path("tests") / "generated_tests" / "test_fallback.py"): content}


def write_tests(mapping: Dict[str, str], project_root: Path) -> Tuple[int, int]:
    written = 0
    skipped = 0
    for rel, content in mapping.items():
        path = project_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            skipped += 1
            continue
        path.write_text(content, encoding="utf-8")
        written += 1
    return written, skipped
