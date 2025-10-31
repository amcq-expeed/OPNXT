# --- v1.0 update ---
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from prometheus_client import Counter

from ...agents.agent_coordinator import AgentCoordinator
from ...agents.status import get_run_state
from ...infrastructure.doc_store import get_doc_store
from ...infrastructure.repository import get_repo


# --- v1.0 update ---
router = APIRouter(tags=["Orchestration"])


# --- v1.0 update ---
_ORCHESTRATION_COUNTER = Counter(
    "opnxt_orchestrations_total",
    "Total orchestrations triggered via API",
)


# --- v1.0 update ---
class OrchestrateRequest(BaseModel):
    goal: str = Field(..., min_length=3)
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    options: Optional[Dict[str, Any]] = None


# --- v1.0 update ---
class OrchestrateResponse(BaseModel):
    run_id: str
    outputs: Dict[str, Any]
    timeline: list[Dict[str, Any]]


# --- v1.0 update ---
@router.post("", response_model=OrchestrateResponse)
def orchestrate_workflow(payload: OrchestrateRequest) -> OrchestrateResponse:
    repo = get_repo()
    project = None
    if payload.project_id:
        project = repo.get(payload.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

    base_docs: Dict[str, str] = {}
    if payload.project_id:
        base_docs = _load_project_docs(payload.project_id)

    option_docs = (payload.options or {}).get("docs") if isinstance(payload.options, dict) else None
    if isinstance(option_docs, dict):
        for key, value in option_docs.items():
            if isinstance(value, str) and value.strip():
                base_docs[key] = value

    stack_prefs = (payload.options or {}).get("stack_prefs") if isinstance(payload.options, dict) else None
    if not isinstance(stack_prefs, dict):
        stack_prefs = None

    coordinator = AgentCoordinator()
    result = coordinator.run(
        goal=payload.goal,
        project_id=payload.project_id,
        project_name=(payload.project_name or getattr(project, "name", None) or "OPNXT Project"),
        docs=base_docs,
        stack_prefs=stack_prefs,
        initial_context={"options": payload.options or {}},
    )

    _ORCHESTRATION_COUNTER.inc()
    _persist_outputs(
        project_id=payload.project_id,
        goal=payload.goal,
        outputs=result.outputs,
        timeline=result.timeline,
        run_id=result.run_id,
    )

    return OrchestrateResponse(run_id=result.run_id, outputs=result.outputs, timeline=result.timeline)


# --- v1.0 update ---
@router.get("/{run_id}", response_model=OrchestrateResponse)
def get_orchestration_run(run_id: str) -> OrchestrateResponse:
    state = get_run_state(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")
    outputs = state.get("outputs") or {}
    timeline = state.get("timeline") or []
    return OrchestrateResponse(run_id=run_id, outputs=outputs, timeline=timeline)


# --- v1.0 update ---
def _load_project_docs(project_id: str) -> Dict[str, str]:
    attachments: Dict[str, str] = {}
    try:
        store = get_doc_store()
        listing = store.list_documents(project_id) or {}
        for fname, versions in listing.items():
            if not versions:
                continue
            latest = versions[-1]
            version_number = int(latest.get("version", 0)) or 1
            doc_version = store.get_document(project_id, fname, version=version_number)
            if doc_version and isinstance(doc_version.content, str) and doc_version.content.strip():
                attachments[fname] = doc_version.content
    except Exception:
        pass
    return attachments


# --- v1.0 update ---
def _persist_outputs(*, project_id: Optional[str], goal: str, outputs: Dict[str, Any], timeline: list[Dict[str, Any]], run_id: str) -> None:
    if not project_id:
        return
    try:
        store = get_doc_store()
        docs_section = outputs.get("docs") if isinstance(outputs, dict) else None
        if isinstance(docs_section, dict):
            for fname, content in docs_section.items():
                if isinstance(content, str) and content.strip():
                    store.save_document(
                        project_id,
                        fname,
                        content,
                        meta={
                            "source": "orchestrate",
                            "run_id": run_id,
                        },
                    )
        summary_payload = {
            "run_id": run_id,
            "goal": goal,
            "timeline": timeline,
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        store.save_document(
            project_id,
            f"Orchestration-{run_id}.json",
            json.dumps(summary_payload, indent=2),
            meta={"source": "orchestrate", "content_type": "application/json"},
        )
    except Exception:
        pass
