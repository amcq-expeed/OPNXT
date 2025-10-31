# --- v1.0 update ---
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List

from .base import BaseAgent


class QAAgent(BaseAgent):
    # --- v1.0 update ---
    name = "qa"

    # --- v1.0 update ---
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        docs = context.get("docs") or {}
        code = context.get("code") or {}
        goal = context.get("goal") or ""
        test_cases: List[Dict[str, Any]] = []
        if docs:
            for fname in sorted(docs.keys()):
                test_cases.append(
                    {
                        "source": fname,
                        "type": "acceptance",
                        "description": f"Validate requirements captured in {fname}.",
                    }
                )
        if goal:
            test_cases.append(
                {
                    "source": "goal",
                    "type": "scenario",
                    "description": f"Ensure solution satisfies: {goal}",
                }
            )
        if code:
            test_cases.append(
                {
                    "source": "code_plan",
                    "type": "unit",
                    "description": "Add unit tests for orchestrator pipeline components.",
                }
            )
        tests = {
            "checklist": test_cases,
            "strategy": "Cover acceptance, scenario, and unit checks for orchestrated agents.",
        }
        return {
            "docs": docs,
            "design": context.get("design") or {},
            "code": code,
            "tests": tests,
            "devops": {},
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "summary": "QA plan constructed covering requirements, goal, and code strategy.",
        }
