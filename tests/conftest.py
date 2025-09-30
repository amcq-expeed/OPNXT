import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)


@pytest.fixture(autouse=True)
def _stub_master_prompt(monkeypatch):
    """Provide deterministic AI doc generation in tests when no LLM key is present."""
    from src.orchestrator.api.routers import projects as pr

    def _fake_master_prompt(*_args, **_kwargs):
        return {
            "ProjectCharter.md": "# Charter\n",
            "SRS.md": "# SRS\nThe system SHALL support testing.",
            "SDD.md": "# SDD\nArchitecture TBD.",
            "TestPlan.md": "# Test Plan\nScope TBD.",
        }

    monkeypatch.setattr(pr, "generate_with_master_prompt", _fake_master_prompt)
    monkeypatch.setattr(pr, "generate_backlog_with_master_prompt", lambda *_a, **_k: {})
