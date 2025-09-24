from __future__ import annotations

from typing import List, Dict, Any
import logging
import re
from fastapi import APIRouter, HTTPException, status, Response, Depends, Body, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from pathlib import Path
import io
import subprocess
import shutil
import tempfile

from ...domain.models import Project, ProjectCreate
from ...infrastructure.repository import get_repo
from ...core.state_machine import next_phase
from ...domain.docs_models import (
    DocGenResponse,
    DocumentArtifact,
    DocGenOptions,
    EnrichRequest,
    EnrichResponse,
    ProjectContext,
    ImpactRequest,
    ImpactResponse,
    ImpactItem,
    AIGenRequest,
    UploadAnalyzeResponse,
    UploadAnalyzeItem,
    UploadApplyRequest,
)
from ...security.rbac import require_permission, Permission
from src.sdlc_generator import generate_all_docs
from src.core import summarize_project
from ...services.doc_ai import enrich_answers_with_ai
from ...services.context_store import get_context_store
from ...infrastructure.doc_store import get_doc_store
from ...infrastructure.chat_store import get_chat_store
from ...services.master_prompt_ai import generate_with_master_prompt, generate_backlog_with_master_prompt
from ...services.doc_ingest import parse_text_from_bytes, extract_shall_statements
import io
import zipfile
import json

router = APIRouter(prefix="/projects", tags=["projects"])
logger = logging.getLogger(__name__)


@router.get("", response_model=List[Project])
def list_projects(user=Depends(require_permission(Permission.PROJECT_READ))) -> List[Project]:
    repo = get_repo()
    return repo.list()


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, user=Depends(require_permission(Permission.PROJECT_WRITE))) -> Project:
    repo = get_repo()
    return repo.create(payload)


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str, user=Depends(require_permission(Permission.PROJECT_READ))) -> Project:
    repo = get_repo()
    proj = repo.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj


