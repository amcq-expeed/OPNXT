# --- v1.0 update ---
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict

from .base import BaseAgent
from ..services import master_prompt_ai


class RequirementsAgent(BaseAgent):
    # --- v1.0 update ---
    name = "requirements"

    # --- v1.0 update ---
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        goal = context.get("goal") or ""
        project_name = context.get("project_name") or context.get("project_id") or "OPNXT Project"
        attachments = context.get("docs") or {}
        doc_types = context.get("doc_types") or None
        docs: Dict[str, str] = {}
        try:
            docs = master_prompt_ai.generate_with_master_prompt(
                project_name=project_name,
                input_text=goal,
                doc_types=doc_types,
                attachments=attachments,
            )
        except Exception:
            docs = {}
        return {
            "docs": docs,
            "design": {},
            "code": {},
            "tests": {},
            "devops": {},
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "summary": "Requirements synthesized from goal and prior docs.",
        }
