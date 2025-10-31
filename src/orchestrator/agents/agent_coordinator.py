# --- v1.0 update ---
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import json
import os
import tempfile
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .base import BaseAgent
from .requirements_agent import RequirementsAgent
from .architect_agent import ArchitectAgent
from .dev_agent import DevAgent
from .qa_agent import QAAgent
from .devops_agent import DevOpsAgent
from ..infrastructure import events


# --- v1.0 update ---
@dataclass
class AgentRunResult:
    run_id: str
    outputs: Dict[str, Any]
    timeline: List[Dict[str, Any]]


# --- v1.0 update ---
class AgentCoordinator:
    def __init__(self, agents: Optional[Sequence[BaseAgent]] = None) -> None:
        self._agents: List[BaseAgent] = list(agents) if agents else [
            RequirementsAgent(),
            ArchitectAgent(),
            DevAgent(),
            QAAgent(),
            DevOpsAgent(),
        ]
        self._state_path = Path(os.getenv("OPNXT_AGENT_STATE_PATH", Path(tempfile.gettempdir()) / "opnxt_agent_state.json"))

    def run(self, *, goal: str, project_id: Optional[str] = None, project_name: Optional[str] = None, docs: Optional[Dict[str, Any]] = None, stack_prefs: Optional[Dict[str, Any]] = None, initial_context: Optional[Dict[str, Any]] = None, run_id: Optional[str] = None) -> AgentRunResult:
        context: Dict[str, Any] = {
            "goal": goal,
            "project_id": project_id,
            "project_name": project_name,
            "docs": docs or {},
            "stack_prefs": stack_prefs or {},
        }
        if initial_context:
            context.update(initial_context)
        run_identifier = run_id or uuid.uuid4().hex
        combined_outputs: Dict[str, Any] = {
            "docs": {},
            "design": {},
            "code": {},
            "tests": {},
            "devops": {},
        }
        timeline: List[Dict[str, Any]] = []
        self._write_state(run_identifier, {
            "run_id": run_identifier,
            "goal": goal,
            "project_id": project_id,
            "status": "started",
            "current_agent": None,
            "timeline": timeline,
            "updated_at": self._now(),
        })

        for agent in self._agents:
            started_at = self._now()
            events.publish_event("agent_started", {
                "run_id": run_identifier,
                "agent": agent.name,
                "goal": goal,
                "project_id": project_id,
                "started_at": started_at,
            })
            agent_entry = {
                "agent": agent.name,
                "status": "running",
                "started_at": started_at,
                "completed_at": None,
                "summary": None,
            }
            timeline.append(agent_entry)
            self._write_state(run_identifier, {
                "run_id": run_identifier,
                "goal": goal,
                "project_id": project_id,
                "status": "running",
                "current_agent": agent.name,
                "timeline": timeline,
                "updated_at": self._now(),
            })
            try:
                result = agent.run(context)
                self._merge_section(combined_outputs, result)
                context.update(result)
                agent_entry["status"] = "completed"
                agent_entry["completed_at"] = self._now()
                agent_entry["summary"] = result.get("summary")
                events.publish_event("agent_completed", {
                    "run_id": run_identifier,
                    "agent": agent.name,
                    "goal": goal,
                    "project_id": project_id,
                    "completed_at": agent_entry["completed_at"],
                })
            except Exception as exc:  # pragma: no cover - defensive routing
                agent_entry["status"] = "failed"
                agent_entry["completed_at"] = self._now()
                agent_entry["summary"] = f"{agent.name} failed: {exc}"[:400]
                events.publish_event("agent_failed", {
                    "run_id": run_identifier,
                    "agent": agent.name,
                    "goal": goal,
                    "project_id": project_id,
                    "error": str(exc),
                    "completed_at": agent_entry["completed_at"],
                })
            finally:
                self._write_state(run_identifier, {
                    "run_id": run_identifier,
                    "goal": goal,
                    "project_id": project_id,
                    "status": "running",
                    "current_agent": agent.name,
                    "timeline": timeline,
                    "updated_at": self._now(),
                })

        final_state = {
            "run_id": run_identifier,
            "goal": goal,
            "project_id": project_id,
            "status": "completed",
            "current_agent": None,
            "timeline": timeline,
            "updated_at": self._now(),
            "outputs": combined_outputs,
        }
        self._write_state(run_identifier, final_state)
        events.publish_event("agent_pipeline_completed", {
            "run_id": run_identifier,
            "goal": goal,
            "project_id": project_id,
            "completed_at": final_state["updated_at"],
        })
        return AgentRunResult(run_id=run_identifier, outputs=combined_outputs, timeline=timeline)

    def _write_state(self, run_id: str, state: Dict[str, Any]) -> None:
        try:
            existing = {}
            if self._state_path.exists():
                existing = json.loads(self._state_path.read_text(encoding="utf-8"))
            existing[str(run_id)] = state
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        except Exception:
            # Persist best-effort only; do not raise to callers
            pass

    def load_state(self, run_id: str) -> Optional[Dict[str, Any]]:
        try:
            if not self._state_path.exists():
                return None
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            return data.get(str(run_id))
        except Exception:
            return None

    def _merge_section(self, combined: Dict[str, Any], result: Dict[str, Any]) -> None:
        for key in ("docs", "design", "code", "tests", "devops"):
            value = result.get(key)
            if isinstance(value, dict):
                combined.setdefault(key, {})
                combined[key].update(value)
            elif value is not None:
                combined[key] = value

    def _now(self) -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")