@router.put("/{project_id}/advance", response_model=Project)
def advance_phase(project_id: str, user=Depends(require_permission(Permission.PROJECT_WRITE))) -> Project:
    repo = get_repo()
    proj = repo.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    nxt = next_phase(proj.current_phase)
    if not nxt:
        raise HTTPException(status_code=400, detail="No further phase available")
    updated = repo.update_phase(project_id, nxt)
    assert updated is not None
    # Auto-generate documents when reaching final phase 'end'
    if updated.current_phase.lower() == "end":
        data = {
            "project": {
                "id": updated.project_id,
                "name": updated.name,
                "description": updated.description,
                "status": updated.status,
                "current_phase": updated.current_phase,
                "metadata": updated.metadata,
            }
        }
        out_dir = Path("docs") / "generated" / project_id
        try:
            generate_all_docs(data, out_dir=out_dir)
        except Exception:
            # Do not fail the advance if doc generation errors; surface via logs later
            pass
    return updated


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_project(project_id: str, user=Depends(require_permission(Permission.ADMIN))) -> Response:
    repo = get_repo()
    ok = repo.delete(project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{project_id}/enrich", response_model=EnrichResponse)
def enrich_project_inputs(
    project_id: str,
    req: EnrichRequest,
    user=Depends(require_permission(Permission.PROJECT_WRITE)),
) -> EnrichResponse:
    repo = get_repo()
    proj = repo.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        answers, summaries = enrich_answers_with_ai(req.prompt or proj.description or "")
        return EnrichResponse(answers=answers, summaries=summaries)
    except Exception as e:
        logger.exception("Enrichment failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Enrichment failed: {e}")


@router.post("/{project_id}/documents", response_model=DocGenResponse)
def generate_documents(
    project_id: str,
    opts: DocGenOptions | None = Body(default=None),
    user=Depends(require_permission(Permission.PROJECT_WRITE)),
) -> DocGenResponse:
    repo = get_repo()
    proj = repo.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        # Base project context
        data: Dict[str, Any] = {
            "project": {
                "id": proj.project_id,
                "name": proj.name,
                "title": proj.name,  # used by templates
                "description": proj.description,
                "status": proj.status,
                "current_phase": proj.current_phase,
                "metadata": proj.metadata,
            }
        }

        # Helper: normalize a free-text requirement into canonical SHALL form
        def _norm_req(text: str) -> str | None:
            s = str(text or "").strip()
            # Remove repeated 'the system shall' prefixes first (case-insensitive via flags)
            s = re.sub(r"^(?:the\s+system\s+shall\s+)+", "", s, flags=re.IGNORECASE)
            # Then strip leading bullets, numbering, unicode bullets
            s = re.sub(r"^\s*(?:[-*•\u2022\u2023\u25E6\u2043–—]|\d+[\.)])\s*", "", s)
            s = s.strip()
            # Remove stray trailing colon-only items
            s = s.rstrip().rstrip(':').strip()
            # Capitalize first letter
            if s and not s[0].isupper():
                s = s[0].upper() + s[1:]
            # Ensure period
            if s and not s.endswith(('.', '!', '?')):
                s = s + '.'
            # Drop too-short fragments (likely headings)
            if len(s.split()) < 3:
                return None
            return f"The system SHALL {s}"

        # Merge stored project context (if any) before AI enrichment and user opts
        try:
            store = get_context_store()
            stored = store.get(project_id)
            if stored:
                if isinstance(stored.get("answers"), list) or isinstance(stored.get("answers"), dict):
                    data.setdefault("answers", {})
                    if isinstance(stored["answers"], dict):
                        for k, v in stored["answers"].items():
                            if isinstance(v, list):
                                existing = list(data["answers"].get(k, [])) if isinstance(data["answers"].get(k), list) else []
                                vn = [_norm_req(x) for x in v]
                                vn = [x for x in vn if x]
                                data["answers"][k] = existing + [x for x in vn if x not in existing]
                    # if stored answers is a flat list, append under Requirements
                    if isinstance(stored.get("answers"), list):
                        lst = [_norm_req(str(x)) for x in stored.get("answers")]
                        lst = [x for x in lst if x]
                        data.setdefault("answers", {})
                        existing = list(data["answers"].get("Requirements", [])) if isinstance(data["answers"].get("Requirements"), list) else []
                        data["answers"]["Requirements"] = existing + [x for x in lst if x not in existing]
                if isinstance(stored.get("summaries"), dict):
                    data.setdefault("summaries", {})
                    for k, v in stored["summaries"].items():
                        data["summaries"].setdefault(k, v)
        except Exception:
            pass

        # Seed answers/summaries using AI enrichment when available; fallback is deterministic.
        # IMPORTANT: Never overwrite stored/user context; only fill gaps or append.
        try:
            ai_answers, ai_summaries = enrich_answers_with_ai(proj.description or "")
            data.setdefault("answers", {})
            if isinstance(ai_answers, dict):
                for k, v in ai_answers.items():
                    if k not in data["answers"]:
                        data["answers"][k] = v
                    elif isinstance(v, list) and isinstance(data["answers"].get(k), list):
                        # append non-duplicates, keep existing first
                        existing = data["answers"][k]
                        data["answers"][k] = list(existing) + [x for x in v if x not in existing]
            data.setdefault("summaries", {})
            if isinstance(ai_summaries, dict):
                for k, v in ai_summaries.items():
                    data["summaries"].setdefault(k, v)
        except Exception:
            try:
                summary = summarize_project(proj.description or "")
                answers_seed: Dict[str, Any] = {
                    "Planning": [
                        f"Goal: {summary.get('summary')}",
                        "Stakeholders: Engineering, Product, QA",
                        proj.metadata.get("timeline", "MVP timeline TBD"),
                    ],
                    "Requirements": [
                        # Minimal requirement derived from description; can be expanded later
                        f"The system SHALL address: {summary.get('summary')}.",
                    ],
                    "Design": [
                        "Architecture: FastAPI backend + Next.js frontend; document generation pipeline.",
                    ],
                }
                summaries_seed: Dict[str, Any] = {
                    "Planning": summary.get("summary", proj.description or "Project purpose"),
                }
                data.setdefault("answers", {})
                for k, v in answers_seed.items():
                    if k not in data["answers"]:
                        data["answers"][k] = v
                    elif isinstance(v, list) and isinstance(data["answers"].get(k), list):
                        existing = data["answers"][k]
                        data["answers"][k] = list(existing) + [x for x in v if x not in existing]
                data.setdefault("summaries", {})
                for k, v in summaries_seed.items():
                    data["summaries"].setdefault(k, v)
            except Exception:
                pass

        # Insert user-provided Features (if any) as SHALL requirements
        try:
            features_raw = str((proj.metadata or {}).get("features") or "").strip()
            if features_raw:
                lines = [ln.strip() for ln in features_raw.splitlines() if ln.strip()]
                # Normalize bullets and create SHALL statements
                feature_reqs: list[str] = []
                for ln in lines:
                    t = _norm_req(ln)
                    if t:
                        feature_reqs.append(t)
                if feature_reqs:
                    data.setdefault("answers", {})
                    existing = list(data["answers"].get("Requirements", [])) if isinstance(data["answers"].get("Requirements"), list) else []
                    # Prepend features, keep uniqueness
                    merged = feature_reqs + [x for x in existing if x not in feature_reqs]
                    data["answers"]["Requirements"] = merged
        except Exception:
            pass

        # Merge user-provided inputs from DocGenOptions (paste + structured)
        try:
            if opts is not None:
                # Paste requirements (free text), one per line, normalized to SHALL form
                if getattr(opts, "paste_requirements", None):
                    pasted = str(opts.paste_requirements).strip()
                    if pasted:
                        plines = [ln.strip() for ln in pasted.splitlines() if ln.strip()]
                        pr_reqs: list[str] = []
                        for ln in plines:
                            t = _norm_req(ln)
                            if t:
                                pr_reqs.append(t)
                        if pr_reqs:
                            data.setdefault("answers", {})
                            existing = list(data["answers"].get("Requirements", [])) if isinstance(data["answers"].get("Requirements"), list) else []
                            data["answers"]["Requirements"] = pr_reqs + [x for x in existing if x not in pr_reqs]

                # Structured answers
                if getattr(opts, "answers", None):
                    data.setdefault("answers", {})
                    for k, v in (opts.answers or {}).items():
                        if isinstance(v, list):
                            existing = list(data["answers"].get(k, [])) if isinstance(data["answers"].get(k), list) else []
                            merged = existing + [x for x in v if x not in existing]
                            data["answers"][k] = merged
                        else:
                            data["answers"][k] = v  # non-list fallback

                # Structured summaries
                if getattr(opts, "summaries", None):
                    data.setdefault("summaries", {})
                    for k, v in (opts.summaries or {}).items():
                        # Let user-provided summaries override AI/fallback values
                        data["summaries"][k] = v
        except Exception:
            pass

        # Enrich with Traceability Map if available and overlay enabled (default True)
        try:
            overlay_on = True if (opts is None or getattr(opts, "traceability_overlay", True)) else False
            if overlay_on:
                project_root = Path(__file__).resolve().parents[4]
                trace_path = project_root / "reports" / "traceability-map.json"
                if trace_path.exists():
                    trace = json.loads(trace_path.read_text(encoding="utf-8"))
                    fmap: Dict[str, Any] = trace.get("map", {})
                    # Build requirements list like: "FR-001 - User Registration [missing]"
                    req_items: list[str] = []
                    for fr_id in sorted(fmap.keys()):
                        item = fmap.get(fr_id) or {}
                        title = item.get("title", "")
                        status_txt = item.get("status", "unknown")
                        req_items.append(f"{fr_id} - {title} [{status_txt}]")

                    # Summary counts
                    statuses = [str((fmap.get(k) or {}).get("status", "unknown")) for k in fmap.keys()]
                    present = statuses.count("present")
                    partial = statuses.count("partial")
                    missing = statuses.count("missing")
                    total = len(statuses)

                    planning_summary = (
                        f"Functional requirements coverage: present={present}, partial={partial}, missing={missing}, total={total}."
                    )
                    design_summary = "System composed of FastAPI backend and Next.js frontend with document generation and RBAC."
                    testing_summary = "Target unit/integration/e2e with coverage >= 80%; add API and UI tests for critical flows."

                    answers = {
                        "Requirements": req_items,
                        "Planning": [
                            proj.description or "Project purpose",
                            "Stakeholders: Engineering, Product, QA",
                            proj.metadata.get("timeline", "MVP timeline TBD"),
                        ],
                        "Design": [
                            "Architecture: FastAPI + Next.js; containerized; future: DB persistence",
                            "Integrations: LLM providers, CI/CD, object storage (planned)",
                            "Data model: In-memory repos now; swap to Postgres/Mongo with migrations",
                        ],
                        "Testing": [
                            "Strategy: unit, integration, e2e; contract tests for APIs",
                            "Environments: dev/stage/prod; seeded test data",
                        ],
                        "Implementation": [
                            "Roles: viewer, contributor, approver, admin",
                        ],
                    }
                    summaries = {
                        "Planning": planning_summary,
                        "Design": design_summary,
                        "Testing": testing_summary,
                    }

                    # Merge enrichment on top of seeds without dropping them
                    data.setdefault("answers", {})
                    for k, v in answers.items():
                        if k in data["answers"] and isinstance(data["answers"][k], list) and isinstance(v, list):
                            # append new items
                            data["answers"][k].extend(x for x in v if x not in data["answers"][k])
                        else:
                            data["answers"][k] = v
                    data.setdefault("summaries", {})
                    for k, v in summaries.items():
                        data["summaries"].setdefault(k, v)
        except Exception:
            # Safe to continue without enrichment
            pass

        out_dir = Path("docs") / "generated" / project_id
        rendered = generate_all_docs(data, out_dir=out_dir)

        # Save document versions to document store
        try:
            store = get_doc_store()
            overlay_flag = bool(getattr(opts, "traceability_overlay", False)) if opts is not None else False
            for fname, text in rendered.items():
                meta = {"overlay": overlay_flag}
                store.save_document(project_id, fname, text, meta=meta)
        except Exception:
            # Do not fail generation due to versioning issues
            pass

        artifacts = [
            DocumentArtifact(filename=fname, content=content, path=str(out_dir / fname))
            for fname, content in rendered.items()
        ]
        return DocGenResponse(project_id=project_id, saved_to=str(out_dir), artifacts=artifacts)
    except Exception as e:
        logger.exception("Document generation failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Doc generation failed: {e}")


@router.post("/{project_id}/uploads/analyze", response_model=UploadAnalyzeResponse)
def analyze_uploads(
    project_id: str,
    files: List[UploadFile] = File(...),
    user=Depends(require_permission(Permission.PROJECT_WRITE)),
) -> UploadAnalyzeResponse:
    repo = get_repo()
    proj = repo.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    items: list[UploadAnalyzeItem] = []
    store = get_doc_store()
    for f in files or []:
        try:
            raw = f.file.read()
        except Exception:
            raw = b""
        text = parse_text_from_bytes(f.filename or "upload.txt", raw or b"")
        reqs = extract_shall_statements(text)
        # Version the parsed text as an uploaded artifact (optional for visibility)
        try:
            safe_name = (f.filename or "upload.txt").strip().replace("/", "_").replace("\\", "_")
            store.save_document(project_id, f"Uploads-{safe_name}.txt", text or "", meta={"uploaded": True, "source": "upload", "original_name": f.filename or ""})
        except Exception:
            pass
        items.append(UploadAnalyzeItem(filename=f.filename or "upload", text_length=len(text or ""), requirements=reqs))

    return UploadAnalyzeResponse(project_id=project_id, items=items)


@router.post("/{project_id}/uploads/apply", response_model=ProjectContext)
def apply_upload_requirements(
    project_id: str,
    payload: UploadApplyRequest,
    user=Depends(require_permission(Permission.PROJECT_WRITE)),
) -> ProjectContext:
    repo = get_repo()
    proj = repo.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    # Normalize requirements into canonical SHALL form (reusing logic similar to doc generation)
    def _norm_req(text: str) -> str | None:
        s = str(text or "").strip()
        s = re.sub(r"^(?:the\s+system\s+shall\s+)+", "", s, flags=re.IGNORECASE)
        s = re.sub(r"^\s*(?:[-*•\u2022\u2023\u25E6\u2043–—]|\d+[\.\)])\s*", "", s)
        s = s.strip().rstrip(':').strip()
        if s and not s[0].isupper():
            s = s[0].upper() + s[1:]
        if s and not s.endswith(('.', '!', '?')):
            s = s + '.'
        if len(s.split()) < 3:
            return None
        return f"The system SHALL {s}"

    normalized: list[str] = []
    seen: set[str] = set()
    for r in (payload.requirements or []):
        t = _norm_req(r)
        if not t:
            continue
        if t not in seen:
            seen.add(t)
            normalized.append(t)

    store = get_context_store()
    data = store.get(project_id) or {}
    answers = data.get("answers") or {}
    if not isinstance(answers, dict):
        answers = {}
    key = payload.category or "Requirements"
    existing = list(answers.get(key, [])) if isinstance(answers.get(key), list) else []
    merged = list(existing) + [x for x in normalized if x not in existing]
    answers[key] = merged
    data["answers"] = answers
    saved = store.put(project_id, data)
    return ProjectContext(data=saved)


@router.get("/{project_id}/documents.zip")
def download_documents_zip(project_id: str, user=Depends(require_permission(Permission.PROJECT_READ))) -> StreamingResponse:
    repo = get_repo()
    proj = repo.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    out_dir = Path("docs") / "generated" / project_id
    if not out_dir.exists():
        # Generate on-demand if missing
        data = {
            "project": {
                "id": proj.project_id,
                "name": proj.name,
                "description": proj.description,
                "status": proj.status,
                "current_phase": proj.current_phase,
                "metadata": proj.metadata,
            }
        }
        generate_all_docs(data, out_dir=out_dir)

    # Create in-memory ZIP
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in out_dir.glob("*.*"):
            zf.write(p, arcname=p.name)
    mem.seek(0)

    headers = {
        "Content-Disposition": f"attachment; filename={project_id}-docs.zip"
    }
    return StreamingResponse(mem, media_type="application/zip", headers=headers)


@router.get("/{project_id}/context", response_model=ProjectContext)
def get_project_context(project_id: str, user=Depends(require_permission(Permission.PROJECT_READ))) -> ProjectContext:
    repo = get_repo()
    proj = repo.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    store = get_context_store()
    data = store.get(project_id)
    return ProjectContext(data=data)


@router.put("/{project_id}/context", response_model=ProjectContext)
def put_project_context(project_id: str, ctx: ProjectContext, user=Depends(require_permission(Permission.PROJECT_WRITE))) -> ProjectContext:
    repo = get_repo()
    proj = repo.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    store = get_context_store()
    stored = store.put(project_id, ctx.data or {})
    return ProjectContext(data=stored)


@router.post("/{project_id}/impacts", response_model=ImpactResponse)
def compute_impacts(project_id: str, req: ImpactRequest, user=Depends(require_permission(Permission.PROJECT_READ))) -> ImpactResponse:
    repo = get_repo()
    proj = repo.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    changed = [str(x).strip() for x in (req.changed or []) if str(x).strip()]
    impacts: list[ImpactItem] = []

    try:
        project_root = Path(__file__).resolve().parents[4]
        trace_path = project_root / "reports" / "traceability-map.json"
        fmap: Dict[str, Any] = {}
        if trace_path.exists():
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            fmap = trace.get("map", {})
        # Aggregate code impacts from FR entries
        for fr in changed:
            item = fmap.get(fr) or {}
            for code_path in item.get("code", []) or []:
                impacts.append(ImpactItem(kind="code", name=str(code_path), confidence=0.8))
        # Heuristic: FR changes typically impact SRS/SDD/TestPlan
        for doc_name in ["SRS.md", "SDD.md", "TestPlan.md"]:
            impacts.append(ImpactItem(kind="document", name=doc_name, confidence=0.6))
    except Exception:
        # Fallback to a generic list
        for doc_name in ["SRS.md", "SDD.md", "TestPlan.md"]:
            impacts.append(ImpactItem(kind="document", name=doc_name, confidence=0.5))

    # Deduplicate by (kind,name)
    seen: set[tuple[str, str]] = set()
    deduped: list[ImpactItem] = []
    for it in impacts:
        key = (it.kind, it.name)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)

    return ImpactResponse(project_id=project_id, impacts=deduped)


