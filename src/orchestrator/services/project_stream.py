from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

from ..infrastructure.doc_store import get_doc_store
from .artifact_stream import artifact_stream, queue_stream_event

_PROJECT_STREAM_PREFIX = "project::"
_STREAM_HEARTBEAT_SECONDS = float(os.getenv("OPNXT_STREAM_HEARTBEAT_SECONDS", "5"))
_STREAM_POLL_SECONDS = float(os.getenv("OPNXT_STREAM_POLL_SECONDS", "0.5"))

_project_revisions: Dict[str, int] = {}


def _stream_key(project_id: str) -> str:
    return f"{_PROJECT_STREAM_PREFIX}{project_id}"


def _next_revision(project_id: str) -> int:
    _project_revisions[project_id] = _project_revisions.get(project_id, 0) + 1
    return _project_revisions[project_id]


def current_revision(project_id: str) -> int:
    return _project_revisions.get(project_id, 0)


def _build_artifact_snapshot(project_id: str) -> List[Dict[str, Any]]:
    store = get_doc_store()
    listing = store.list_documents(project_id) or {}
    artifacts: List[Dict[str, Any]] = []
    for filename, versions in sorted(listing.items()):
        if not versions:
            continue
        latest = versions[-1]
        version = int(latest.get("version", 0)) if latest.get("version") is not None else None
        content: Optional[str] = None
        if version is not None:
            doc_version = store.get_document(project_id, filename, version=version)
            if doc_version:
                content = doc_version.content
        artifacts.append(
            {
                "filename": filename,
                "version": version,
                "created_at": latest.get("created_at"),
                "meta": latest.get("meta") or {},
                "content": content,
            }
        )
    return artifacts


def queue_project_status(project_id: str, message: str, stage: Optional[str] = None, progress: Optional[float] = None) -> None:
    revision = _next_revision(project_id)
    payload: Dict[str, Any] = {
        "type": "status",
        "message": message,
        "stage": stage,
        "progress": progress,
        "revision": revision,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "system",
    }
    queue_stream_event(_stream_key(project_id), payload)
    return revision


def queue_project_document_update(
    project_id: str,
    filename: str,
    content: str,
    *,
    meta: Optional[Dict[str, Any]] = None,
    source: str = "generation",
    section: Optional[str] = None,
    message_id: Optional[str] = None,
    summary: Optional[str] = None,
    change_description: Optional[str] = None,
    diff: Optional[str] = None,
    version: Optional[int] = None,
    stage: Optional[str] = None,
    progress: Optional[float] = None,
) -> None:
    revision = _next_revision(project_id)
    payload: Dict[str, Any] = {
        "type": "document_update",
        "filename": filename,
        "content": content,
        "meta": meta or {},
        "source": source,
        "section": section,
        "message_id": message_id,
        "revision": revision,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if summary is None and meta:
        summary = meta.get("summary") if isinstance(meta, dict) else None
    if change_description is None and meta:
        change_description = meta.get("change_description") if isinstance(meta, dict) else None
    if version is None and meta:
        try:
            version = int(meta.get("version"))  # type: ignore[arg-type]
        except Exception:
            version = version
    if stage is None and meta:
        stage = meta.get("stage") if isinstance(meta, dict) else None
    if progress is None and meta:
        try:
            progress_value = meta.get("progress") if isinstance(meta, dict) else None
            progress = float(progress_value) if progress_value is not None else None
        except Exception:
            progress = progress
    if summary:
        payload["summary"] = summary
    if change_description:
        payload["change_description"] = change_description
    if diff:
        payload["diff"] = diff
    if version is not None:
        payload["version"] = version
    if stage:
        payload["stage"] = stage
    if progress is not None:
        payload["progress"] = progress
    queue_stream_event(_stream_key(project_id), payload)
    return revision


def queue_project_snapshot(project_id: str) -> None:
    revision = current_revision(project_id)
    artifacts = _build_artifact_snapshot(project_id)
    payload = {
        "type": "snapshot",
        "revision": revision,
        "artifacts": artifacts,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    queue_stream_event(_stream_key(project_id), payload)
    return revision


def queue_project_draft_preview(project_id: str, preview_markdown: str) -> None:
    revision = _next_revision(project_id)
    payload = {
        "type": "draft_update",
        "preview": preview_markdown,
        "revision": revision,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    queue_stream_event(_stream_key(project_id), payload)
    return revision


async def stream_project_documents(project_id: str, start_revision: int = 0) -> AsyncGenerator[Dict[str, Any], None]:
    key = _stream_key(project_id)
    heartbeat_interval = max(0.5, _STREAM_HEARTBEAT_SECONDS)
    poll_interval = max(0.1, _STREAM_POLL_SECONDS)
    last_heartbeat = 0.0

    current = current_revision(project_id)
    if start_revision <= current:
        yield {
            "type": "snapshot",
            "revision": current,
            "artifacts": _build_artifact_snapshot(project_id),
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    while True:
        updates: List[Dict[str, Any]] = []
        queued = await artifact_stream.get_for_session(key)
        while queued is not None:
            if queued.get("revision") is None:
                queued["revision"] = _next_revision(project_id)
            updates.append(queued)
            queued = await artifact_stream.get_for_session(key)
        if updates:
            yield {
                "type": "updates",
                "updates": updates,
                "latest_revision": max(item.get("revision", 0) for item in updates),
            }
        now = time.time()
        if now - last_heartbeat >= heartbeat_interval:
            heartbeat_revision = current_revision(project_id)
            yield {
                "type": "heartbeat",
                "revision": heartbeat_revision,
                "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            last_heartbeat = now
        await asyncio.sleep(poll_interval)


def reset_project_stream(project_id: str) -> None:
    artifact_stream.reset(_stream_key(project_id))
    _project_revisions.pop(project_id, None)
