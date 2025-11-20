from __future__ import annotations

from collections import Counter, defaultdict
import base64
import difflib
import io
import subprocess
import tempfile
from datetime import datetime, timezone
from threading import Event, Thread
from typing import Any, AsyncGenerator, Dict, Iterable, List, Optional, Tuple
import zipfile

from pathlib import Path

import asyncio
import html
import json
import logging
import os  # --- opnxt-stream ---
import re
import textwrap
import time
import uuid

from ..domain.accelerator_session import AcceleratorMessage, AcceleratorSession
from ..domain.chat_intents import ChatIntent
from ..domain.models import Project, ProjectCreate
from ..infrastructure.accelerator_store import get_accelerator_store
from ..infrastructure.doc_store import get_doc_store
from ..infrastructure.repository import get_repo
from ..security.auth import User
from ..services.catalog_service import get_intent
from ..services.chat_ai import reply_with_chat_ai
from ..services.model_router import build_model_catalog
from ..services.doc_ingest import parse_text_from_bytes
from ..services.master_prompt_ai import generate_with_master_prompt
from ..services.artifact_stream import artifact_stream
from ..services.streaming import iter_as_async  # --- opnxt-stream ---
from ..services.telemetry_sink import TelemetryEvent, record_event, record_metric


logger = logging.getLogger("opnxt.accelerator")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("[OPNXT][%(levelname)s] %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


# --- opnxt-stream ---
artifacts_queue = artifact_stream


# --- opnxt-stream ---
_STREAM_HEARTBEAT_SECONDS = float(os.getenv("OPNXT_STREAM_HEARTBEAT_SECONDS", "5"))
_STREAM_POLL_SECONDS = float(os.getenv("OPNXT_STREAM_POLL_SECONDS", "0.5"))

ATTACHMENT_MAX_FILES = int(os.getenv("OPNXT_ACCELERATOR_MAX_ATTACHMENTS", "5"))
ATTACHMENT_MAX_CHARS = int(os.getenv("OPNXT_ACCELERATOR_ATTACHMENT_MAX_CHARS", "8000"))
ATTACHMENT_PREVIEW_CHARS = int(os.getenv("OPNXT_ACCELERATOR_ATTACHMENT_PREVIEW_CHARS", "360"))


# --- opnxt-stream ---
def _coerce_text(draft: Any) -> str:
    if isinstance(draft, str):
        return draft
    if isinstance(draft, dict):
        for key in ("text", "markdown", "content", "message", "preview"):
            value = draft.get(key)
            if value:
                return str(value)
    return str(draft or "")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "accelerator"


_PREVIEW_THEME_PRESETS = [
    {
        "keywords": {"patient", "health", "care", "clinic", "intake"},
        "theme": {
            "background": "#0f172a",
            "surface": "#ffffff",
            "surface_alt": "rgba(15, 23, 42, 0.04)",
            "primary": "#2563eb",
            "primary_soft": "rgba(37, 99, 235, 0.12)",
            "accent": "#22d3ee",
            "accent_soft": "rgba(34, 211, 238, 0.14)",
            "gradient": "linear-gradient(135deg, #2563eb 0%, #22d3ee 100%)",
            "text_primary": "#0f172a",
            "text_muted": "rgba(15, 23, 42, 0.65)",
            "border": "rgba(15, 23, 42, 0.1)",
        },
    },
    {
        "keywords": {"finance", "budget", "spend", "analytics", "dashboard"},
        "theme": {
            "background": "#111827",
            "surface": "#1f2937",
            "surface_alt": "rgba(255, 255, 255, 0.04)",
            "primary": "#f97316",
            "primary_soft": "rgba(249, 115, 22, 0.18)",
            "accent": "#22c55e",
            "accent_soft": "rgba(34, 197, 94, 0.18)",
            "gradient": "linear-gradient(135deg, #f97316 0%, #22c55e 100%)",
            "text_primary": "#f9fafb",
            "text_muted": "rgba(249, 250, 251, 0.7)",
            "border": "rgba(249, 250, 251, 0.1)",
        },
    },
]

_DEFAULT_PREVIEW_THEME = {
    "background": "#0b1120",
    "surface": "#ffffff",
    "surface_alt": "rgba(15, 23, 42, 0.05)",
    "primary": "#7c3aed",
    "primary_soft": "rgba(124, 58, 237, 0.14)",
    "accent": "#f472b6",
    "accent_soft": "rgba(244, 114, 182, 0.18)",
    "gradient": "linear-gradient(135deg, #7c3aed 0%, #f472b6 100%)",
    "text_primary": "#0b1120",
    "text_muted": "rgba(11, 17, 32, 0.68)",
    "border": "rgba(11, 17, 32, 0.12)",
}


def _choose_preview_theme(context: str) -> Dict[str, str]:
    lowered = (context or "").lower()
    for preset in _PREVIEW_THEME_PRESETS:
        if any(keyword in lowered for keyword in preset["keywords"]):
            return dict(preset["theme"])
    return dict(_DEFAULT_PREVIEW_THEME)


def _strip_requirement_refs(text: str) -> str:
    return re.sub(r"\b(?:FR|NFR|QR|DR)-\d+\b", "", text or "", flags=re.IGNORECASE)


def _normalise_copy(value: str, limit: int) -> str:
    cleaned = _strip_requirement_refs(value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if limit and len(cleaned) > limit:
        cleaned = cleaned[:limit].rstrip()
        if not cleaned.endswith("…"):
            cleaned = cleaned.rstrip("., ") + "…"
    return cleaned


def _extract_candidate_title(latest_input: str) -> Optional[str]:
    text = (latest_input or "").strip()
    if not text:
        return None
    segments = re.split(r"[\n\r\.!?]+", text)
    for segment in segments:
        cleaned = _strip_requirement_refs(segment)
        cleaned = re.sub(r"[^A-Za-z0-9\s:/&'\-]", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" :.-")
        if len(cleaned) >= 6:
            return cleaned
    return None


def _extract_supporting_line(latest_input: str, primary_line: str) -> Optional[str]:
    lines = [
        re.sub(r"\s+", " ", _strip_requirement_refs(line)).strip(" :.-")
        for line in re.split(r"[\n\r]+", latest_input or "")
        if line and line.strip()
    ]
    for line in lines:
        if primary_line and line.lower() == primary_line.lower():
            continue
        if len(line) >= 12:
            return line
    return None


def _infer_preview_metadata(
    latest_input: str,
    intent: ChatIntent,
    fr_refs: Iterable[str],
    nfr_refs: Iterable[str],
) -> Dict[str, Any]:
    base_title = intent.requirement_area or intent.title or "Interactive Prototype"
    candidate_title = _extract_candidate_title(latest_input)
    title = candidate_title or base_title
    title = _normalise_copy(title, 72).rstrip(".")
    if len(title) < 6:
        title = base_title or "Interactive Prototype"

    supporting = _extract_supporting_line(latest_input, candidate_title or "")
    tagline = supporting or f"Interactive preview for {title}."
    tagline = _normalise_copy(tagline, 140)
    if not tagline.endswith("."):
        tagline += "."

    context = f"{title} {latest_input or ''}"
    theme = _choose_preview_theme(context)
    lowered_title = title.lower()
    healthcare_context = any(keyword in lowered_title for keyword in {"intake", "patient", "care"})

    fr_list = sorted({ref.upper() for ref in fr_refs if ref})
    nfr_list = sorted({ref.upper() for ref in nfr_refs if ref})
    fr_value = ", ".join(fr_list) if fr_list else "Pending FR mapping"
    nfr_value = ", ".join(nfr_list) if nfr_list else "Pending NFR mapping"

    if healthcare_context:
        call_to_action = "Start assessment"
        secondary_action = "View compliance metrics"
        form_title = "Capture intake details"
        form_description = "Submit a sample patient record to review validations and metrics instrumentation."
    else:
        call_to_action = "Launch experience"
        secondary_action = "Review instrumentation"
        form_title = "Submit sample data"
        form_description = "Exercise the workflow with representative values to validate logic and observability."

    highlights: List[str] = [
        f"Traces to {fr_value}." if fr_list else "Trace mapping ready for refinement.",
        f"Meets {nfr_value}." if nfr_list else "Add NFR instrumentation before release.",
        "Backed by FastAPI, PostgreSQL, and Prometheus telemetry.",
    ]

    if healthcare_context:
        form_fields = [
            {"label": "Patient age", "type": "number", "placeholder": "e.g. 42"},
            {"label": "Primary symptoms", "type": "text", "placeholder": "Shortness of breath"},
            {"label": "Insurance provider", "type": "text", "placeholder": "Enter payer name"},
        ]
    else:
        form_fields = [
            {"label": "Primary objective", "type": "text", "placeholder": "e.g. Reduce onboarding friction"},
            {"label": "Success metric", "type": "text", "placeholder": "Target KPI or SLA"},
            {"label": "Risk flag", "type": "text", "placeholder": "Document known blockers"},
        ]

    preview_meta: Dict[str, Any] = {
        "title": title,
        "tagline": tagline,
        "call_to_action": call_to_action,
        "secondary_action": secondary_action,
        "form_title": form_title,
        "form_description": form_description,
        "form_fields": form_fields,
        "metrics": [
            {"label": "Functional coverage", "value": fr_value, "hint": "Traceable requirements"},
            {"label": "NFR guardrail", "value": nfr_value, "hint": "Performance & quality targets"},
            {"label": "Stack", "value": "FastAPI · PostgreSQL · Prometheus", "hint": "Provisioned components"},
        ],
        "highlights": highlights,
        "footer": "Keyboard accessible prototype: use Tab/Shift+Tab to explore, Enter or Space to trigger actions.",
        "status_text": "Live prototype",
        "theme": theme,
        "slug": _slugify(title),
    }
    return preview_meta


def _should_request_ready_bundle(latest_input: str) -> bool:
    text = (latest_input or "").lower()
    if not text.strip():
        return False
    bundle_tokens = ["bundle", "zip", "ready-to-run", "ready to run", "scaffold"]
    preview_tokens = ["preview", "html", "mock", "live ui", "ui preview"]
    bundle_match = any(token in text for token in bundle_tokens)
    preview_match = any(token in text for token in preview_tokens)
    return bundle_match and preview_match


def _ensure_ready_bundle_flag(payload: Dict[str, Any], latest_input: str) -> Dict[str, Any]:
    if isinstance(payload, dict) and "include_ready_bundle" not in payload:
        if _should_request_ready_bundle(latest_input):
            payload["include_ready_bundle"] = True
    return payload


def _dedupe_preserve(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for raw in items:
        trimmed = raw.strip()
        if not trimmed or trimmed in seen:
            continue
        seen.add(trimmed)
        ordered.append(trimmed)
    return ordered


def _collect_message_ids_from(source: Any) -> List[str]:
    if not isinstance(source, dict):
        return []
    candidates: List[str] = []

    multi_keys = ("message_ids", "messageIds")
    single_keys = ("message_id", "messageId")

    for key in multi_keys:
        value = source.get(key)
        if isinstance(value, (list, tuple, set)):
            for entry in value:
                if isinstance(entry, str) and entry.strip():
                    candidates.append(entry)

    for key in single_keys:
        entry = source.get(key)
        if isinstance(entry, str) and entry.strip():
            candidates.append(entry)

    return candidates


def _merge_message_metadata(payload: Dict[str, Any], meta: Dict[str, Any], message_id: Optional[str]) -> None:
    collected: List[str] = []
    collected.extend(_collect_message_ids_from(payload))
    collected.extend(_collect_message_ids_from(meta))
    trimmed_message_id = message_id.strip() if isinstance(message_id, str) else None
    if trimmed_message_id:
        collected.append(trimmed_message_id)

    if collected:
        merged = _dedupe_preserve(collected)
        payload["message_ids"] = merged
        meta["message_ids"] = merged
    elif trimmed_message_id:
        payload.pop("message_ids", None)
        meta.pop("message_ids", None)

    if trimmed_message_id:
        payload["message_id"] = trimmed_message_id
        meta["message_id"] = trimmed_message_id
    else:
        if "message_id" in payload and not payload["message_id"]:
            payload.pop("message_id", None)
        if "message_id" in meta and not meta["message_id"]:
            meta.pop("message_id", None)


def _prepare_artifact_payload(artifact: Dict[str, Any], message_id: Optional[str]) -> Dict[str, Any]:
    payload = dict(artifact or {})
    meta_raw = payload.get("meta")
    meta = dict(meta_raw or {})

    _merge_message_metadata(payload, meta, message_id)

    stage = payload.get("stage") or meta.get("stage")
    if isinstance(stage, str) and stage.strip():
        normalized_stage = stage.strip()
        payload["stage"] = normalized_stage
        meta["stage"] = normalized_stage
    else:
        payload.pop("stage", None)
        meta.pop("stage", None)

    progress_value = payload.get("progress")
    if progress_value is None:
        progress_value = meta.get("progress")
    if isinstance(progress_value, (int, float)):
        payload["progress"] = progress_value
        meta["progress"] = progress_value
    else:
        payload.pop("progress", None)
        meta.pop("progress", None)

    diff_summary = payload.get("diff")
    if isinstance(diff_summary, str) and diff_summary.strip():
        meta.setdefault("diff_summary", diff_summary)

    source_value = payload.get("source") or meta.get("source")
    if isinstance(source_value, str) and source_value.strip():
        trimmed = source_value.strip()
        payload["source"] = trimmed
        meta["source"] = trimmed

    if meta_raw is not None or meta:
        payload["meta"] = meta
    else:
        payload.pop("meta", None)

    return payload


def _queue_artifact(session_id: str, artifact: Dict[str, Any], *, _skip_prepare: bool = False) -> None:
    if not _skip_prepare:
        artifact = _prepare_artifact_payload(artifact, None)

    artifact_type = (artifact.get("type") or "").lower()

    store = None
    if artifact_type not in {"snapshot", "commit"}:
        try:
            store = get_accelerator_store()
            store.add_live_artifact(session_id, artifact)
        except Exception:
            logger.exception("accelerator_live_artifact_failed", extra={"session_id": session_id})

    if artifact_type == "commit":
        try:
            store = store or get_accelerator_store()
            store.add_live_artifact(session_id, artifact)
        except Exception:
            logger.exception("accelerator_live_artifact_failed", extra={"session_id": session_id, "stage": "commit"})

    try:
        artifacts_queue.put_nowait(session_id, artifact)
    except Exception:
        logger.exception(
            "artifact_stream_enqueue_failed",
            extra={"session_id": session_id, "type": artifact.get("type")},
        )


def _queue_linked_artifact(
    session_id: str,
    artifact: Dict[str, Any],
    *,
    message_id: Optional[str] = None,
) -> None:
    enriched = _prepare_artifact_payload(artifact, message_id)
    _queue_artifact(session_id, enriched, _skip_prepare=True)


def _emit_storage_error(session_id: str, filename: str, exc: Exception) -> None:
    logger.exception(
        "accelerator_storage_failed",
        extra={"session_id": session_id, "artifact_filename": filename},
    )
    _queue_artifact(
        session_id,
        {
            "type": "error",
            "title": "Artifact storage delayed",
            "preview": f"Unable to persist {filename}: {exc}",
            "source": "system",
        },
    )


def _hydrate_snapshot_artifacts(session_id: str, artifacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    doc_store = get_doc_store()
    try:
        previews = doc_store.list_accelerator_previews(session_id)
    except Exception:
        logger.exception("accelerator_snapshot_preview_hydration_failed", extra={"session_id": session_id})
        return artifacts

    indexed: Dict[str, Dict[str, Any]] = {}
    ordered: List[Dict[str, Any]] = []
    for artifact in artifacts or []:
        filename = artifact.get("filename")
        if not filename:
            ordered.append(artifact)
            continue
        indexed[str(filename)] = artifact
        ordered.append(artifact)

    for preview in previews:
        filename = str(preview.get("filename") or "").strip()
        if not filename:
            continue
        preview_meta = dict(preview.get("meta") or {})
        preview_meta.setdefault("version", preview.get("version"))
        existing = indexed.get(filename)
        if existing:
            existing_meta = dict(existing.get("meta") or {})
            merged_meta = dict(preview_meta)
            merged_meta.update(existing_meta)
            existing["meta"] = merged_meta
            existing.setdefault("filename", filename)
            existing.setdefault("created_at", preview.get("created_at"))
            existing.setdefault("title", merged_meta.get("title") or filename)
            existing.setdefault("type", merged_meta.get("type") or merged_meta.get("kind"))
            continue

        hydrated = {
            "filename": filename,
            "created_at": preview.get("created_at"),
            "meta": preview_meta,
            "type": preview_meta.get("type") or preview_meta.get("kind"),
            "title": preview_meta.get("title") or filename,
        }
        ordered.append(hydrated)
        indexed[filename] = hydrated

    return ordered


def _enqueue_snapshot_refresh(session_id: str) -> None:
    store = get_accelerator_store()
    try:
        artifacts, revision = store.artifact_snapshot(session_id)
    except Exception:
        logger.exception("accelerator_snapshot_failed", extra={"session_id": session_id})
        return
    hydrated_artifacts = _hydrate_snapshot_artifacts(session_id, artifacts)
    _queue_artifact(
        session_id,
        {
            "type": "snapshot",
            "revision": revision,
            "artifacts": hydrated_artifacts,
        },
    )


ACCELERATOR_ASSISTANT_SYSTEM_PROMPT = textwrap.dedent(
    """
You are the OPNXT Expert Circle, collaborating with delivery leaders. Respond in a natural, senior-consultant tone.

When replying inside an accelerator chat:
- Open with a direct acknowledgement that mirrors the user's latest intent ("Thanks for the context on…"), speaking in first person plural.
- Sprinkle warm, encouraging phrases (e.g., "Got it", "Thanks for sharing that detail") so newer practitioners feel supported.
- Lead with the top two insights or next actions already available from context so progress feels immediate.
- Wherever possible, draft concrete content (tables, bullet lists, checklists) instead of deferring work back to the user.
- Limit clarification asks to one focused question per turn when additional data is absolutely required.
- Offer at least one option or next-step suggestion that highlights trade-offs for the user.
- Include one pair-programming style coaching tip (e.g., alternatives to try, best-practice reminder, or quality check) that the user can act on immediately.
- Close with clear next steps so the user always knows how to proceed.

Use concise Markdown with headings and lists. Avoid repeating previously asked intake questions unless the user contradicts earlier inputs.
"""
)


ACCELERATOR_DOCUMENT_PROMPT = textwrap.dedent(
    """
You are preparing an executive-ready accelerator deliverable. Produce polished Markdown suitable for export to PDF/Docx.

Structure requirements:
- Begin with an `#` title that includes the initiative name and deliverable focus, followed by a concise paragraph that frames the business outcome.
- Provide a **Highlights Dashboard** table (3 columns: Focus Area, Current Confidence, Exec Callout) before the table of contents.
- Include a mini table of contents linking to each major section.
- Craft an Executive Summary section with 3-5 punchy bullets that synthesize value, scope, urgency, and risks.
- Use dedicated sections (in this order): Objectives, Functional Scope, Non-Functional Guardrails, Stakeholders & Governance, Delivery Timeline & Milestones, Risks & Mitigations, Financial & Compliance Notes, Next Actions, Approval Checklist.
- Render functional scope, timeline, and risk content in clean Markdown tables with executive-friendly labels; avoid raw bullet dumps.
- Highlight gaps or unknowns with italicized callouts so decision-makers see where input is required.
- Close with a short "Advisor Perspective" paragraph that recaps momentum and names the decision or confirmation needed from leadership.

Write in a confident, advisory tone. Keep the document self-contained so it can be shared without the chat transcript.
"""
)


CODE_INTENT_IDS = {"design-build-guidance"}


ACCELERATOR_CODE_ASSISTANT_PROMPT = textwrap.dedent(
    """
You are the OPNXT Engineering Pair Programmer collaborating live with delivery teams.

When replying inside a code-focused accelerator chat:
- Acknowledge the user's latest goal conversationally (“Let’s sketch that service together…”) and include a reassuring phrase (“Got it—here’s how I’m thinking about it”).
- Highlight immediate next build actions before diving into details.
- Provide concise, code-oriented guidance (diffs, code blocks, checklists) without executive slide language.
- Ask at most one clarifying question when more detail is absolutely required.
- Close by inviting the user to run the scaffold or request additional coverage.
- Always provide a concrete pair-programming tip that reinforces quality or offers an alternative approach.

Keep the tone collaborative and human. Use Markdown with short sections (Summary, Implementation Notes, Next Steps) and include inline code where it helps.
"""
)


def _is_code_intent(intent: Optional[ChatIntent]) -> bool:
    return bool(intent and intent.intent_id in CODE_INTENT_IDS)


# --- accelerator-prompts ---
def _compose_assistant_system_prompt(intent: Optional[ChatIntent], session: AcceleratorSession) -> str:
    context_lines: List[str] = []
    if intent:
        context_lines.append(f"Initiative: {intent.title}")
        if intent.requirement_area:
            context_lines.append(f"Focus area: {intent.requirement_area}")
        if intent.deliverables:
            deliverables = ", ".join(intent.deliverables)
            context_lines.append(f"Target deliverables: {deliverables}")
        if intent.group:
            context_lines.append(f"Catalog track: {intent.group}")
    metadata = session.metadata or {}
    benefit = metadata.get("opnxt_benefit")
    if benefit:
        context_lines.append(f"Business driver: {benefit}")
    if session.persona:
        context_lines.append(f"Primary persona lens: {session.persona}")

    base_prompt = (
        ACCELERATOR_CODE_ASSISTANT_PROMPT if _is_code_intent(intent) else ACCELERATOR_ASSISTANT_SYSTEM_PROMPT
    )
    prompt_sections = [base_prompt.strip()]
    if context_lines:
        contextual_block = "Context to honor in every response:\n" + "\n".join(
            f"- {line}" for line in context_lines
        )
        prompt_sections.append(contextual_block)
    return "\n\n".join(prompt_sections)


_DEFAULT_CODE_PATH = "src/orchestrator/services/clinical_rules.py"
_DEFAULT_TEST_PATH = "tests/test_clinical_rules.py"
_DEFAULT_CONFIG_PATH = "config/rules.yaml"
_ALLOWED_TEST_PATHS = {_DEFAULT_TEST_PATH}


def _write_package_file(base_dir: Path, relative_path: str, content: bytes | str) -> Path:
    target = base_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        target.write_bytes(content)
    else:
        target.write_text(content, encoding="utf-8")
    if target.suffix == ".py":
        current = target.parent
        base = base_dir.resolve()
        while base in current.resolve().parents or current.resolve() == base:
            init_file = current / "__init__.py"
            if not init_file.exists():
                init_file.write_text("", encoding="utf-8")
            if current == base:
                break
            current = current.parent
    return target


def run_accelerator_tests(
    session_id: str,
    *,
    test_path: str | None = None,
    timeout_seconds: int = 60,
) -> Dict[str, Any]:
    doc_store = get_doc_store()
    selected_test_path = test_path or _DEFAULT_TEST_PATH
    if selected_test_path not in _ALLOWED_TEST_PATHS:
        raise ValueError("Unsupported test path requested")

    required_assets = {
        _DEFAULT_CODE_PATH: None,
        selected_test_path: None,
    }
    optional_assets = {
        _DEFAULT_CONFIG_PATH: None,
    }

    for filename in required_assets.keys():
        blob = doc_store.get_accelerator_asset(session_id, filename)
        if blob is None:
            preview = doc_store.get_accelerator_preview(session_id, filename)
            content = preview.get("content") if preview else None
            if isinstance(content, str):
                blob = content.encode("utf-8")
        if not blob:
            raise ValueError(f"Asset '{filename}' not available for session")
        required_assets[filename] = blob

    for filename in optional_assets.keys():
        blob = doc_store.get_accelerator_asset(session_id, filename)
        if blob is None:
            preview = doc_store.get_accelerator_preview(session_id, filename)
            content = preview.get("content") if preview else None
            if isinstance(content, str):
                blob = content.encode("utf-8")
        optional_assets[filename] = blob

    command = [
        "pytest",
        selected_test_path,
        "-q",
        "--disable-warnings",
        "--maxfail=1",
    ]

    started_at = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory(prefix="opnxt-accel-tests-") as tmp:
        base_dir = Path(tmp)
        for rel_path, blob in required_assets.items():
            _write_package_file(base_dir, rel_path, blob or b"")
        for rel_path, blob in optional_assets.items():
            if blob:
                _write_package_file(base_dir, rel_path, blob)

        env = os.environ.copy()
        env.setdefault("PYTHONPATH", tmp)
        start = time.perf_counter()
        try:
            result = subprocess.run(
                command,
                cwd=tmp,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            status = "passed" if result.returncode == 0 else "failed"
            stdout = result.stdout or ""
            stderr = result.stderr or ""
        except subprocess.TimeoutExpired as exc:
            status = "timeout"
            stdout = exc.stdout or ""
            stderr = (exc.stderr or "") + "\nTest run timed out."
            result = SimpleNamespace(returncode=None)  # type: ignore
        duration_ms = (time.perf_counter() - start) * 1000.0

    completed_at = datetime.now(timezone.utc)
    truncated_stdout = stdout[-10000:]
    truncated_stderr = stderr[-10000:]

    return {
        "status": status,
        "command": " ".join(command),
        "test_path": selected_test_path,
        "exit_code": getattr(result, "returncode", None),
        "stdout": truncated_stdout,
        "stderr": truncated_stderr,
        "duration_ms": duration_ms,
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "completed_at": completed_at.isoformat().replace("+00:00", "Z"),
    }


def _build_ready_to_run_readme(project_name: str) -> str:
    return textwrap.dedent(
        f"""
        # {project_name} – Ready-to-Run Scaffold

        ## Prerequisites
        - Python 3.11+
        - Node.js 20+
        - Pipenv or virtualenv recommended for Python dependencies

        ## Backend (FastAPI)
        ```bash
        pip install fastapi uvicorn pyyaml
        uvicorn src.orchestrator.services.clinical_rules_app:app --reload
        ```

        ## Frontend (React + Vite)
        ```bash
        cd frontend
        npm install
        npm run dev
        ```

        ## Tests
        ```bash
        pytest tests/test_clinical_rules.py -q
        ```

        ## Configuration
        - Update `config/rules.yaml` to change rule logic.
        - Environment variables can be set via `.env` (copy from `.env.example`).
        - Adjust `frontend/src/data/sampleExpenses.ts` to seed different demo data.
        """
    ).strip()


def _package_ready_to_run_bundle(bundle_files: Dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, content in bundle_files.items():
            zf.writestr(path, content)
    buffer.seek(0)
    return buffer.getvalue()


def _default_frontend_scaffold(project_name: str) -> Dict[str, str]:
    return {
        "frontend/package.json": textwrap.dedent(
            """
            {
              "name": "budget-tracker",
              "version": "0.1.0",
              "private": true,
              "scripts": {
                "dev": "vite",
                "build": "vite build",
                "preview": "vite preview",
                "test": "jest"
              },
              "dependencies": {
                "react": "^18.2.0",
                "react-dom": "^18.2.0",
                "@testing-library/react": "^14.1.2",
                "@testing-library/jest-dom": "^6.4.2"
              },
              "devDependencies": {
                "@types/react": "^18.2.21",
                "@types/react-dom": "^18.2.7",
                "@vitejs/plugin-react": "^4.2.0",
                "typescript": "^5.3.0",
                "vite": "^5.0.0",
                "@types/jest": "^29.5.5",
                "jest": "^29.7.0",
                "ts-jest": "^29.1.1",
                "jest-environment-jsdom": "^29.7.0"
              }
            }
            """
        ).strip(),
        "frontend/tsconfig.json": textwrap.dedent(
            """
            {
              "compilerOptions": {
                "target": "ESNext",
                "useDefineForClassFields": true,
                "lib": ["DOM", "DOM.Iterable", "ESNext"],
                "allowJs": false,
                "skipLibCheck": true,
                "esModuleInterop": true,
                "allowSyntheticDefaultImports": true,
                "strict": true,
                "forceConsistentCasingInFileNames": true,
                "module": "ESNext",
                "moduleResolution": "Node",
                "resolveJsonModule": true,
                "isolatedModules": true,
                "noEmit": true,
                "jsx": "react-jsx"
              },
              "include": ["src"],
              "references": [{ "path": "./tsconfig.node.json" }]
            }
            """
        ).strip(),
        "frontend/tsconfig.node.json": textwrap.dedent(
            """
            {
              "compilerOptions": {
                "composite": true,
                "module": "ESNext",
                "moduleResolution": "Node",
                "allowSyntheticDefaultImports": true
              },
              "include": ["vite.config.ts"]
            }
            """
        ).strip(),
        "frontend/vite.config.ts": textwrap.dedent(
            """
            import { defineConfig } from "vite";
            import react from "@vitejs/plugin-react";

            export default defineConfig({
              plugins: [react()],
              server: {
                port: 5173,
              },
            });
            """
        ).strip(),
        "frontend/jest.config.js": textwrap.dedent(
            """
            /** @type {import('ts-jest').JestConfigWithTsJest} */
            module.exports = {
              preset: 'ts-jest',
              testEnvironment: 'jest-environment-jsdom',
              setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],
              moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx'],
              transform: {
                '^.+\\.(ts|tsx)$': ['ts-jest', { tsconfig: 'tsconfig.json' }],
              },
            };
            """
        ).strip(),
        "frontend/jest.setup.ts": textwrap.dedent(
            """
            import '@testing-library/jest-dom';
            """
        ).strip(),
        "frontend/index.html": textwrap.dedent(
            """
            <!doctype html>
            <html lang="en">
              <head>
                <meta charset="UTF-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1.0" />
                <title>Budget Tracker</title>
              </head>
              <body>
                <div id="root"></div>
                <script type="module" src="/src/main.tsx"></script>
              </body>
            </html>
            """
        ).strip(),
        "frontend/src/__tests__/App.test.tsx": textwrap.dedent(
            """
            import { describe, it, expect } from '@jest/globals';
            import { render, screen } from '@testing-library/react';
            import App from '../App';

            describe('Budget Tracker hero (FR trace)', () => {
              it('renders the add expense CTA tied to FR-001', () => {
                render(<App />);
                expect(screen.getByText(/Add expense/i)).toBeInTheDocument();
              });
            });
            """
        ).strip(),
        "frontend/src/main.tsx": textwrap.dedent(
            """
            import React from "react";
            import ReactDOM from "react-dom/client";
            import App from "./App";
            import "./styles.css";

            ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
              <React.StrictMode>
                <App />
              </React.StrictMode>,
            );
            """
        ).strip(),
        "frontend/src/data/sampleExpenses.ts": textwrap.dedent(
            """
            export interface Expense {
              id: string;
              description: string;
              amount: number;
              category: string;
            }

            export const DEFAULT_CATEGORIES = [
              "Food",
              "Transportation",
              "Entertainment",
              "Utilities",
              "Shopping",
              "Healthcare",
              "Other",
            ];

            export const SAMPLE_EXPENSES: Expense[] = [
              { id: "1", description: "Groceries", amount: 85.5, category: "Food" },
              { id: "2", description: "Gas", amount: 45, category: "Transportation" },
              { id: "3", description: "Netflix", amount: 15.99, category: "Entertainment" },
            ];
            """
        ).strip(),
        "frontend/src/App.tsx": textwrap.dedent(
            """
            import { useMemo, useState } from "react";
            import {
              DEFAULT_CATEGORIES,
              SAMPLE_EXPENSES,
              type Expense,
            } from "./data/sampleExpenses";

            interface FormState {
              description: string;
              amount: string;
              category: string;
            }

            export default function App() {
              const [expenses, setExpenses] = useState<Expense[]>(SAMPLE_EXPENSES);
              const [form, setForm] = useState<FormState>({
                description: "",
                amount: "",
                category: DEFAULT_CATEGORIES[0],
              });

              const totals = useMemo(() => {
                return expenses.reduce<Record<string, number>>((acc, expense) => {
                  acc[expense.category] = (acc[expense.category] ?? 0) + expense.amount;
                  return acc;
                }, {});
              }, [expenses]);

              const totalAmount = useMemo(
                () => expenses.reduce((sum, expense) => sum + expense.amount, 0),
                [expenses],
              );

              function resetForm() {
                setForm({ description: "", amount: "", category: DEFAULT_CATEGORIES[0] });
              }

              function handleChange(event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) {
                const { name, value } = event.target;
                setForm((prev) => ({ ...prev, [name]: value }));
              }

              function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
                event.preventDefault();
                const amount = Number(form.amount);
                if (!form.description.trim() || Number.isNaN(amount) || amount <= 0) {
                  alert("Enter a description and a positive amount.");
                  return;
                }
                const newExpense: Expense = {
                  id: crypto.randomUUID(),
                  description: form.description.trim(),
                  amount,
                  category: form.category,
                };
                setExpenses((prev) => [newExpense, ...prev]);
                resetForm();
              }

              function handleDelete(id: string) {
                setExpenses((prev) => prev.filter((expense) => expense.id !== id));
              }

              function handleEdit(expense: Expense) {
                setForm({
                  description: expense.description,
                  amount: expense.amount.toString(),
                  category: expense.category,
                });
                setExpenses((prev) => prev.filter((item) => item.id !== expense.id));
              }

              return (
                <div className="app-shell">
                  <header className="app-header">
                    <h1>{project_name} Budget Tracker</h1>
                    <p className="app-subtitle">
                      Track spending by category, edit entries inline, and keep an up-to-date running total.
                    </p>
                  </header>

                  <section className="card">
                    <h2>Add New Expense</h2>
                    <form className="expense-form" onSubmit={handleSubmit}>
                      <label className="field">
                        <span>Description</span>
                        <input
                          type="text"
                          name="description"
                          placeholder="e.g. Grocery run"
                          required
                        />
                      </label>
                      <label className="field">
                        <span>Amount</span>
                        <input
                          type="number"
                          name="amount"
                          min="0"
                          step="0.01"
                          required
                        />
                      </label>
                      <label className="field">
                        <span>Category</span>
                        <select name="category" id="category-select"></select>
                      </label>
                      <div className="form-actions">
                        <button type="submit" className="primary">
                          Add
                        </button>
                        <button type="button" onClick={resetForm}>
                          Reset
                        </button>
                      </div>
                    </form>
                  </section>

                  <section className="card">
                    <h2>Summary by Category</h2>
                    <div className="summary-grid" id="summary-grid"></div>
                  </section>

                  <section className="card">
                    <header className="card-header">
                      <h2>All Expenses</h2>
                      <span className="total">Total Expenses: $0.00</span>
                    </header>
                    <ul className="expense-list" id="expense-list"></ul>
                    <p className="empty" id="empty-state" hidden>No expenses yet. Add your first entry above!</p>
                  </section>
                </div>
              );
            }
            """
        ).strip(),
        "frontend/src/styles.css": textwrap.dedent(
            """
            :root {
              color: #0b1220;
              background: linear-gradient(135deg, #f1f5ff 0%, #f9fcff 100%);
              font-family: "Inter", system-ui, sans-serif;
            }

            body {
              margin: 0;
              background: #f5f7ff;
            }

            .app-shell {
              max-width: 960px;
              margin: 40px auto;
              padding: 0 20px 60px;
              display: grid;
              gap: 24px;
            }

            .app-header {
              display: grid;
              gap: 8px;
              text-align: center;
            }

            .app-header h1 {
              margin: 0;
              font-size: clamp(2rem, 4vw, 3rem);
            }

            .app-subtitle {
              margin: 0;
              color: rgba(11, 18, 32, 0.65);
            }

            .card {
              background: #fff;
              padding: 20px clamp(20px, 3vw, 28px);
              border-radius: 18px;
              box-shadow: 0 20px 40px rgba(32, 41, 74, 0.1);
              display: grid;
              gap: 18px;
            }

            .card h2 {
              margin: 0;
              font-size: 1.4rem;
            }

            .expense-form {
              display: grid;
              gap: 14px;
            }

            .field {
              display: grid;
              gap: 6px;
            }

            .field input,
            .field select {
              border: 1px solid rgba(32, 41, 74, 0.2);
              border-radius: 10px;
              padding: 10px 12px;
              font-size: 1rem;
            }

            .form-actions {
              display: flex;
              gap: 10px;
            }

            button.primary {
              background: linear-gradient(135deg, #2955ff, #6a7dff);
              color: #fff;
              border-radius: 999px;
              padding: 10px 22px;
              border: none;
              cursor: pointer;
              font-weight: 600;
              letter-spacing: 0.4px;
            }

            button.primary:hover {
              filter: brightness(1.02);
            }

            .form-actions button {
              border-radius: 999px;
              padding: 10px 22px;
              border: none;
              cursor: pointer;
              font-weight: 600;
            }

            .form-actions button:not(.primary) {
              background: rgba(32, 41, 74, 0.08);
              color: #20294a;
            }

            .summary-grid {
              display: grid;
              gap: 12px;
              grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
            }

            .summary-tile {
              background: rgba(41, 85, 255, 0.08);
              border-radius: 14px;
              padding: 16px;
              display: grid;
              gap: 6px;
              text-align: center;
            }

            .summary-label {
              text-transform: uppercase;
              font-size: 0.75rem;
              letter-spacing: 0.6px;
              color: rgba(32, 41, 74, 0.56);
            }

            .expense-list {
              list-style: none;
              margin: 0;
              padding: 0;
              display: grid;
              gap: 12px;
            }

            .expense-item {
              display: flex;
              justify-content: space-between;
              align-items: center;
              padding: 12px 16px;
              border-radius: 12px;
              border: 1px solid rgba(32, 41, 74, 0.12);
              gap: 12px;
              background: rgba(255, 255, 255, 0.92);
            }

            .expense-meta {
              display: block;
              font-size: 0.78rem;
              color: rgba(32, 41, 74, 0.55);
            }

            .expense-actions {
              display: flex;
              align-items: center;
              gap: 10px;
            }

            .expense-actions button {
              border: none;
              background: transparent;
              cursor: pointer;
              font-size: 1rem;
            }

            .expense-amount {
              font-weight: 600;
            }

            .empty {
              margin: 0;
              color: rgba(32, 41, 74, 0.55);
              text-align: center;
            }

            .card-header {
              display: flex;
              justify-content: space-between;
              align-items: baseline;
            }

            .total {
              font-size: 1.1rem;
              font-weight: 700;
            }
            """
        ).strip(),
    }


def _compose_capability_summary(project_name: str, fr_refs: Iterable[str], nfr_refs: Iterable[str], preview_meta: Optional[Dict[str, Any]] = None) -> str:
    meta = dict(preview_meta or {})
    title = meta.get("title") or project_name or "Interactive Prototype"
    fr_list = sorted({ref.upper() for ref in fr_refs if ref})
    nfr_list = sorted({ref.upper() for ref in nfr_refs if ref})
    fr_trace = ", ".join(fr_list) if fr_list else "Pending mapping"
    nfr_trace = ", ".join(nfr_list) if nfr_list else "Pending instrumentation"
    hero_callout = meta.get("tagline") or "Feature-aligned prototype snapshot"
    return textwrap.dedent(
        f"""
        ## {title} – Capability & Traceability Snapshot

        _{hero_callout}_

        | Component | Description | Trace References |
        | --- | --- | --- |
        | FastAPI_rules service | YAML-driven evaluation with decision triage and observability hooks | {fr_trace} |
        | React experience layer | High-fidelity UI preview instrumented for telemetry | {fr_trace if fr_list else "FR alignment pending"} |
        | Quality & guardrails | PyTest + Jest scaffolding with NFR checkpoints | {nfr_trace if nfr_list else "NFR mapping pending"} |

        ### Test Scaffolding
        - `tests/test_clinical_rules.py` defends the critical rules engine with scenario coverage.
        - `frontend/src/__tests__/App.test.tsx` boots the SPA with Jest + Testing Library to verify interaction flows.
        - Extend suites with feature-specific scenarios to raise coverage above guardrail targets.
        """
    ).strip()


def _compose_ready_to_run_instructions() -> str:
    return textwrap.dedent(
        """
        ### How to use this scaffold

        1. Download the **Ready-to-run bundle** artifact from the accelerator sidebar, or copy the `Ready-to-run bundle (Base64)` text into `bundle.b64`.
        2. If using the Base64 text, decode and extract the archive:

           ```bash
           base64 -d bundle.b64 > scaffolding.zip
           unzip scaffolding.zip
           ```

        3. Follow the README in the extracted folder to install dependencies, run the backend/frontend, and execute both PyTest and Jest suites (`npm test`).
        4. Update `config/rules.yaml` to tailor the rule logic for your project, and extend the Jest test to codify UI acceptance criteria traced to FR/NFRs.
        """
    ).strip()


def _build_live_preview_html(preview_meta: Dict[str, Any]) -> str:
    meta = dict(preview_meta or {})
    theme = dict(meta.get("theme") or {})

    def _theme_value(key: str, fallback: str) -> str:
        value = theme.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return fallback

    palette = {
        "background": _theme_value("background", "#0b1120"),
        "surface": _theme_value("surface", "#ffffff"),
        "surface_alt": _theme_value("surface_alt", "rgba(255, 255, 255, 0.08)"),
        "primary": _theme_value("primary", "#7c3aed"),
        "primary_soft": _theme_value("primary_soft", "rgba(124, 58, 237, 0.14)"),
        "accent": _theme_value("accent", "#22d3ee"),
        "accent_soft": _theme_value("accent_soft", "rgba(34, 211, 238, 0.16)"),
        "gradient": _theme_value("gradient", "linear-gradient(135deg, #7c3aed 0%, #f472b6 100%)"),
        "text_primary": _theme_value("text_primary", "#0b1120"),
        "text_muted": _theme_value("text_muted", "rgba(11, 17, 32, 0.72)"),
        "border": _theme_value("border", "rgba(11, 17, 32, 0.12)"),
    }

    title = html.escape(str(meta.get("title") or "Interactive Prototype"))
    tagline = html.escape(str(meta.get("tagline") or "Modern product preview."))
    call_to_action = html.escape(str(meta.get("call_to_action") or "Launch experience"))
    secondary_action = html.escape(str(meta.get("secondary_action") or "Review instrumentation"))
    form_title = html.escape(str(meta.get("form_title") or "Submit sample data"))
    form_description = html.escape(str(meta.get("form_description") or "Exercise the workflow with representative values."))
    footer_text = html.escape(str(meta.get("footer") or ""))
    status_text = html.escape(str(meta.get("status_text") or "Live prototype"))

    metrics = meta.get("metrics") if isinstance(meta.get("metrics"), list) else []
    highlights = meta.get("highlights") if isinstance(meta.get("highlights"), list) else []
    form_fields = meta.get("form_fields") if isinstance(meta.get("form_fields"), list) else []

    if not metrics:
        metrics = [
            {"label": "Functional coverage", "value": "Trace pending", "hint": "Link requirements"},
            {"label": "NFR guardrail", "value": "TBD", "hint": "Observe performance"},
        ]
    if not highlights:
        highlights = [
            "Modular architecture ready for iteration.",
            "Instrumentation hooks baked in for observability.",
        ]
    if not form_fields:
        form_fields = [
            {"label": "Primary input", "type": "text", "placeholder": "Enter sample value"},
            {"label": "Secondary input", "type": "text", "placeholder": "Add context for validation"},
        ]

    metric_blocks: List[str] = []
    for item in metrics:
        label = html.escape(str(item.get("label") or "Metric"))
        value = html.escape(str(item.get("value") or "—"))
        hint = html.escape(str(item.get("hint") or ""))
        metric_blocks.append(
            (
                """
                <article class="metric-card" role="group" aria-label="{label}">
                  <span class="metric-label">{label}</span>
                  <span class="metric-value">{value}</span>
                  <span class="metric-hint">{hint}</span>
                </article>
                """
            ).format(label=label, value=value, hint=hint).strip()
        )
    metrics_html = "\n".join(metric_blocks)

    highlight_blocks: List[str] = []
    for highlight in highlights:
        highlight_blocks.append(
            f"<li class=\"highlight-item\">{html.escape(str(highlight))}</li>"
        )
    highlights_html = "\n".join(highlight_blocks)

    form_blocks: List[str] = []
    for idx, field in enumerate(form_fields):
        label_text = html.escape(str(field.get("label") or f"Field {idx + 1}"))
        field_type = html.escape(str(field.get("type") or "text").lower())
        placeholder = html.escape(str(field.get("placeholder") or ""))
        field_id = _slugify(field.get("label") or f"field-{idx + 1}")
        form_blocks.append(
            (
                """
                <label class="field" for="{field_id}">
                  <span>{label}</span>
                  <input id="{field_id}" name="{field_id}" type="{field_type}" placeholder="{placeholder}" required />
                </label>
                """
            ).format(field_id=field_id, label=label_text, field_type=field_type, placeholder=placeholder).strip()
        )
    form_fields_html = "\n".join(form_blocks)

    status_text_js = json.dumps(str(meta.get("status_text") or "Live prototype"))
    call_to_action_js = json.dumps(str(meta.get("call_to_action") or "Launch experience"))
    secondary_action_js = json.dumps(str(meta.get("secondary_action") or "Review instrumentation"))

    footer_block = f"<footer class=\"app-footer\">{footer_text}</footer>" if footer_text else ""

    return textwrap.dedent(
        f"""
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>{title} Preview</title>
            <style>
              :root {{
                color-scheme: light;
                --bg: {palette['background']};
                --surface: {palette['surface']};
                --surface-alt: {palette['surface_alt']};
                --primary: {palette['primary']};
                --primary-soft: {palette['primary_soft']};
                --accent: {palette['accent']};
                --accent-soft: {palette['accent_soft']};
                --gradient: {palette['gradient']};
                --text-primary: {palette['text_primary']};
                --text-muted: {palette['text_muted']};
                --border: {palette['border']};
                font-family: "Inter", "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
                background: var(--bg);
                color: var(--text-primary);
              }}

              * {{ box-sizing: border-box; }}

              body {{
                margin: 0;
                background: linear-gradient(180deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0.35)), var(--bg);
                min-height: 100vh;
              }}

              header.hero {{
                display: grid;
                gap: 1rem;
                padding: clamp(2.5rem, 7vw, 4rem) clamp(1.5rem, 4vw, 3rem) clamp(1.5rem, 4vw, 3rem);
                background: var(--gradient);
                color: #fff;
                border-bottom-left-radius: 32px;
                border-bottom-right-radius: 32px;
                position: relative;
                overflow: hidden;
              }}

              header.hero::after {{
                content: "";
                position: absolute;
                inset: 0;
                background: radial-gradient(circle at top right, rgba(255, 255, 255, 0.35), transparent 55%);
                pointer-events: none;
              }}

              header.hero h1 {{
                margin: 0;
                font-size: clamp(2.6rem, 6vw, 3.8rem);
                letter-spacing: -0.02em;
              }}

              header.hero p {{
                max-width: 54ch;
                margin: 0;
                font-size: clamp(1.05rem, 3vw, 1.35rem);
                color: rgba(255, 255, 255, 0.88);
              }}

              .status-pill {{
                display: inline-flex;
                align-items: center;
                gap: 0.4rem;
                border-radius: 999px;
                padding: 0.35rem 0.85rem;
                background: rgba(255, 255, 255, 0.14);
                color: #fff;
                font-size: 0.85rem;
                width: fit-content;
              }}

              .status-dot {{
                width: 0.5rem;
                height: 0.5rem;
                border-radius: 999px;
                background: #4ade80;
                box-shadow: 0 0 0 4px rgba(74, 222, 128, 0.12);
              }}

              .actions {{
                display: flex;
                flex-wrap: wrap;
                gap: 0.75rem;
                margin-top: 0.5rem;
              }}

              .actions button {{
                border: none;
                border-radius: 999px;
                padding: 0.85rem 1.8rem;
                font-weight: 600;
                letter-spacing: 0.01em;
                cursor: pointer;
                transition: transform 160ms ease, box-shadow 160ms ease;
              }}

              .actions button.primary {{
                background: #ffffff;
                color: var(--text-primary);
                box-shadow: 0 16px 35px rgba(15, 17, 35, 0.18);
              }}

              .actions button.secondary {{
                background: rgba(255, 255, 255, 0.12);
                color: #fff;
                border: 1px solid rgba(255, 255, 255, 0.28);
              }}

              .actions button:active {{ transform: translateY(1px); }}

              main {{
                margin: clamp(-2.5rem, -6vw, -3.5rem) auto 3rem;
                padding: 0 clamp(1.25rem, 5vw, 2.5rem) 4rem;
                max-width: 1120px;
                display: grid;
                gap: clamp(1.75rem, 4vw, 2.5rem);
              }}

              .panel {{
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: 24px;
                box-shadow: 0 18px 48px rgba(15, 23, 42, 0.12);
                padding: clamp(1.5rem, 4vw, 2.4rem);
                display: grid;
                gap: clamp(1.25rem, 3vw, 1.8rem);
              }}

              .panel header {{
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                gap: 1.2rem;
              }}

              .panel header h2 {{
                margin: 0;
                font-size: clamp(1.35rem, 3vw, 1.65rem);
                letter-spacing: -0.01em;
              }}

              .panel header p {{
                margin: 0;
                color: var(--text-muted);
                max-width: 42ch;
                font-size: 0.98rem;
              }}

              .metrics-grid {{
                display: grid;
                gap: 1rem;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
              }}

              .metric-card {{
                background: var(--surface-alt);
                border-radius: 18px;
                padding: 1.2rem 1.4rem;
                display: grid;
                gap: 0.45rem;
              }}

              .metric-label {{
                text-transform: uppercase;
                font-size: 0.75rem;
                letter-spacing: 0.16em;
                color: var(--text-muted);
              }}

              .metric-value {{
                font-size: 1.4rem;
                font-weight: 700;
              }}

              .metric-hint {{
                font-size: 0.88rem;
                color: var(--text-muted);
              }}

              .layout {{
                display: grid;
                grid-template-columns: minmax(0, 1fr);
                gap: clamp(1.75rem, 4vw, 2.6rem);
              }}

              @media (min-width: 980px) {{
                .layout {{
                  grid-template-columns: minmax(0, 1.8fr) minmax(0, 1.15fr);
                  align-items: start;
                }}
              }}

              form.intake-form {{
                display: grid;
                gap: 1rem;
              }}

              .field {{
                display: grid;
                gap: 0.45rem;
              }}

              .field input,
              .field textarea {{
                padding: 0.9rem 1rem;
                border-radius: 14px;
                border: 1px solid var(--border);
                font-size: 1rem;
                background: rgba(255,255,255,0.92);
                transition: border 150ms ease, box-shadow 150ms ease;
              }}

              .field input:focus-visible,
              .field textarea:focus-visible {{
                outline: none;
                border-color: var(--primary);
                box-shadow: 0 0 0 4px var(--primary_soft);
              }}

              .intake-actions {{
                display: flex;
                gap: 0.75rem;
                flex-wrap: wrap;
              }}

              .intake-actions button {{
                border-radius: 12px;
                padding: 0.75rem 1.4rem;
                border: none;
                cursor: pointer;
                font-weight: 600;
                background: var(--primary);
                color: #fff;
              }}

              .intake-actions button.secondary {{
                background: transparent;
                color: var(--text-primary);
                border: 1px solid var(--border);
              }}

              ul.highlights {{
                list-style: none;
                margin: 0;
                padding: 0;
                display: grid;
                gap: 0.85rem;
              }}

              .highlight-item {{
                padding: 0.95rem 1.1rem;
                border-radius: 14px;
                background: var(--surface-alt);
                border: 1px solid rgba(255, 255, 255, 0.08);
              }}

              .activity-feed {{
                display: grid;
                gap: 0.85rem;
              }}

              .activity-item {{
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                gap: 0.75rem;
                padding: 0.9rem 1.1rem;
                background: var(--surface-alt);
                border-radius: 14px;
                border: 1px dashed rgba(255, 255, 255, 0.06);
              }}

              .activity-item strong {{ font-size: 0.95rem; }}

              .activity-item time {{
                font-size: 0.82rem;
                color: var(--text-muted);
              }}

              .app-footer {{
                margin-top: 1rem;
                font-size: 0.85rem;
                color: rgba(255, 255, 255, 0.74);
                text-align: center;
              }}

              @media (prefers-reduced-motion: reduce) {{
                *, *::before, *::after {{
                  animation-duration: 0.01ms !important;
                  animation-iteration-count: 1 !important;
                  transition-duration: 0.01ms !important;
                  scroll-behavior: auto !important;
                }}
              }}
            </style>
          </head>
          <body>
            <header class="hero">
              <span class="status-pill" data-role="status-pill">
                <span class="status-dot" aria-hidden="true"></span>
                <span class="status-label">{status_text}</span>
              </span>
              <h1>{title}</h1>
              <p>{tagline}</p>
              <div class="actions">
                <button class="primary" type="button" data-role="primary-action">{call_to_action}</button>
                <button class="secondary" type="button" data-role="secondary-action">{secondary_action}</button>
              </div>
            </header>

            <main>
              <section class="panel" aria-labelledby="metrics-heading">
                <header>
                  <div>
                    <h2 id="metrics-heading">Operational readiness</h2>
                    <p>Key delivery signals the team should monitor as we evolve this prototype.</p>
                  </div>
                </header>
                <div class="metrics-grid">
{textwrap.indent(metrics_html, '                  ')}
                </div>
              </section>

              <div class="layout">
                <section class="panel" aria-labelledby="intake-heading">
                  <header>
                    <div>
                      <h2 id="intake-heading">{form_title}</h2>
                      <p>{form_description}</p>
                    </div>
                  </header>
                  <form class="intake-form" data-role="intake-form">
{textwrap.indent(form_fields_html, '                    ')}
                    <div class="intake-actions">
                      <button type="submit">Capture sample</button>
                      <button class="secondary" type="reset">Clear</button>
                    </div>
                  </form>
                </section>

                <section class="panel" aria-labelledby="highlights-heading">
                  <header>
                    <div>
                      <h2 id="highlights-heading">Experience highlights</h2>
                      <p>Use these talking points during stakeholder reviews and design playback sessions.</p>
                    </div>
                  </header>
                  <ul class="highlights">
{textwrap.indent(highlights_html, '                    ')}
                  </ul>
                </section>
              </div>

              <section class="panel" aria-labelledby="activity-heading">
                <header>
                  <div>
                    <h2 id="activity-heading">Recent prototype activity</h2>
                    <p>Interactions captured while exploring the preview. Use this to validate traceability.</p>
                  </div>
                </header>
                <div class="activity-feed" data-role="activity-feed">
                  <div class="activity-item">
                    <div>
                      <strong>Prototype initialized</strong>
                      <p class="metric-hint">Session token established. Observability hooks armed.</p>
                    </div>
                    <time data-role="activity-time" datetime="">Moments ago</time>
                  </div>
                </div>
              </section>
            </main>
            {footer_block}

            <script>
              const statusText = {status_text_js};
              const primaryLabel = {call_to_action_js};
              const secondaryLabel = {secondary_action_js};

              const statusPill = document.querySelector('[data-role="status-pill"]');
              const statusLabel = statusPill?.querySelector('.status-label');
              const activityFeed = document.querySelector('[data-role="activity-feed"]');
              const intakeForm = document.querySelector('[data-role="intake-form"]');
              const primaryAction = document.querySelector('[data-role="primary-action"]');
              const secondaryAction = document.querySelector('[data-role="secondary-action"]');

              if (statusLabel) {{
                statusLabel.textContent = statusText;
              }}

              function addActivity(text, meta) {{
                if (!activityFeed) return;
                const item = document.createElement('div');
                item.className = 'activity-item';
                const timestamp = new Date();
                const timeEl = document.createElement('time');
                timeEl.dateTime = timestamp.toISOString();
                timeEl.textContent = timestamp.toLocaleTimeString([], {{ hour: '2-digit', minute: '2-digit' }});
                const strong = document.createElement('strong');
                strong.textContent = text;
                const hint = document.createElement('p');
                hint.className = 'metric-hint';
                hint.textContent = meta || 'Captured via preview instrumentation.';
                const content = document.createElement('div');
                content.appendChild(strong);
                content.appendChild(hint);
                item.appendChild(content);
                item.appendChild(timeEl);
                activityFeed.prepend(item);
              }}

              if (intakeForm) {{
                intakeForm.addEventListener('submit', (event) => {{
                  event.preventDefault();
                  const formData = new FormData(intakeForm);
                  const summary = Array.from(formData.entries())
                    .map(([key, value]) => `${{key}}: ${{value}}`)
                    .join(' • ');
                  addActivity('Intake captured', summary || 'Fields recorded.');
                  intakeForm.reset();
                }});

                intakeForm.addEventListener('reset', () => {{
                  addActivity('Form cleared', 'Input fields cleared for next scenario.');
                }});
              }}

              if (primaryAction) {{
                primaryAction.textContent = primaryLabel;
                primaryAction.addEventListener('click', () => {{
                  addActivity(primaryLabel, 'Primary flow triggered. Monitoring metrics…');
                }});
              }}

              if (secondaryAction) {{
                secondaryAction.textContent = secondaryLabel;
                secondaryAction.addEventListener('click', () => {{
                  addActivity(secondaryLabel, 'Secondary telemetry ping acknowledged.');
                }});
              }}
            </script>
          </body>
        </html>
        """
    ).strip()


def _extract_requirement_refs(text: str, prefix: str) -> List[str]:
    pattern = re.compile(rf"{re.escape(prefix)}-\d+", re.IGNORECASE)
    refs = {match.upper() for match in pattern.findall(text or "")}
    return sorted(refs)


def _summarize_diff(previous: Optional[str], current: str, max_lines: int = 12) -> str:
    prev = (previous or "").splitlines()
    curr = (current or "").splitlines()
    if not prev:
        return "Initial version"
    diff_lines = list(difflib.unified_diff(prev, curr, fromfile="previous", tofile="current", lineterm=""))
    if not diff_lines:
        return "No changes"
    excerpt = diff_lines[:max_lines]
    if len(diff_lines) > max_lines:
        excerpt.append("… (diff truncated)")
    return "\n".join(excerpt)


def _compute_gate_stage(kind: str) -> str:
    mapping = {
        "code": "implementation",
        "test": "testing",
        "config": "governance",
        "summary": "analysis",
        "bundle": "implementation",
    }
    return mapping.get(kind, "unspecified")


def _infer_kind_from_path(path: str) -> str:
    lowered = path.lower()
    if lowered.endswith(('.md', '.markdown', '.txt')):
        return "summary"
    if lowered.endswith(('.yaml', '.yml', '.json', '.toml', '.env')):
        return "config"
    if lowered.endswith(('.spec.ts', '.spec.tsx', '.spec.js', '.test.ts', '.test.tsx', '.test.js', '.py')) and (
        'test' in Path(path).name.lower()
    ):
        return "test"
    return "code"


def _infer_language_from_path(path: str, default: str = "text") -> str:
    lowered = path.lower()
    if lowered.endswith('.py'):
        return "python"
    if lowered.endswith(('.ts', '.tsx')):
        return "typescript"
    if lowered.endswith('.js'):
        return "javascript"
    if lowered.endswith('.jsx'):
        return "jsx"
    if lowered.endswith('.css'):
        return "css"
    if lowered.endswith(('.yaml', '.yml')):
        return "yaml"
    if lowered.endswith('.json'):
        return "json"
    if lowered.endswith('.html'):
        return "html"
    if lowered.endswith('.md'):
        return "markdown"
    return default


def _strip_json_block(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        while lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _parse_code_payload(raw: str) -> Optional[Dict[str, Any]]:
    candidate = _strip_json_block(raw)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _fallback_code_payload(latest_input: str) -> Dict[str, Any]:
    note = "Fallback scaffold generated because the LLM response could not be parsed."
    if latest_input.strip():
        note = f"{note} Latest request: {latest_input.strip()}"

    code_content = textwrap.dedent(
        '''
        from typing import Any, Dict, List


        def evaluate_intake(intake: Dict[str, Any], rules: List[Dict[str, Any]]) -> List[Dict[str, str]]:
            """Evaluate an intake submission against configured clinical rules."""
            alerts: List[Dict[str, str]] = []

            age = intake.get("age")
            if isinstance(age, (int, float)) and age >= 65:
                alerts.append(
                    {
                        "type": "clinical",
                        "severity": "high",
                        "message": "Age 65+ requires nurse triage",
                    }
                )

            symptom_values = intake.get("symptoms", [])
            symptoms_text = " ".join(str(item) for item in symptom_values).lower()
            if "chest pain" in symptoms_text:
                alerts.append(
                    {
                        "type": "clinical",
                        "severity": "high",
                        "message": "Chest pain flagged for immediate review",
                    }
                )

            insurance = intake.get("insurance") or {}
            if not isinstance(insurance, dict) or not insurance.get("member_id"):
                alerts.append(
                    {
                        "type": "administrative",
                        "severity": "medium",
                        "message": "Insurance information incomplete",
                    }
                )

            return alerts
        '''
    ).strip()

    test_content = textwrap.dedent(
        '''
        import pytest

        from src.orchestrator.services.clinical_rules import evaluate_intake


        @pytest.mark.parametrize(
            "payload,expected_types",
            [
                ({"age": 70}, {"clinical"}),
                ({"symptoms": ["Chest pain"]}, {"clinical"}),
                ({"insurance": {}}, {"administrative"}),
            ],
        )
        def test_evaluate_intake_flags(payload, expected_types):
            alerts = evaluate_intake(payload, [])
            assert {item["type"] for item in alerts} == expected_types
        '''
    ).strip()

    config_content = textwrap.dedent(
        '''
        - id: age_high_risk
          description: Flag seniors for clinical review.
          when:
            all:
              - field: age
                operator: gte
                value: 65
          alert:
            type: clinical
            severity: high
            message: Age 65+ requires nurse triage

        - id: chest_pain
          description: Escalate patients reporting chest pain.
          when:
            any:
              - field: symptoms
                operator: contains
                value: chest pain
          alert:
            type: clinical
            severity: high
            message: Chest pain flagged for immediate review

        - id: missing_insurance
          description: Prompt staff to complete insurance paperwork.
          when:
            all:
              - field: insurance.member_id
                operator: blank
          alert:
            type: administrative
            severity: medium
            message: Insurance information incomplete
        '''
    ).strip()

    return {
        "code": {
            "path": _DEFAULT_CODE_PATH,
            "language": "python",
            "content": code_content,
        },
        "tests": {
            "path": _DEFAULT_TEST_PATH,
            "language": "python",
            "content": test_content,
        },
        "config": {
            "path": _DEFAULT_CONFIG_PATH,
            "language": "yaml",
            "content": config_content,
        },
        "notes": [note],
        "source": "fallback",
    }


def _compose_code_generation_prompt(intent: ChatIntent, latest_input: str, conversation_excerpt: str) -> str:
    focus = intent.requirement_area or intent.title
    latest_block = latest_input.strip() or "No additional details supplied."
    convo_block = conversation_excerpt.strip() or "No prior conversation available."
    return textwrap.dedent(
        f"""
        You are assisting the engineering team with "{intent.title}" focused on {focus}.
        Generate production-ready scaffolding for a Python FastAPI capability that evaluates intake submissions using YAML-configurable rules.

        Latest engineer request:
        {latest_block}

        Conversation summary:
        {convo_block}

        Requirements:
        - Primary service must live at {_DEFAULT_CODE_PATH} and expose `evaluate_intake(intake: Dict[str, Any], rules: List[Dict[str, Any]]) -> List[Dict[str, str]]`.
        - Provide pytest-based tests located at {_DEFAULT_TEST_PATH} covering age >= 65, chest pain symptoms, and missing insurance member IDs.
        - Supply a YAML sample at {_DEFAULT_CONFIG_PATH} that demonstrates rule definitions with fields, operators, and alert metadata.
        - Avoid external dependencies beyond the Python standard library.
        - Return ONLY JSON with the following shape:
          {{
            "code": {{"path": "...", "language": "python", "content": "..."}},
            "tests": {{"path": "...", "language": "python", "content": "..."}},
            "config": {{"path": "...", "language": "yaml", "content": "..."}},
            "notes": ["...", "..."]
          }}
        - Escape newlines using `\\n` so the JSON parses cleanly.
        """
    ).strip()


def _normalise_code_sections(payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    sections: List[Dict[str, Any]] = []
    defaults = {
        "code": ("code", _DEFAULT_CODE_PATH, "python"),
        "tests": ("test", _DEFAULT_TEST_PATH, "python"),
        "config": ("config", _DEFAULT_CONFIG_PATH, "yaml"),
    }
    for key, (kind, default_path, default_language) in defaults.items():
        section = payload.get(key)
        if not isinstance(section, dict):
            continue
        path = str(section.get("path") or default_path)
        language = str(section.get("language") or default_language)
        content = section.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        sections.append(
            {
                "kind": kind,
                "path": path,
                "language": language,
                "content": content.strip(),
            }
        )

    notes_field = payload.get("notes")
    if isinstance(notes_field, list):
        notes = [str(item).strip() for item in notes_field if str(item).strip()]
    elif isinstance(notes_field, str) and notes_field.strip():
        notes = [notes_field.strip()]
    else:
        notes = []
    return sections, notes


def _generate_code_payload(session: AcceleratorSession, intent: ChatIntent, latest_input: str) -> Dict[str, Any]:
    store = get_accelerator_store()
    recent_messages = store.list_messages(session.session_id)
    history = [
        {"role": msg.role, "content": msg.content}
        for msg in recent_messages[-8:]
    ]
    prompt = _compose_code_generation_prompt(intent, latest_input, "\n".join(
        f"{msg.role.upper()}: {msg.content.strip()}"
        for msg in recent_messages[-6:]
        if msg.content and msg.content.strip()
    ))

    response = reply_with_chat_ai(
        project_name=intent.title,
        user_message=prompt,
        history=history,
        attachments=None,
        persona=session.persona,
        intent_override="documentation",
        purpose_override="accelerator_code",
    )
    text = _coerce_text(response)
    payload = _parse_code_payload(text)
    if not payload:
        payload = _fallback_code_payload(latest_input)
    return _ensure_ready_bundle_flag(payload, latest_input)


def _publish_code_artifacts(
    session: AcceleratorSession,
    intent: ChatIntent,
    payload: Dict[str, Any],
    duration_ms: float,
    latest_input: str,
    *,
    trigger_message_id: Optional[str] = None,
) -> None:
    sections, notes = _normalise_code_sections(payload)
    if not sections:
        raise ValueError("code_generation_empty_sections")

    store = get_accelerator_store()
    doc_store = get_doc_store()
    _, revision = store.artifact_snapshot(session.session_id)
    version = revision + 1

    previous_previews = doc_store.list_accelerator_previews(session.session_id)

    bundle_files: Dict[str, str] = {}
    aggregate_fr_refs: set[str] = set()
    aggregate_nfr_refs: set[str] = set()
    for section in sections:
        content = section["content"]
        preview = content[:240]
        previous_match = next(
            (
                item
                for item in reversed(previous_previews)
                if item.get("filename") == section["path"]
            ),
            None,
        )
        previous_content = (
            str(previous_match.get("content")) if previous_match and previous_match.get("content") else ""
        )
        diff_summary = _summarize_diff(previous_content, content)
        fr_refs = _extract_requirement_refs(content, "FR")
        nfr_refs = _extract_requirement_refs(content, "NFR")
        aggregate_fr_refs.update(fr_refs)
        aggregate_nfr_refs.update(nfr_refs)
        gate_stage = _compute_gate_stage(section["kind"])
        meta = {
            "version": version,
            "type": section["kind"],
            "language": section["language"],
            "summary": preview,
            "diff_summary": diff_summary,
            "fr_refs": fr_refs,
            "nfr_refs": nfr_refs,
            "gate_stage": gate_stage,
        }
        if trigger_message_id:
            meta["message_id"] = trigger_message_id
        store.add_artifact(
            session.session_id,
            filename=section["path"],
            project_id=session.project_id,
            meta=meta,
        )
        doc_store.save_accelerator_preview(session.session_id, section["path"], content, meta)
        try:
            doc_store.save_accelerator_asset(
                session.session_id,
                section["path"],
                content.encode("utf-8"),
                meta,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            _emit_storage_error(session.session_id, section["path"], exc)
        _queue_linked_artifact(
            session.session_id,
            {
                "type": section["kind"],
                "title": section["path"],
                "preview": preview or "Generated artifact ready to copy.",
                "source": payload.get("source", "llm"),
                "version": version,
                "diff": diff_summary,
                "fr_refs": fr_refs,
                "nfr_refs": nfr_refs,
                "gate_stage": gate_stage,
                "filename": section["path"],
                "meta": meta,
            },
            message_id=trigger_message_id,
        )
        bundle_files[section["path"]] = content
        version += 1

    if notes:
        _queue_linked_artifact(
            session.session_id,
            {
                "type": "status",
                "title": "Code generation notes",
                "preview": " ".join(notes)[:240],
                "source": payload.get("source", "llm"),
            },
            message_id=trigger_message_id,
        )

    preview_meta = _infer_preview_metadata(
        latest_input,
        intent,
        aggregate_fr_refs,
        aggregate_nfr_refs,
    )
    preview_title = preview_meta.get("title") or intent.requirement_area or intent.title or "Interactive Prototype"
    slug = preview_meta.get("slug") or _slugify(preview_title)

    if bundle_files:
        include_ready_bundle = bool(payload.get("include_ready_bundle"))

        if include_ready_bundle:
            frontend_files = _default_frontend_scaffold(preview_title)
            bundle_files.update(frontend_files)
            bundle_files.setdefault("README.md", _build_ready_to_run_readme(preview_title))
            bundle_files.setdefault(
                "SUMMARY.md",
                _compose_capability_summary(
                    preview_title,
                    aggregate_fr_refs,
                    aggregate_nfr_refs,
                    preview_meta,
                ),
            )
            archive_bytes = _package_ready_to_run_bundle(bundle_files)
            archive_b64 = base64.b64encode(archive_bytes).decode("utf-8")
            bundle_filename = f"{slug}-bundle.zip"
            bundle_download_path = f"/accelerators/sessions/{session.session_id}/artifacts/{bundle_filename}/download"
            bundle_meta = {
                "version": version,
                "type": "bundle",
                "language": "binary",
                "summary": "Ready-to-run project bundle (ZIP)",
                "gate_stage": _compute_gate_stage("bundle"),
                "download_path": bundle_download_path,
            }
            store.add_artifact(
                session.session_id,
                filename=bundle_filename,
                project_id=session.project_id,
                meta=bundle_meta,
            )
            doc_store.save_accelerator_preview(
                session.session_id,
                bundle_filename,
                archive_b64,
                bundle_meta,
            )
            try:
                doc_store.save_accelerator_asset(session.session_id, bundle_filename, archive_bytes, bundle_meta)
            except Exception as exc:  # pragma: no cover - defensive logging
                _emit_storage_error(session.session_id, bundle_filename, exc)
            store.save_asset(session.session_id, bundle_filename, archive_bytes)
            _queue_linked_artifact(
                session.session_id,
                {
                    "type": "bundle",
                    "title": "Ready-to-run bundle",
                    "preview": "Download the ZIP to get the full scaffold.",
                    "source": payload.get("source", "llm"),
                    "version": version,
                    "download_path": bundle_download_path,
                },
                message_id=trigger_message_id,
            )
            version += 1

        live_preview_filename = f"{slug}-preview.html"
        live_preview_path = f"/accelerators/sessions/{session.session_id}/artifacts/{live_preview_filename}/preview"
        live_preview_html = _build_live_preview_html(preview_meta)
        live_preview_meta = {
            "version": version,
            "type": "preview",
            "language": "html",
            "title": preview_title,
            "summary": preview_meta.get("tagline") or "Interactive preview ready.",
            "gate_stage": _compute_gate_stage("code"),
            "iframe_url": live_preview_path,
            "preview_meta": preview_meta,
            "fr_refs": sorted(aggregate_fr_refs),
            "nfr_refs": sorted(aggregate_nfr_refs),
        }
        store.add_artifact(
            session.session_id,
            filename=live_preview_filename,
            project_id=session.project_id,
            meta=live_preview_meta,
        )
        doc_store.save_accelerator_preview(
            session.session_id,
            live_preview_filename,
            live_preview_html,
            live_preview_meta,
        )
        try:
            doc_store.save_accelerator_asset(
                session.session_id,
                live_preview_filename,
                live_preview_html.encode("utf-8"),
                live_preview_meta,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            _emit_storage_error(session.session_id, live_preview_filename, exc)
        _queue_linked_artifact(
            session.session_id,
            {
                "type": "preview",
                "title": preview_title,
                "preview": live_preview_meta["summary"],
                "source": "system",
                "version": version,
                "iframe_url": live_preview_path,
                "meta": live_preview_meta,
            },
            message_id=trigger_message_id,
        )
        version += 1

        if include_ready_bundle and bundle_files:
            if aggregate_fr_refs:
                primary_ref = next(iter(sorted(aggregate_fr_refs)))
            else:
                primary_ref = "FR-001"
            prototype_html = textwrap.dedent(
                f"""
                <!doctype html>
                <html lang="en">
                  <head>
                    <meta charset="utf-8" />
                    <title>Interactive Prototype</title>
                    <style>
                      body {{ font-family: Arial, sans-serif; margin: 1.5rem; }}
                      .trace {{ font-weight: 600; color: #0b7285; }}
                      button {{ padding: 0.5rem 1rem; border-radius: 0.5rem; border: none; background: #15aabf; color: #fff; }}
                    </style>
                  </head>
                  <body>
                    <h1>Capability Prototype</h1>
                    <p>This interaction aligns with <span class="trace">{primary_ref}</span>{' and ' + ', '.join(sorted(aggregate_nfr_refs)) if aggregate_nfr_refs else ''}.</p>
                    <button id="prototype-action">Simulate Decision</button>
                    <p id="prototype-status">Awaiting input…</p>
                    <script>
                      document.getElementById("prototype-action").addEventListener("click", () => {{
                        const ts = new Date().toISOString();
                        document.getElementById("prototype-status").innerText = "Decision captured @ " + ts + " (trace: {primary_ref})";
                      }});
                    </script>
                  </body>
                </html>
                """
            ).strip()
            prototype_meta = {
                "version": version,
                "type": "prototype",
                "language": "html",
                "summary": "Interactive HTML prototype snippet aligned to FR requirements.",
                "gate_stage": _compute_gate_stage("code"),
                "fr_refs": sorted(aggregate_fr_refs) or [primary_ref],
                "nfr_refs": sorted(aggregate_nfr_refs),
            }
            store.add_artifact(
                session.session_id,
                filename="prototype-inline.html",
                project_id=session.project_id,
                meta=prototype_meta,
            )
            doc_store.save_accelerator_preview(
                session.session_id,
                "prototype-inline.html",
                prototype_html,
                prototype_meta,
            )
            try:
                doc_store.save_accelerator_asset(
                    session.session_id,
                    "prototype-inline.html",
                    prototype_html.encode("utf-8"),
                    prototype_meta,
                )
            except Exception as exc:  # pragma: no cover - defensive
                _emit_storage_error(session.session_id, "prototype-inline.html", exc)
            _queue_linked_artifact(
                session.session_id,
                {
                    "type": "prototype",
                    "title": "HTML prototype snippet",
                    "preview": prototype_html[:240],
                    "source": "system",
                    "version": version,
                    "fr_refs": sorted(aggregate_fr_refs) or [primary_ref],
                    "nfr_refs": sorted(aggregate_nfr_refs),
                },
                message_id=trigger_message_id,
            )
            version += 1

        guidance = _compose_ready_to_run_instructions()
        guidance_meta = {
            "version": version,
            "type": "summary",
            "language": "markdown",
            "summary": "Instructions for running the generated scaffold.",
            "gate_stage": _compute_gate_stage("summary"),
        }
        doc_store.save_accelerator_preview(
            session.session_id,
            "READY-TO-RUN.md",
            guidance,
            guidance_meta,
        )
        try:
            doc_store.save_accelerator_asset(
                session.session_id,
                "READY-TO-RUN.md",
                guidance.encode("utf-8"),
                guidance_meta,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            _emit_storage_error(session.session_id, "READY-TO-RUN.md", exc)
        _queue_linked_artifact(
            session.session_id,
            {
                "type": "summary",
                "title": "Ready-to-run instructions",
                "preview": guidance[:240],
                "source": "system",
                "version": version,
            },
            message_id=trigger_message_id,
        )
        version += 1

    record_metric(
        name="accelerator_code_generation_ms",
        value=duration_ms,
        properties={
            "intent_id": intent.intent_id,
            "session_id": session.session_id,
        },
    )
    record_metric(
        name="accelerator_response_ms",
        value=duration_ms,
        properties={
            "intent_id": intent.intent_id,
            "session_id": session.session_id,
            "mode": "code",
        },
    )
    record_event(
        TelemetryEvent(
            name="accelerator_code_artifacts_generated",
            actor=session.created_by,
            properties={
                "session_id": session.session_id,
                "intent_id": intent.intent_id,
                "paths": [section["path"] for section in sections],
            },
        )
    )

    metadata = dict(session.metadata or {})
    metadata.setdefault("artifacts", store.list_artifacts(session.session_id))
    metadata["status"] = "ready"
    metadata["last_generated_at"] = time.time()
    _update_session_metadata(session.session_id, metadata)
    _enqueue_snapshot_refresh(session.session_id)


def edit_accelerator_artifact(
    session_id: str,
    filename: str,
    *,
    content: str,
    summary: Optional[str] = None,
    section: Optional[str] = None,
    change_description: Optional[str] = None,
    message_id: Optional[str] = None,
    edited_by: Optional[str] = None,
) -> Dict[str, Any]:
    store = get_accelerator_store()
    session = store.get_session(session_id)
    if not session:
        raise ValueError("Session not found")

    doc_store = get_doc_store()
    previous_preview = doc_store.get_accelerator_preview(session_id, filename) or {}
    previous_meta = dict(previous_preview.get("meta") or {})
    previous_content = str(previous_preview.get("content") or "")

    edited_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    meta: Dict[str, Any] = {
        **previous_meta,
        "manual_edit": True,
        "edited_at": edited_at,
    }
    if edited_by:
        meta["edited_by"] = edited_by
    if summary is not None:
        meta["summary"] = summary
    if section is not None:
        meta["section"] = section
    if change_description:
        meta["change_description"] = change_description
    if message_id:
        meta["message_id"] = message_id

    version = doc_store.save_accelerator_preview(session_id, filename, content, meta)
    meta["version"] = version
    try:
        doc_store.save_accelerator_asset(session_id, filename, content.encode("utf-8"), meta)
    except Exception as exc:  # pragma: no cover - defensive logging
        _emit_storage_error(session_id, filename, exc)

    store.add_artifact(
        session_id,
        filename=filename,
        project_id=session.project_id,
        meta=meta,
    )

    diff_summary = _summarize_diff(previous_content, content)
    _queue_linked_artifact(
        session_id,
        {
            "type": "document_update",
            "title": meta.get("title") or filename,
            "preview": summary or meta.get("summary") or "Manual edit applied.",
            "source": "edit",
            "stage": "edit",
            "filename": filename,
            "version": version,
            "meta": meta,
            "diff": diff_summary,
            "content": content,
        },
        message_id=message_id,
    )

    metadata = dict(session.metadata or {})
    metadata.setdefault("artifacts", store.list_artifacts(session_id))
    metadata["last_activity"] = edited_at
    metadata["status"] = "ready"
    _update_session_metadata(session_id, metadata)
    _enqueue_snapshot_refresh(session_id)

    return {
        "filename": filename,
        "version": version,
        "content": content,
        "meta": meta,
    }


def _schedule_code_generation(
    session_id: str,
    intent: ChatIntent,
    latest_input: str,
    *,
    trigger_message_id: Optional[str] = None,
) -> None:
    store = get_accelerator_store()

    def worker() -> None:
        _queue_linked_artifact(
            session_id,
            {
                "type": "status",
                "title": "Generating code scaffold",
                "preview": "Collecting context and preparing scaffolds…",
                "stage": "code_generation",
                "progress": 0.1,
                "source": "system",
            },
            message_id=trigger_message_id,
        )
        time.sleep(0.5)
        try:
            session = store.get_session(session_id)
            if not session:
                return
            start = time.perf_counter()
            _queue_linked_artifact(
                session_id,
                {
                    "type": "status",
                    "title": "Drafting code components",
                    "preview": "Assembling feature modules and tests…",
                    "stage": "code_generation",
                    "progress": 0.4,
                    "source": "system",
                },
                message_id=trigger_message_id,
            )
            payload = _generate_code_payload(session, intent, latest_input)
            duration_ms = (time.perf_counter() - start) * 1000.0
            _publish_code_artifacts(
                session,
                intent,
                payload,
                duration_ms,
                latest_input,
                trigger_message_id=trigger_message_id,
            )
            _queue_linked_artifact(
                session_id,
                {
                    "type": "status",
                    "title": "Code scaffold ready",
                    "preview": "Scaffolds generated and linked to the latest request.",
                    "stage": "code_generation",
                    "progress": 1.0,
                    "source": "system",
                },
                message_id=trigger_message_id,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("code_generation_failed session=%s err=%s", session_id, exc)
            _queue_linked_artifact(
                session_id,
                {
                    "type": "status",
                    "title": "Code scaffolding delayed",
                    "preview": "We hit an error while generating code snippets. Please retry or adjust inputs.",
                    "source": "system",
                    "stage": "code_generation",
                    "progress": 0.0,
                },
                message_id=trigger_message_id,
            )
            refreshed = store.get_session(session_id)
            if refreshed:
                metadata = dict(refreshed.metadata or {})
                metadata["status"] = "ready"
                _update_session_metadata(session_id, metadata)

    Thread(target=worker, daemon=True).start()

def _compose_document_system_prompt(intent: Optional[ChatIntent], session: AcceleratorSession) -> str:
    context_lines: List[str] = []
    if intent:
        context_lines.append(f"Initiative: {intent.title}")
        if intent.requirement_area:
            context_lines.append(f"Focus area: {intent.requirement_area}")
        if intent.deliverables:
            deliverables = ", ".join(intent.deliverables)
            context_lines.append(f"Target deliverables: {deliverables}")
    metadata = session.metadata or {}
    timelines = metadata.get("milestones") or metadata.get("timeline")
    if isinstance(timelines, str) and timelines.strip():
        context_lines.append(f"Milestones: {timelines.strip()}")
    if session.persona:
        context_lines.append(f"Primary reader persona: {session.persona}")

    prompt_sections = [ACCELERATOR_DOCUMENT_PROMPT.strip()]
    if context_lines:
        contextual_block = "Context for this draft:\n" + "\n".join(
            f"- {line}" for line in context_lines
        )
        prompt_sections.append(contextual_block)
    return "\n\n".join(prompt_sections)


# --- opnxt-stream ---
def _enqueue_immediate_start(session_id: str, *, force: bool = False) -> None:
    store = get_accelerator_store()
    if not force:
        try:
            meta = store.get_session(session_id).metadata  # type: ignore[attr-defined]
        except Exception:
            meta = None
        if not meta:
            return
        already_sent = bool(meta.get("status") in {"thinking", "drafting"})
        if meta.get("message_count", 0) == 0 or already_sent:
            return

    progress_value = 0.05
    artifact = {
        "type": "status",
        "title": "Generation started",
        "preview": "Preparing your draft…",
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "system",
        "stage": "analysis",
        "progress": progress_value,
        "meta": {
            "stage": "analysis",
            "progress": progress_value,
        },
    }
    _queue_artifact(session_id, artifact)


# --- accelerator-seed ---
def _seed_baseline_artifact(
    session: AcceleratorSession,
    intent: ChatIntent,
    intro_text: str,
) -> AcceleratorSession:
    store = get_accelerator_store()
    doc_store = get_doc_store()
    artifacts, _ = store.artifact_snapshot(session.session_id)
    if artifacts:
        return session

    recent_messages = store.list_messages(session.session_id)
    summary_context = _render_summary_context(session, intent, intro_text, recent_messages)
    system_prompt = _compose_document_system_prompt(intent, session)
    history: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for msg in recent_messages[-4:]:
        history.append({"role": msg.role, "content": msg.content})
    draft_reply = reply_with_chat_ai(
        project_name=intent.title,
        user_message=textwrap.dedent(
            f"""
            Produce the first executive-ready working draft for this accelerator session.
            Use the summary context, intro message, and recent chat history to align language, risks, and next steps.

            Summary context:
            {summary_context}
            """
        ).strip(),
        history=history,
        attachments=None,
        persona=session.persona,
        intent_override="documentation",
        purpose_override="accelerator_executive",
    )
    draft = _coerce_text(draft_reply)
    if not draft.strip():
        draft = _compose_baseline_draft(intent, summary_context)

    summary = draft[:240]
    filename = f"{intent.title.lower().replace(' ', '-')}-draft-v1.md"
    store.add_artifact(
        session.session_id,
        filename=filename,
        project_id=session.project_id,
        meta={
            "version": 1,
            "summary": summary,
            "provider": "seed",
            "model": None,
        },
    )
    doc_store.save_accelerator_preview(session.session_id, filename, draft)
    try:
        doc_store.save_accelerator_asset(session.session_id, filename, draft.encode("utf-8"))
    except Exception as exc:  # pragma: no cover - defensive logging
        _emit_storage_error(session.session_id, filename, exc)
    _queue_artifact(
        session.session_id,
        {
            "type": "summary",
            "title": "Baseline Executive Draft",
            "preview": summary,
            "source": "seed",
        },
    )
    _enqueue_snapshot_refresh(session.session_id)
    refreshed = store.get_session(session.session_id)
    return refreshed or session


# --- opnxt-stream ---
def _emit_stream_chunks(
    session_id: str,
    text: str,
    *,
    stage: str = "draft",
    progress: Optional[float] = None,
) -> None:
    if not text:
        return
    chunk_size = max(40, min(160, len(text) // 12 or 40))
    for idx in range(0, len(text), chunk_size):
        segment = text[idx : idx + chunk_size]
        ts_value = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        artifact = {
            "type": "draft_update",
            "title": "Draft (streaming)",
            "preview": segment,
            "source": "stream",
            "ts": ts_value,
        }
        if stage:
            artifact["stage"] = stage
        if progress is not None:
            artifact["progress"] = progress
        artifact.setdefault("meta", {})
        artifact["meta"].update(
            {
                "stage": stage,
                "progress": progress,
                "chunk_index": idx // chunk_size,
                "ts": ts_value,
            }
        )
        _queue_artifact(session_id, artifact)
        time.sleep(0.05)


# --- opnxt-stream ---
def _queue_stream_commit(
    session_id: str,
    preview: str,
    *,
    title: str = "Assistant draft ready",
    stage: str = "ready",
    progress: float = 0.98,
) -> None:
    ts_value = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {
        "type": "commit",
        "title": title,
        "preview": preview,
        "source": "stream",
        "stage": stage,
        "progress": progress,
        "ts": ts_value,
        "meta": {
            "stage": stage,
            "progress": progress,
            "ts": ts_value,
        },
    }
    _queue_artifact(session_id, payload)


# --- opnxt-stream ---
def _simulate_stream_from_text(session_id: str, text: str) -> None:
    """Emit draft/commit events when provider response is non-streaming."""

    trimmed = (text or "").strip()
    if not trimmed:
        return

    _emit_stream_chunks(session_id, trimmed, stage="draft", progress=0.7)
    commit_preview = trimmed[-320:].strip() if len(trimmed) > 320 else trimmed
    _queue_stream_commit(session_id, commit_preview or "Assistant draft ready.")


# --- opnxt-stream ---
async def _stream_tokens_to_artifacts(session_id: str, token_iter: Iterable[Dict[str, Any]]) -> str:  # --- opnxt-stream ---
    buffer: List[str] = []
    last_flush = time.time()
    flush_interval = 0.5
    flush_count = 0
    progress_floor = 0.35
    progress_cap = 0.85
    async for token in iter_as_async(token_iter):
        piece = token.get("token")
        if not piece:
            continue
        buffer.append(piece)
        if time.time() - last_flush >= flush_interval:
            preview = "".join(buffer)[-600:]
            ts_value = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            artifact = {
                "type": "draft_update",
                "title": "Draft (streaming)",
                "preview": preview,
                "source": "stream",
                "ts": ts_value,
            }
            flush_count += 1
            progress_value = min(progress_cap, progress_floor + flush_count * 0.06)
            artifact["stage"] = "draft"
            artifact["progress"] = progress_value
            artifact["meta"] = {
                "stage": "draft",
                "progress": progress_value,
                "flush_count": flush_count,
                "ts": ts_value,
            }
            _queue_artifact(session_id, artifact)
            last_flush = time.time()
    full_text = "".join(buffer)
    if full_text:
        final_progress = min(0.92, progress_floor + (flush_count + 1) * 0.06)
        _emit_stream_chunks(session_id, full_text[-600:], stage="draft", progress=final_progress)
        commit_preview = full_text[-320:].strip() or "Assistant draft ready for review."
        _queue_stream_commit(session_id, commit_preview)
    return full_text  # --- opnxt-stream ---


def _run_stream_task(coro: "asyncio.Future[str]") -> str:
    """Execute an async streaming coroutine even when the main event loop is running."""

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        result: Dict[str, str] = {}
        error: Dict[str, BaseException] = {}
        finished = Event()

        def _runner() -> None:
            local_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(local_loop)
            try:
                result["text"] = local_loop.run_until_complete(coro)
            except BaseException as exc:  # pragma: no cover - defensive
                error["exc"] = exc
            finally:
                local_loop.close()
                finished.set()

        Thread(target=_runner, daemon=True).start()
        finished.wait()
        if "exc" in error:
            raise error["exc"]
        return result.get("text", "")

    return asyncio.run(coro)


def _get_first_name(user: Optional[User]) -> str:
    if not user or not user.name:
        return "there"
    return user.name.split()[0]


def _build_intro_message(intent: ChatIntent, user: Optional[User], persona: Optional[str]) -> str:
    first_name = _get_first_name(user)
    focus = intent.requirement_area or intent.group or "this initiative"
    deliverables = intent.deliverables or [
        "Project Charter",
        "Requirements Outline",
        "Solution Notes",
        "Test Readiness Checklist",
    ]
    persona_line = (
        f"We'll keep the {persona.title()} lens front-and-center." if persona else "We'll balance product, engineering, and delivery angles."
    )

    lines: List[str] = []
    lines.append("### Executive Summary")
    lines.append(
        f"- Hi {first_name}, the Expert Circle is ready to spin up {', '.join(deliverables)} for **{intent.title}**."
    )
    lines.append(f"- We'll focus on {focus.lower()} and surface decisions that unblock fast drafting.")
    if intent.opnxt_benefit:
        lines.append(f"- Business driver to amplify: {intent.opnxt_benefit}.")
    lines.append(f"- {persona_line}")

    lines.append("")
    lines.append("### Readiness & Gaps")
    lines.append("- Need crisp outcomes or KPIs that define success.")
    lines.append("- Need stakeholder map plus owners for cross-team handoffs.")
    lines.append("- Need guardrails: timelines, tech constraints, compliance notes.")

    lines.append("")
    lines.append("### Recommended Actions")
    lines.append("- Drop in any pre-existing notes so we can reuse them verbatim where possible.")
    lines.append("- Call out non-functional expectations (latency, reliability, security) up front.")
    lines.append("- Flag the next SDLC gate so we can show draft readiness against it.")

    lines.append("")
    lines.append("### Questions for You")
    lines.append("1. What outcomes or metrics prove this initiative is hitting the mark?")
    lines.append("2. Who must review or sign off before we promote the deliverables?")
    lines.append("3. Are there constraints (tools, integrations, budget) we must respect from day one?")

    return "\n".join(lines)


def _collect_workspace_snapshot() -> Dict[str, Any]:
    repo = get_repo()
    doc_store = get_doc_store()
    projects: List[Dict[str, Any]] = []
    try:
        project_list = repo.list()
    except Exception:  # pragma: no cover - defensive
        project_list = []

    for project in project_list[:5]:
        try:
            docs = doc_store.list_documents(project.project_id) or {}
        except Exception:  # pragma: no cover - defensive
            docs = {}
        recent_docs: List[Dict[str, Any]] = []
        for fname, versions in list(docs.items())[:5]:
            if not versions:
                continue
            latest = versions[-1]
            recent_docs.append(
                {
                    "filename": fname,
                    "version": latest.get("version"),
                    "created_at": latest.get("created_at"),
                }
            )
        projects.append(
            {
                "project_id": project.project_id,
                "name": project.name,
                "documents": recent_docs,
            }
        )
    return {"projects": projects}


def _render_summary_context(
    session: AcceleratorSession,
    intent: ChatIntent,
    intro_text: str,
    recent_messages: List[AcceleratorMessage],
) -> str:
    requirement_focus = intent.requirement_area or intent.group or "General initiative"
    deliverables = ", ".join(intent.deliverables) if intent.deliverables else "Not specified"
    persona = session.persona or "unspecified"
    metadata = session.metadata or {}
    workspace_snapshot = metadata.get("workspace_snapshot") or {}
    projects_snapshot = workspace_snapshot.get("projects") or []

    last_user_message = next(
        (msg for msg in reversed(recent_messages) if msg.role == "user" and msg.content.strip()),
        None,
    )

    lines: List[str] = [
        f"Intent: {intent.title} ({intent.intent_id})",
        f"Requirement focus: {requirement_focus}",
        f"Detected persona: {persona}",
        f"Target deliverables: {deliverables}",
        f"Messages observed: {len(recent_messages)}",
    ]

    if intro_text.strip():
        lines.append(f"Launch prompt: {intro_text.strip()[:280]}")

    if last_user_message:
        lines.append(f"Latest user input: {last_user_message.content.strip()[:320]}")

    if projects_snapshot:
        project_summaries = []
        for project in projects_snapshot[:3]:
            name = project.get("name") or project.get("project_id") or "Unnamed project"
            doc_count = len(project.get("documents") or [])
            project_summaries.append(f"- {name}: {doc_count} linked docs")
        if project_summaries:
            lines.append("Workspace snapshot:")
            lines.extend(project_summaries)

    lines.append("Session metadata: " + json.dumps({k: v for k, v in metadata.items() if k not in {"workspace_snapshot"}}, ensure_ascii=False)[:400])
    return "\n".join(lines)


def _compose_baseline_draft(intent: ChatIntent, summary_context: str) -> str:
    focus = intent.requirement_area or intent.group or "This initiative"
    summary_block = summary_context.strip() or "No additional context provided yet."
    indented_summary = textwrap.indent(summary_block, "    ")
    deliverables = intent.deliverables or []
    deliverable_lines = "\n".join(f"- {item}" for item in deliverables) if deliverables else "- Establish deliverables with the stakeholder team."

    return textwrap.dedent(
        f"""
        # {intent.title} – Executive Working Draft

        We're aligning the Expert Circle around the outcomes for {focus.lower()} so documentation can move immediately toward approval.

        **Highlights Dashboard**
        | Focus Area | Current Confidence | Exec Callout |
        | --- | --- | --- |
        | Value Hypothesis | Medium | Validate success metrics with sponsors and agree on measurable outcomes. |
        | Delivery Runway | Medium | Stand up delivery cadence, dependencies, and funding checkpoints. |
        | Risk Posture | Medium | Capture integration, compliance, and scalability risks explicitly. |

        ## Executive Summary
        - Provide a concise articulation of the problem, target users, and desired business outcomes.
        - Confirm the success measures and non-functional guardrails before advancing to design.
        - Use the latest discovery context to align stakeholders on scope and readiness.

        ## Latest Discovery Context
        {indented_summary}

        ## Planned Deliverables
        {deliverable_lines}

        ## Immediate Next Actions
        1. Capture explicit success metrics and guardrails that must appear in the SDLC plan.
        2. Identify system integrations and data sources that influence architecture and testing.
        3. Outline stakeholder ownership (sponsor, delivery lead, compliance, architecture).

        ## Risks & Mitigations
        | Risk | Impact | Mitigation |
        | --- | --- | --- |
        | Ambiguous requirements | High | Facilitate requirement workshop to confirm scope and acceptance criteria. |
        | Compliance or audit gaps | Medium | Loop in compliance partner to enumerate required controls. |
        | Integration unknowns | Medium | Schedule deep dive sessions with integration owners and capture SLAs. |

        ## Advisor Perspective
        We're ready to translate this into polished deliverables once leadership confirms scope, risks, and guardrails. Highlight any mandatory constraints so we can finalize the SRS, test plan, and architecture package without rework.
        """
    ).strip()


def _default_api_templates(intent: ChatIntent) -> List[Dict[str, Any]]:
    examples = [
        {
            "label": "Order validation (SAP ERP)",
            "description": "Validates proof-of-purchase details and returns eligibility flags.",
            "example": textwrap.dedent(
                """
{
  "method": "POST",
  "url": "https://sap.example.com/api/v1/claims/validate",
  "headers": {
    "Authorization": "Bearer <client-credential-token>",
    "Content-Type": "application/json"
  },
  "body": {
    "receiptNumber": "A1234-5678",
    "sku": "TV-55-UHD",
    "purchaseDate": "2025-02-10",
    "channel": "in-store"
  }
}
                """
            ).strip(),
        },
        {
            "label": "Shipping label creation (FedEx API)",
            "description": "Creates a prepaid label and returns tracking details.",
            "example": textwrap.dedent(
                """
{
  "method": "POST",
  "url": "https://apis.fedex.com/ship/v21/shipments",
  "headers": {
    "X-FedEx-Api-Key": "<key>",
    "X-FedEx-Api-Secret": "<secret>",
    "Content-Type": "application/json"
  },
  "body": {
    "serviceType": "FEDEX_GROUND",
    "shipper": {"postalCode": "43004", "countryCode": "US"},
    "recipient": {"postalCode": "78701", "countryCode": "US"},
    "packages": [{"weight": {"units": "LB", "value": 8}}]
  }
}
                """
            ).strip(),
        },
        {
            "label": "Refund settlement (Stripe)",
            "description": "Issues a partial refund tied to the original payment.",
            "example": textwrap.dedent(
                """
{
  "method": "POST",
  "url": "https://api.stripe.com/v1/refunds",
  "headers": {
    "Authorization": "Bearer sk_live_xxx",
    "Content-Type": "application/x-www-form-urlencoded"
  },
  "form": {
    "payment_intent": "pi_3P123456",
    "amount": 12999,
    "metadata[claim_id]": "RET-2048"
  }
}
                """
            ).strip(),
        },
    ]

    if intent and intent.deliverables:
        deliverable_preview = "\n".join(f"- {d}" for d in intent.deliverables)
        examples.append(
            {
                "label": "Deliverable checklist",
                "description": "Catalog deliverables referenced in this accelerator.",
                "example": deliverable_preview,
            }
        )

    return examples


def _suggested_prompts(intent: ChatIntent, snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
    prompts: List[Dict[str, str]] = []
    focus = intent.requirement_area or intent.title
    prompts.append(
        {
            "id": "flows",
            "label": "Outline customer & associate flows",
            "body": textwrap.dedent(
                f"""
Here are the journeys to cover for {focus}:
• Customer submits request, uploads proof, selects pickup/drop-off, tracks approval
• Associate triages eligibility, issues instant credit, prints shipping label
• Finance & merchandising teams review dashboards for trends, fraud, SLA compliance
Flag any corrections or extra steps we should capture.
                """
            ).strip(),
        }
    )
    prompts.append(
        {
            "id": "nfr",
            "label": "Confirm non-functional guardrails",
            "body": textwrap.dedent(
                """
Non-functional targets we plan to bake into the docs:
• Availability 99.7% with Azure Front Door active-active failover
• Performance <2s median API latency, <3s p95 page load @ 400 sessions
• Compliance: PCI-DSS for refunds, SOC2 logging, encrypted PII at rest, Azure AD SSO with MFA
• Observability: OpenTelemetry tracing, Azure Monitor dashboards, synthetic probes every 5 minutes
Let us know if these align or require adjustments.
                """
            ).strip(),
        }
    )

    if snapshot.get("projects"):
        prompts.append(
            {
                "id": "reuse",
                "label": "Reuse existing artifacts",
                "body": textwrap.dedent(
                    """
We spotted existing workspace documents. Highlight anything we should repurpose so the new drafts stay aligned with prior deliverables.
                    """
                ).strip(),
            }
        )
    return prompts


def _schedule_background_generation(
    session_id: str,
    intent: ChatIntent,
    latest_input: str,
    *,
    trigger_message_id: Optional[str] = None,
) -> None:
    store = get_accelerator_store()
    doc_store = get_doc_store()

    def worker():
        _queue_linked_artifact(
            session_id,
            {
                "type": "status",
                "title": "Drafting accelerator deliverable",
                "preview": "Generating the next document revision…",
                "source": "system",
                "stage": "analysis",
                "progress": 0.1,
            },
            message_id=trigger_message_id,
        )
        time.sleep(0.5)
        try:
            start = time.perf_counter()
            session = store.get_session(session_id)
            if not session:
                return
            _queue_linked_artifact(
                session_id,
                {
                    "type": "status",
                    "title": "Collecting workspace context",
                    "preview": "Summarizing recent chat and artifacts…",
                    "source": "system",
                    "stage": "analysis",
                    "progress": 0.3,
                },
                message_id=trigger_message_id,
            )
            artifacts, revision = store.artifact_snapshot(session_id)
            version = revision + 1
            history = [
                {"role": msg.role, "content": msg.content}
                for msg in store.list_messages(session_id)[-12:]
            ]
            system_prompt = _compose_document_system_prompt(intent, session)
            doc_history = [{"role": "system", "content": system_prompt}] + history
            prompt = textwrap.dedent(
                f"""
Generate the next revision of the accelerator deliverable for "{intent.title}".
Summarize the current plan, highlight risks, and translate actions into an executive-ready narrative.
Latest user input:
{latest_input}
                """
            ).strip()
            _queue_linked_artifact(
                session_id,
                {
                    "type": "status",
                    "title": "Drafting executive summary",
                    "preview": "Rendering updated narrative…",
                    "source": "system",
                    "stage": "analysis",
                    "progress": 0.6,
                },
                message_id=trigger_message_id,
            )
            draft = reply_with_chat_ai(
                project_name=intent.title,
                user_message=prompt,
                history=doc_history,
                attachments=None,
                persona=session.persona,
                intent_override="documentation",
                purpose_override="accelerator_executive",
            )
            # --- mcp-fix ---
            if isinstance(draft, dict):
                draft_text = _coerce_text(draft)  # --- opnxt-stream ---
                provider = draft.get("provider")
                model = draft.get("model")
            else:
                draft_text = _coerce_text(draft)  # --- opnxt-stream ---
                provider = None
                model = None
            if not draft_text:
                logger.warning(
                    "accelerator_generation_empty",
                    extra={"session": session_id, "intent": intent.intent_id},
                )
                return
            filename = f"{intent.title.lower().replace(' ', '-')}-draft-v{version}.md"
            store.add_artifact(
                session_id,
                filename=filename,
                project_id=session.project_id,
                meta={
                    "version": version,
                    # --- mcp-fix ---
                    "summary": draft_text[:240],
                    "provider": provider,
                    "model": model,
                },
            )
            # --- mcp-fix ---
            doc_store.save_accelerator_preview(session_id, filename, draft_text)
            try:
                doc_store.save_accelerator_asset(session_id, filename, draft_text.encode("utf-8"))
            except Exception as exc:  # pragma: no cover - defensive
                _emit_storage_error(session_id, filename, exc)
            summary_artifact = {
                "type": "summary",
                "title": "Draft Summary",
                "preview": draft_text[:240] or "Generation completed with fallback; expand to view.",
                "length": len(draft_text),
                "source": "llm" if provider else "fallback",
            }  # --- opnxt-stream ---
            _queue_artifact(session_id, summary_artifact)  # --- opnxt-stream ---
            ready_artifact = {
                "type": "status",
                "title": f"Draft v{version} ready",
                "preview": draft_text[:160] or "New draft completed.",
                "source": "llm" if provider else "fallback",
                "version": version,
            }
            _queue_linked_artifact(
                session_id,
                ready_artifact,
                message_id=trigger_message_id,
            )

            # Attempt full SDLC document generation using master prompt
            generation_context = textwrap.dedent(
                f"""
                SESSION PERSONA: {session.persona or 'unspecified'}
                LATEST INPUT:
                {latest_input or 'No additional context supplied.'}

                MOST RECENT EXECUTIVE DRAFT:
                {draft_text}
                """
            ).strip()
            existing_previews = doc_store.list_accelerator_previews(session_id)
            attachment_map = {
                item.get("filename", f"artifact-{idx}.md"): str(item.get("content") or "")
                for idx, item in enumerate(existing_previews)
                if item.get("content")
            }

            _queue_artifact(
                session_id,
                {
                    "type": "status",
                    "title": "Generating SDLC documents",
                    "preview": "Creating charter, SRS, SDD, and Test Plan drafts…",
                    "source": "system",
                    "stage": "analysis",
                    "progress": 0.7,
                },
            )

            doc_map = {}
            try:
                doc_map = generate_with_master_prompt(
                    project_name=intent.title,
                    input_text=generation_context,
                    doc_types=None,
                    attachments=attachment_map,
                )
            except Exception as gen_exc:
                logger.exception(
                    "sdlc_master_prompt_failed",
                    extra={"session": session_id, "intent": intent.intent_id, "err": str(gen_exc)},
                )

            if doc_map:
                def _doc_kind(name: str) -> str:
                    lowered = name.lower()
                    if "charter" in lowered:
                        return "Project Charter"
                    if "srs" in lowered:
                        return "SRS"
                    if "sdd" in lowered:
                        return "SDD"
                    if "test" in lowered:
                        return "Test Plan"
                    return "Document"

                for fname, content in doc_map.items():
                    doc_version = version + 1
                    meta = {
                        "version": doc_version,
                        "type": "document",
                        "document_name": fname,
                        "document_kind": _doc_kind(fname),
                        "summary": (content or "")[:240],
                        "source": "llm",
                    }
                    store.add_artifact(
                        session_id,
                        filename=fname,
                        project_id=session.project_id,
                        meta=meta,
                    )
                    doc_store.save_accelerator_preview(session_id, fname, content, meta)
                    try:
                        doc_store.save_accelerator_asset(session_id, fname, content.encode("utf-8"), meta)
                    except Exception as exc:  # pragma: no cover - defensive
                        _emit_storage_error(session_id, fname, exc)
                    _queue_artifact(
                        session_id,
                        {
                            "type": "document",
                            "title": meta["document_kind"],
                            "preview": meta["summary"] or "Generated SDLC draft ready for review.",
                            "source": "llm",
                            "filename": fname,
                            "version": doc_version,
                            "stage": "analysis",
                            "progress": 0.85,
                            "meta": meta,
                            "message_id": trigger_message_id,
                        },
                    )
                    version = doc_version

                _queue_artifact(
                    session_id,
                    {
                        "type": "status",
                        "title": "SDLC package ready",
                        "preview": "Project Charter, SRS, SDD, and Test Plan drafts generated.",
                        "source": "system",
                        "stage": "analysis",
                        "progress": 1.0,
                        "message_id": trigger_message_id,
                    },
                )
            else:
                _queue_linked_artifact(
                    session_id,
                    {
                        "type": "status",
                        "title": "SDLC document generation skipped",
                        "preview": "Master prompt did not return documents; keeping executive draft only.",
                        "source": "system",
                        "stage": "analysis",
                        "progress": 0.8,
                    },
                    message_id=trigger_message_id,
                )

            metadata = session.metadata or {}
            metadata.setdefault("artifacts", store.list_artifacts(session_id))
            metadata["last_generated_at"] = time.time()
            _update_session_metadata(session_id, metadata)
            _enqueue_snapshot_refresh(session_id)

            duration_ms = (time.perf_counter() - start) * 1000.0
            record_metric(
                name="accelerator_artifact_generation_ms",
                value=duration_ms,
                properties={
                    "intent_id": intent.intent_id,
                    "session_id": session_id,
                },
            )
            record_metric(
                name="accelerator_response_ms",
                value=duration_ms,
                properties={
                    "intent_id": intent.intent_id,
                    "session_id": session_id,
                    "mode": "documentation",
                },
            )
        except Exception as exc:  # pragma: no cover - background guard
            # --- mcp-fix ---
            logger.exception("background_generation_failed session=%s err=%s", session_id, exc)
            error_artifact = {
                "type": "status",
                "title": "Draft generation delayed",
                "preview": "We hit an error generating the latest draft. Please retry or adjust inputs.",
                "source": "system",
                "stage": "analysis",
                "progress": 0.0,
            }
            _queue_linked_artifact(session_id, error_artifact, message_id=trigger_message_id)

    Thread(target=worker, daemon=True).start()


async def stream_accelerator_artifacts(session_id: str, start_revision: int = 0) -> AsyncGenerator[Dict[str, Any], None]:
    store = get_accelerator_store()
    active_counter_name = "accelerator_artifact_stream_active"
    record_metric(
        name=active_counter_name,
        value=1,
        properties={
            "session_id": session_id,
        },
        metric_type="gauge_delta",
    )
    heartbeat_interval = max(0.5, _STREAM_HEARTBEAT_SECONDS)  # --- opnxt-stream ---
    poll_interval = max(0.1, _STREAM_POLL_SECONDS)  # --- opnxt-stream ---
    last_heartbeat = 0.0  # --- opnxt-stream ---
    revision = max(0, start_revision)  # --- opnxt-stream ---
    try:
        logger.info(
            "artifact_stream_client_connected",
            extra={"session_id": session_id, "start_revision": revision},
        )
        artifacts, current_revision = store.artifact_snapshot(session_id)
        if current_revision >= revision:  # --- opnxt-stream ---
            revision = current_revision  # --- opnxt-stream ---
            yield {
                "revision": revision,
                "artifacts": artifacts,
                "type": "snapshot",
            }
        while True:
            updates: List[Dict[str, Any]] = []  # --- opnxt-stream ---
            queued = await artifacts_queue.get_for_session(session_id)  # --- opnxt-stream ---
            while queued:
                updates.append(queued)
                queued = await artifacts_queue.get_for_session(session_id)
            if updates:
                yield {
                    "revision": revision,
                    "updates": updates,
                    "type": "updates",
                }
            artifacts, current_revision = store.artifact_snapshot(session_id)
            if current_revision > revision:
                revision = current_revision
                yield {
                    "revision": revision,
                    "artifacts": artifacts,
                    "type": "snapshot",
                }
            now = time.time()  # --- opnxt-stream ---
            if now - last_heartbeat >= heartbeat_interval:
                yield {
                    "heartbeat": True,
                    "revision": revision,
                    "type": "heartbeat",
                    "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }
                logger.debug(
                    "artifact_stream_heartbeat",
                    extra={"session_id": session_id, "revision": revision},
                )
                last_heartbeat = now
            await asyncio.sleep(poll_interval)
    finally:
        record_metric(
            name=active_counter_name,
            value=-1,
            properties={
                "session_id": session_id,
            },
            metric_type="gauge_delta",
        )
        logger.info("artifact_stream_client_closed", extra={"session_id": session_id})


def _infer_persona(text: str) -> Tuple[Optional[str], List[str]]:
    haystack = (text or "").lower()
    if not haystack:
        return None, []

    persona_keywords = {
        "architect": {"architecture", "system design", "architect", "solution", "platform", "integration", "systems"},
        "product": {"roadmap", "product", "portfolio", "market", "persona", "feature", "launch", "backlog", "customer", "self-service", "dashboard", "adoption", "experience"},
        "qa": {"testing", "qa", "quality assurance", "defect", "test plan", "test case", "acceptance", "validation"},
        "developer": {"code", "api", "implementation", "dev", "sdk", "repository", "deployment", "integration"},
        "executive": {"vision", "strategy", "executive", "roi", "budget", "c-suite", "board", "investment"},
        "operations": {"support", "operations", "runbook", "incident", "uptime", "monitoring", "service desk", "ticket"},
        "people": {"employee", "hr", "human resources", "people", "talent", "payroll", "benefits", "onboarding", "retention"},
    }

    scores = Counter()
    matched = defaultdict(set)
    for persona, keywords in persona_keywords.items():
        for word in keywords:
            if word in haystack:
                scores[persona] += 1
                matched[persona].add(word)

    if not scores:
        return None, []

    best_persona, best_score = scores.most_common(1)[0]
    strong_triggers = {
        "roadmap",
        "payroll",
        "benefits",
        "runbook",
        "architecture",
        "roi",
        "employee",
        "dashboard",
        "self-service",
        "experience",
    }
    if best_score >= 2:
        return best_persona, sorted(matched[best_persona])

    for persona, hits in matched.items():
        if strong_triggers & hits:
            return persona, sorted(hits)

    return best_persona, sorted(matched[best_persona])


def launch_accelerator_session(intent_id: str, user: User, persona: Optional[str] = None) -> Tuple[AcceleratorSession, List[AcceleratorMessage], ChatIntent]:
    intent = get_intent(intent_id)
    if not intent:
        raise ValueError("Unknown accelerator intent")

    store = get_accelerator_store()
    snapshot = _collect_workspace_snapshot()
    metadata = {
        "intent_id": intent.intent_id,
        "intent_title": intent.title,
        "requirement_area": intent.requirement_area,
        "core_functionality": intent.core_functionality,
        "opnxt_benefit": intent.opnxt_benefit,
        "workspace_snapshot": snapshot,
        "api_templates": _default_api_templates(intent),
        "suggested_prompts": _suggested_prompts(intent, snapshot),
        "last_activity": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "message_count": 0,
    }
    session = store.create_session(
        accelerator_id=intent.intent_id,
        created_by=user.email,
        persona=persona,
        metadata=metadata,
    )
    _enqueue_immediate_start(session.session_id)  # --- opnxt-stream ---

    prefill = (intent.prefill_prompt or "").strip()
    message_batch: List[AcceleratorMessage] = []

    if prefill:
        assistant_text = prefill.strip() or _build_intro_message(intent, user, persona)
        intro_message = store.add_message(
            session.session_id,
            role="assistant",
            content=assistant_text,
            metadata={
                "provider": "system",
                "prefill": True,
            },
        )
        message_batch.append(intro_message)
    else:
        intro = _build_intro_message(intent, user, persona)
        intro_message = store.add_message(session.session_id, role="assistant", content=intro)
        message_batch.append(intro_message)

    if message_batch:
        latest_timestamp = message_batch[-1].created_at
    else:
        latest_timestamp = session.created_at
    metadata_update = dict(session.metadata or {})
    metadata_update["last_activity"] = latest_timestamp
    metadata_update["message_count"] = len(store.list_messages(session.session_id))
    metadata_update["status"] = "ready"
    session = _update_session_metadata(session.session_id, metadata_update)

    record_event(
        TelemetryEvent(
            name="accelerator_session_started",
            actor=user.email,
            properties={
                "intent_id": intent.intent_id,
                "persona": persona,
            },
        )
    )

    hydrated = _hydrate_session_metadata(session)
    return hydrated, message_batch, intent


def load_accelerator_context(session_id: str) -> Tuple[AcceleratorSession, ChatIntent, List[AcceleratorMessage]]:
    store = get_accelerator_store()
    session = store.get_session(session_id)
    if not session:
        raise ValueError("Session not found")
    metadata = session.metadata or {}
    intent_id = metadata.get("intent_id") or session.accelerator_id
    intent = get_intent(intent_id)
    if not intent:
        raise ValueError("Accelerator intent metadata missing")
    messages = store.list_messages(session_id)
    hydrated = _hydrate_session_metadata(session)
    return hydrated, intent, messages


def _update_session_metadata(session_id: str, metadata: Dict[str, Any]) -> AcceleratorSession:
    """Persist session metadata while synchronizing attachment snapshot."""
    store = get_accelerator_store()
    metadata_copy = dict(metadata or {})
    attachments_snapshot = store.list_attachments(session_id)
    if attachments_snapshot:
        metadata_copy["attachments"] = attachments_snapshot
    else:
        metadata_copy.pop("attachments", None)
    return store.update_session_metadata(session_id, metadata_copy)


def _hydrate_session_metadata(session: AcceleratorSession) -> AcceleratorSession:
    """Ensure metadata surfaces persisted artifacts and accelerator model catalog."""

    store = get_accelerator_store()
    metadata = dict(session.metadata or {})

    try:
        artifacts, revision = store.artifact_snapshot(session.session_id)
    except Exception:
        artifacts = metadata.get("artifacts") or []
        revision = metadata.get("artifact_revision")

    if artifacts:
        metadata["artifacts"] = artifacts
        if revision is not None:
            metadata["artifact_revision"] = revision
    else:
        metadata.pop("artifacts", None)
        metadata.pop("artifact_revision", None)

    try:
        catalog = build_model_catalog()
    except Exception:
        catalog = []

    if catalog:
        metadata["accelerator_models"] = [option.model_dump() for option in catalog]
    else:
        metadata.pop("accelerator_models", None)

    session.metadata = metadata
    return session


def list_accelerator_previews(session_id: str) -> List[Dict[str, Any]]:
    store = get_accelerator_store()
    session = store.get_session(session_id)
    if not session:
        raise ValueError("Session not found")
    doc_store = get_doc_store()
    return doc_store.list_accelerator_previews(session_id)


def get_accelerator_asset_blob(session_id: str, filename: str) -> bytes:
    store = get_accelerator_store()
    blob = store.get_asset(session_id, filename)
    if blob is not None:
        return blob
    doc_store = get_doc_store()
    asset = doc_store.get_accelerator_asset(session_id, filename)
    if isinstance(asset, (bytes, bytearray)):
        return bytes(asset)
    preview = doc_store.get_accelerator_preview(session_id, filename)
    if preview and isinstance(preview.get("content"), str):
        content_str = preview["content"]
        try:
            return base64.b64decode(content_str.encode("utf-8"))
        except Exception:
            return content_str.encode("utf-8")
    raise FileNotFoundError(filename)


def get_accelerator_preview_html(session_id: str, filename: str) -> str:
    doc_store = get_doc_store()
    preview = doc_store.get_accelerator_preview(session_id, filename)
    if not preview:
        raise FileNotFoundError(filename)
    content = preview.get("content")
    if not isinstance(content, str):
        raise FileNotFoundError(filename)
    return content


def list_accelerator_attachments(session_id: str) -> List[Dict[str, Any]]:
    store = get_accelerator_store()
    session = store.get_session(session_id)
    if not session:
        raise ValueError("Session not found")
    return store.list_attachments(session_id)


def add_accelerator_attachments(
    session_id: str,
    files: List[Tuple[str, Optional[str], bytes]],
    user: User,
) -> List[Dict[str, Any]]:
    store = get_accelerator_store()
    session = store.get_session(session_id)
    if not session:
        raise ValueError("Session not found")

    current = store.attachment_count(session_id)
    remaining_slots = ATTACHMENT_MAX_FILES - current
    if remaining_slots <= 0:
        raise ValueError(f"Attachment limit reached ({ATTACHMENT_MAX_FILES})")

    processed = 0
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for name, content_type, data in files:
        if processed >= remaining_slots:
            break
        blob = bytes(data or b"")
        if not blob:
            continue
        try:
            extracted = parse_text_from_bytes(name, blob)
        except Exception:
            extracted = ""
        text = (extracted or "")[:ATTACHMENT_MAX_CHARS]
        preview = (text or "").strip()[:ATTACHMENT_PREVIEW_CHARS]
        if not preview:
            size_hint = len(blob)
            if size_hint:
                preview = f"[{size_hint} bytes uploaded — no readable text]"
        attachment_id = str(uuid.uuid4())
        clean_name = os.path.basename(name or "") or "upload"
        payload = {
            "id": attachment_id,
            "filename": clean_name,
            "content_type": content_type,
            "size": len(blob),
            "uploaded_at": now_iso,
            "preview": preview,
            "text": text,
            "source": "upload",
        }
        store.add_attachment(session_id, payload)
        processed += 1

    if processed == 0:
        raise ValueError("No attachments were processed")

    session = store.get_session(session_id)
    metadata_update = dict(session.metadata or {})
    metadata_update["last_activity"] = now_iso
    _update_session_metadata(session_id, metadata_update)

    record_event(
        TelemetryEvent(
            name="accelerator_attachment_uploaded",
            actor=user.email,
            properties={
                "session_id": session_id,
                "count": processed,
            },
        )
    )

    return store.list_attachments(session_id)


def remove_accelerator_attachment(session_id: str, attachment_id: str, user: User) -> List[Dict[str, Any]]:
    store = get_accelerator_store()
    session = store.get_session(session_id)
    if not session:
        raise ValueError("Session not found")

    store.remove_attachment(session_id, attachment_id)

    session = store.get_session(session_id)
    metadata_update = dict(session.metadata or {})
    metadata_update["last_activity"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _update_session_metadata(session_id, metadata_update)

    record_event(
        TelemetryEvent(
            name="accelerator_attachment_removed",
            actor=user.email,
            properties={
                "session_id": session_id,
                "attachment_id": attachment_id,
            },
        )
    )

    return store.list_attachments(session_id)


def post_accelerator_message(
    session_id: str,
    content: str,
    user: User,
    *,
    attachment_ids: Optional[List[str]] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> AcceleratorMessage:
    if not content or not content.strip():
        raise ValueError("Message content required")
    store = get_accelerator_store()
    session = store.get_session(session_id)
    if not session:
        raise ValueError("Session not found")

    session_metadata = dict(session.metadata or {})
    intent_id = session_metadata.get("intent_id") or session.accelerator_id
    intent = get_intent(intent_id)
    if not intent:
        raise ValueError("Accelerator intent metadata missing")
    metadata_update = dict(session.metadata or {})
    metadata_update.setdefault("intent_id", intent.intent_id)
    metadata_update.setdefault("intent_title", intent.title)
    metadata_update.setdefault("workspace_snapshot", _collect_workspace_snapshot())

    trimmed = content.strip()
    message_metadata: Dict[str, Any] = {}
    attachments_meta: List[Dict[str, Any]] = []
    if attachment_ids:
        unique_ids: List[str] = []
        for raw_id in attachment_ids:
            cleaned = (raw_id or "").strip()
            if cleaned and cleaned not in unique_ids:
                unique_ids.append(cleaned)
        for att_id in unique_ids[:ATTACHMENT_MAX_FILES]:
            record = store.get_attachment(session_id, att_id)
            if record:
                attachments_meta.append(record)
            else:
                logger.info(
                    "accelerator_attachment_missing",
                    extra={"session_id": session_id, "attachment_id": att_id},
                )
    if attachments_meta:
        message_metadata["attachments"] = attachments_meta
    store.add_message(session_id, role="user", content=trimmed, metadata=message_metadata or None)
    title = session_metadata.get("intent_title") or session_metadata.get("intent_id") or "Accelerator"

    metadata_update["last_activity"] = datetime.utcnow().isoformat().replace("+00:00", "Z")
    metadata_update["message_count"] = len(store.list_messages(session.session_id))
    metadata_update["status"] = "thinking"
    session = _update_session_metadata(session.session_id, metadata_update)
    session_metadata = dict(session.metadata or {})

    inferred, matched_keywords = _infer_persona(trimmed)
    logger.info(
        "accelerator_persona_inference session=%s existing=%s candidate=%s keywords=%s",
        session_id,
        session.persona,
        inferred,
        matched_keywords,
    )
    if inferred and inferred != session.persona:
        try:
            old_persona = session.persona
            session = store.update_persona(session_id, inferred)
            logger.info(
                "accelerator_persona_updated session=%s old=%s new=%s keywords=%s",
                session_id,
                old_persona,
                inferred,
                matched_keywords,
            )
        except KeyError:
            pass

    recent_messages = store.list_messages(session_id)
    attachment_texts = store.attachment_text_map(session_id)
    attachment_payload = attachment_texts if attachment_texts else None
    raw_history = recent_messages[-8:]
    history = [
        {"role": msg.role, "content": msg.content}
        for msg in raw_history
    ]
    system_prompt = _compose_assistant_system_prompt(intent, session)
    assistant_history = [{"role": "system", "content": system_prompt}] + history
    # surface immediate progress feedback for client streams
    try:
        _enqueue_immediate_start(session.session_id, force=True)
    except Exception:
        logger.exception("accelerator_enqueue_start_failed", extra={"session": session.session_id})

    assistant_reply = reply_with_chat_ai(
        project_name=title,
        user_message=trimmed,
        history=assistant_history,
        attachments=attachment_payload,
        persona=session.persona,
        provider=provider,
        model=model,
        intent_override="documentation",
        purpose_override="accelerator_executive",
        streaming_aware=True,
    )  # --- opnxt-stream ---
    stream_client = assistant_reply.get("stream") if isinstance(assistant_reply, dict) else None  # --- opnxt-stream ---
    assistant_provider = assistant_reply.get("provider") if isinstance(assistant_reply, dict) else None
    assistant_model = assistant_reply.get("model") if isinstance(assistant_reply, dict) else None
    assistant_text = ""
    stream_used = False

    if stream_client and hasattr(stream_client, "stream"):
        messages_for_stream = assistant_reply.get("messages") if isinstance(assistant_reply, dict) else None
        token_iter = stream_client.stream(messages_for_stream or history or [])
        try:
            assistant_text = _run_stream_task(_stream_tokens_to_artifacts(session_id, token_iter))
            stream_used = True
        except Exception as exc:
            logger.exception("accelerator_stream_failed session=%s err=%s", session_id, exc)
            assistant_text = ""
            stream_used = False
    else:
        assistant_text = (
            str(assistant_reply.get("text", "")) if isinstance(assistant_reply, dict) else str(assistant_reply)
        )

    if not stream_used and assistant_text.strip():
        _simulate_stream_from_text(session_id, assistant_text)

    if not assistant_text.strip():
        logger.warning(
            "accelerator_empty_assistant_text session=%s intent=%s", session_id, intent.intent_id if intent else "unknown"
        )
        assistant_text = (
            "We hit a delay preparing the next accelerator update. I logged the issue—please retry in a moment or provide more detail if the problem persists."
        )

    assistant_message = store.add_message(
        session_id,
        role="assistant",
        content=assistant_text,
        metadata={
            "provider": assistant_provider,
            "model": assistant_model,
        },
    )

    metadata_ready = dict(session.metadata or {})
    existing_attachments = metadata_ready.get("attachments")
    metadata_ready["last_activity"] = assistant_message.created_at
    metadata_ready["message_count"] = len(store.list_messages(session_id))
    metadata_ready["status"] = "ready"
    metadata_ready["last_summary"] = _render_summary_context(session, intent, system_prompt, recent_messages)
    if existing_attachments is not None:
        metadata_ready["attachments"] = existing_attachments
    session = _update_session_metadata(session_id, metadata_ready)

    artifacts_snapshot, _ = store.artifact_snapshot(session_id)
    if not artifacts_snapshot and intent:
        session = _seed_baseline_artifact(session, intent, assistant_text)

    doc_store = get_doc_store()
    project_id = session.project_id
    metadata_update = dict(session.metadata or {})
    if project_id:
        listing = doc_store.list_documents(project_id)
        latest_artifacts = []
        for fname, versions in listing.items():
            if not versions:
                continue
            latest = versions[-1]
            latest_artifacts.append(
                {
                    "filename": fname,
                    "version": latest.get("version"),
                    "created_at": latest.get("created_at"),
                }
            )
        metadata_update["artifacts"] = latest_artifacts

    metadata_update["last_activity"] = assistant_message.created_at
    metadata_update["message_count"] = len(store.list_messages(session_id))
    metadata_update["status"] = "ready"
    session = _update_session_metadata(session_id, metadata_update)

    metadata = session.metadata or {}

    intent = get_intent(metadata.get("intent_id") or session.accelerator_id)
    if intent:
        if _is_code_intent(intent):
            _schedule_code_generation(
                session_id,
                intent,
                trimmed,
                trigger_message_id=assistant_message.message_id,
            )
        else:
            _schedule_background_generation(
                session_id,
                intent,
                trimmed,
                trigger_message_id=assistant_message.message_id,
            )

    record_event(
        TelemetryEvent(
            name="accelerator_message_posted",
            actor=user.email,
            properties={
                "session_id": session_id,
                "intent_id": metadata.get("intent_id"),
                "persona": session.persona,
                "model_provider": assistant_provider,
                "model_name": assistant_model,
            },
        )
    )

    return assistant_message


def promote_accelerator_session(
    session_id: str,
    user: User,
    *,
    project_id: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Tuple[AcceleratorSession, Project]:
    store = get_accelerator_store()
    session = store.get_session(session_id)
    if not session:
        raise ValueError("Session not found")

    metadata = session.metadata or {}
    intent = get_intent(metadata.get("intent_id") or session.accelerator_id)

    repo = get_repo()
    project: Optional[Project] = None
    if project_id:
        project = repo.get(project_id)
        if not project:
            raise ValueError("Project not found")
    else:
        default_name = name or (intent.title if intent else "Accelerator Project")
        default_description = description or (intent.description if intent else "")
        payload = ProjectCreate(
            name=default_name[:120],
            description=default_description[:1000],
            type=metadata.get("requirement_area"),
            methodology=None,
            features=f"Accelerator:{metadata.get('intent_id', session.accelerator_id)}",
        )
        project = repo.create(payload)

    promoted_session = store.promote_session(session_id, project.project_id)
    if not promoted_session:
        raise ValueError("Unable to promote session")

    record_event(
        TelemetryEvent(
            name="accelerator_session_promoted",
            actor=user.email,
            properties={
                "session_id": session_id,
                "project_id": project.project_id,
                "intent_id": promoted_session.metadata.get("intent_id") if promoted_session.metadata else None,
            },
        )
    )

    return promoted_session, project