@router.get("/{project_id}/documents/versions")
def list_document_versions(project_id: str, user=Depends(require_permission(Permission.PROJECT_READ))):
    repo = get_repo()
    proj = repo.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    store = get_doc_store()
    versions = store.list_documents(project_id)
    # Fallback: if empty, ingest from filesystem output directory
    if not versions:
        out_dir = Path("docs") / "generated" / project_id
        if out_dir.exists():
            for p in out_dir.glob("*.*"):
                try:
                    text = p.read_text(encoding="utf-8")
                    store.save_document(project_id, p.name, text, meta={"ingested": True})
                except Exception:
                    continue
        versions = store.list_documents(project_id)
    return {"project_id": project_id, "versions": versions}


@router.get("/{project_id}/documents/{filename}/versions/{version}")
def get_document_version(project_id: str, filename: str, version: int, user=Depends(require_permission(Permission.PROJECT_READ))):
    repo = get_repo()
    proj = repo.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    store = get_doc_store()
    dv = store.get_document(project_id, filename, version=version)
    if not dv:
        raise HTTPException(status_code=404, detail="Version not found")
    return {"filename": filename, "version": dv.version, "content": dv.content}


@router.get("/{project_id}/documents/{filename}/download")
def download_document(
    project_id: str,
    filename: str,
    version: int | None = Query(default=None),
    user=Depends(require_permission(Permission.PROJECT_READ)),
):
    repo = get_repo()
    proj = repo.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    store = get_doc_store()
    dv = store.get_document(project_id, filename, version=version)
    if not dv:
        raise HTTPException(status_code=404, detail="Document or version not found")

    # Infer content type by extension
    fname_lower = filename.lower()
    if fname_lower.endswith(".md"):
        media_type = "text/markdown; charset=utf-8"
    elif fname_lower.endswith(".csv"):
        media_type = "text/csv; charset=utf-8"
    elif fname_lower.endswith(".json"):
        media_type = "application/json; charset=utf-8"
    else:
        media_type = "text/plain; charset=utf-8"

    data = (dv.content or "").encode("utf-8")
    mem = io.BytesIO(data)
    headers = {
        "Content-Disposition": f"attachment; filename={filename}"
    }
    return StreamingResponse(mem, media_type=media_type, headers=headers)


