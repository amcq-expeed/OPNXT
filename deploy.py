"""Deployment utilities for OPNXT.

Scaffolds a minimal GitHub Actions CI workflow that:
- Sets up Python
- Installs dependencies
- Runs pytest
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple


WORKFLOW_YAML = """
name: CI

on:
  push:
    branches: [ main, master ]
  pull_request:
    branches: [ main, master ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

      - name: Run tests
        run: |
          pytest -q
""".lstrip()


def scaffold_github_actions(project_root: Path) -> Tuple[Path, bool]:
    """Create a minimal CI workflow file if it doesn't already exist.

    Returns (path, created) where created indicates whether a new file was written.
    """
    wf_dir = project_root / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    wf_path = wf_dir / "ci.yml"
    if wf_path.exists():
        return wf_path, False
    wf_path.write_text(WORKFLOW_YAML, encoding="utf-8")
    return wf_path, True