@router.get("/{project_id}/documents/{filename}/docx")
def download_document_as_docx(
    project_id: str,
    filename: str,
    version: int | None = Query(default=None),
    user=Depends(require_permission(Permission.PROJECT_READ)),
):
    # Only convert Markdown files
    if not filename.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="DOCX conversion is only supported for Markdown (.md) files")

    repo = get_repo()
    proj = repo.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    store = get_doc_store()
    dv = store.get_document(project_id, filename, version=version)
    if not dv:
        raise HTTPException(status_code=404, detail="Document or version not found")

    # Ensure pandoc is available
    if not shutil.which("pandoc"):
        raise HTTPException(status_code=503, detail="Pandoc is not installed on the server. Please install pandoc to enable DOCX conversion.")

    md_text = dv.content or ""
    # Convert Markdown to DOCX using pandoc via temp files
    tmp_in = tempfile.NamedTemporaryFile(suffix=".md", delete=False)
    tmp_out = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    tmp_in_name = tmp_in.name
    tmp_out_name = tmp_out.name
    try:
        tmp_in.write(md_text.encode("utf-8"))
        tmp_in.flush()
        tmp_in.close()
        tmp_out.close()
        # Use GitHub-flavored Markdown (gfm) for better compatibility
        cmd = ["pandoc", "-f", "gfm", "-t", "docx", tmp_in_name, "-o", tmp_out_name]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=500, detail=f"Pandoc conversion failed: {e}")
        data = Path(tmp_out_name).read_bytes()
        mem = io.BytesIO(data)
        out_name = filename[:-3] + ".docx"
        headers = {
            "Content-Disposition": f"attachment; filename={out_name}"
        }
        return StreamingResponse(mem, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers=headers)
    finally:
        try:
            Path(tmp_in_name).unlink(missing_ok=True)
        except Exception:
            pass
        try:
            Path(tmp_out_name).unlink(missing_ok=True)
        except Exception:
            pass


@router.post("/{project_id}/ai-docs", response_model=DocGenResponse)
def ai_generate_documents(project_id: str, req: AIGenRequest, user=Depends(require_permission(Permission.PROJECT_WRITE))) -> DocGenResponse:
    repo = get_repo()
    proj = repo.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    # Load latest existing docs to attach as context for reuse
    store = get_doc_store()
    attachments: dict[str, str] = {}
    try:
        listing = store.list_documents(project_id) or {}
        # Prefer attaching the main doc set if present
        preferred = {"ProjectCharter.md", "SRS.md", "SDD.md", "TestPlan.md"}
        candidates = list(listing.keys())
        # Attach preferred docs first, then others
        for fname in sorted(candidates, key=lambda f: (f not in preferred, f)):
            vers = listing.get(fname) or []
            if not vers:
                continue
            last_ver = int(vers[-1].get("version", 0))
            dv = store.get_document(project_id, fname, version=last_ver)
            if dv and isinstance(dv.content, str) and dv.content.strip():
                attachments[fname] = dv.content
    except Exception:
        # Non-fatal if versioning is unavailable
        attachments = {}

    # Build augmented input from request text, stored structured context, and (if needed) a chat transcript fallback
    base_text = (req.input_text or proj.description or "").strip()
    # Telemetry (masked): track sources used in prompt assembly
    telemetry: dict[str, Any] = {
        "project_id": project_id,
        "doc_types_requested": list(req.doc_types or []),
        "include_backlog": bool(getattr(req, "include_backlog", False)),
        "attachments_count": len(attachments),
        "attachments_names": list(sorted(list(attachments.keys()))[:4]),  # first few names only
        "context_included": False,
        "context_answers_keys": 0,
        "context_summaries_keys": 0,
        "context_requirements_count": 0,
        "chat_fallback_included": False,
        "chat_fallback_msg_count": 0,
    }
    # Append structured context from ProjectContext store (answers/summaries)
    try:
        ctx_store = get_context_store()
        ctx = ctx_store.get(project_id) or {}
        ctx_answers = ctx.get("answers") or {}
        ctx_summaries = ctx.get("summaries") or {}
        if (isinstance(ctx_answers, dict) and any(ctx_answers.values())) or (isinstance(ctx_summaries, dict) and any(ctx_summaries.values())):
            # Keep compact but explicit for the LLM
            ctx_payload = {"answers": ctx_answers, "summaries": ctx_summaries}
            base_text += "\n\nSTRUCTURED CONTEXT (answers/summaries as JSON):\n" + json.dumps(ctx_payload, indent=2)
            telemetry["context_included"] = True
            telemetry["context_answers_keys"] = len(ctx_answers) if isinstance(ctx_answers, dict) else 0
            telemetry["context_summaries_keys"] = len(ctx_summaries) if isinstance(ctx_summaries, dict) else 0
            try:
                reqs = (ctx_answers or {}).get("Requirements")
                if isinstance(reqs, list):
                    telemetry["context_requirements_count"] = len(reqs)
            except Exception:
                pass
    except Exception:
        # Non-fatal if context store unavailable
        pass

    # If no transcript present in the provided text, append a short latest chat transcript (newest session, last 12 msgs)
    try:
        if ("Conversation Transcript" not in base_text) and ("CHAT TRANSCRIPT" not in base_text):
            chat_store = get_chat_store()
            sessions = chat_store.list_sessions(project_id) or []
            if sessions:
                latest_session = sessions[0]  # list_sessions returns newest first
                last_msgs = chat_store.list_messages(latest_session.session_id)[-12:]
                if last_msgs:
                    lines = [f"{(m.role or 'user').capitalize()}: {m.content}" for m in last_msgs]
                    base_text += "\n\nCHAT TRANSCRIPT (latest):\n" + "\n".join(lines)
                    telemetry["chat_fallback_included"] = True
                    telemetry["chat_fallback_msg_count"] = len(last_msgs)
    except Exception:
        # Best-effort transcript; safe to continue without it
        pass

    try:
        telemetry["prompt_len"] = len(base_text)
        logger.info("ai-docs: assembly=%s", json.dumps(telemetry))
    except Exception:
        pass

    # If structured context is present, avoid attaching prior docs to reduce anchoring on stale content
    dropped_attachments = False
    try:
        if telemetry.get("context_included"):
            attachments = {}
            dropped_attachments = True
    except Exception:
        pass

    if dropped_attachments:
        try:
            logger.info("ai-docs: prior_attachments_dropped_due_to_context=true")
        except Exception:
            pass

    # Call the Master Prompt LLM to generate full markdown docs
    texts = generate_with_master_prompt(
        project_name=proj.name,
        input_text=base_text,
        doc_types=req.doc_types,
        attachments=attachments,
    )
    if not texts:
        raise HTTPException(status_code=503, detail="AI generation unavailable. Check API key/model settings.")

    out_dir = Path("docs") / "generated" / project_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write files and version them
    artifacts: list[DocumentArtifact] = []
    for fname, content in texts.items():
        try:
            (out_dir / fname).write_text(content, encoding="utf-8")
        except Exception:
            # continue even if filesystem write fails; still return content
            pass
        try:
            store.save_document(project_id, fname, content, meta={"ai_master_prompt": True})
        except Exception:
            pass
        artifacts.append(DocumentArtifact(filename=fname, content=content, path=str(out_dir / fname)))

    # Optionally generate backlog artifacts in a second pass using the SRS/Charter as attachments
    try:
        if getattr(req, "include_backlog", False):
            backlog_attachments: dict[str, str] = {}
            # Prefer freshly generated docs; otherwise use latest from store
            for key in ("SRS.md", "ProjectCharter.md"):
                if key in texts:
                    backlog_attachments[key] = texts[key]
                else:
                    dv = store.get_document(project_id, key)
                    if dv and dv.content:
                        backlog_attachments[key] = dv.content
            bl = generate_backlog_with_master_prompt(project_name=proj.name, attachments=backlog_attachments)
            try:
                logger.info(
                    "ai-docs: backlog_pass attachments=%s generated=%s",
                    list(sorted(list(backlog_attachments.keys()))),
                    list(sorted(list(bl.keys())))
                )
            except Exception:
                pass
            for fname, content in bl.items():
                try:
                    (out_dir / fname).write_text(content, encoding="utf-8")
                except Exception:
                    pass
                try:
                    store.save_document(project_id, fname, content, meta={"ai_master_prompt": True, "kind": "backlog"})
                except Exception:
                    pass
                artifacts.append(DocumentArtifact(filename=fname, content=content, path=str(out_dir / fname)))
    except Exception:
        # Non-fatal if backlog generation fails
        pass

    return DocGenResponse(project_id=project_id, saved_to=str(out_dir), artifacts=artifacts)
