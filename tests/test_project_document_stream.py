from __future__ import annotations

import asyncio
from typing import Any, Dict, Tuple

import pytest
from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from src.orchestrator.infrastructure.doc_store import get_doc_store
from src.orchestrator.services.project_stream import (
    reset_project_stream,
    stream_project_documents,
    queue_project_snapshot,
)
from src.orchestrator.security.auth import decode_token

from .utils import admin_headers


client = TestClient(app)


def _create_project() -> Tuple[str, Dict[str, str]]:
    headers = admin_headers(client)
    resp = client.post(
        "/projects",
        json={"name": "StreamProj", "description": "Doc stream"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    project_id = resp.json()["project_id"]
    return project_id, headers


async def _stream_until(project_id: str, predicate, start_revision: int = 0, timeout: float = 2.0) -> Dict[str, Any]:
    agen = stream_project_documents(project_id, start_revision=start_revision)
    try:
        while True:
            event = await asyncio.wait_for(agen.__anext__(), timeout=timeout)
            if predicate(event):
                return event
    finally:
        await agen.aclose()


def _wait_for_event(project_id: str, predicate, start_revision: int = 0) -> Dict[str, Any]:
    return asyncio.run(_stream_until(project_id, predicate, start_revision=start_revision))


@pytest.mark.parametrize("initial_content", ["# Initial\n", "Document body"])
def test_patch_project_document_emits_stream_updates(initial_content: str):
    project_id, headers = _create_project()
    store = get_doc_store()
    reset_project_stream(project_id)
    filename = "SRS.md"
    store.save_document(project_id, filename, initial_content, meta={"seed": True})
    queue_project_snapshot(project_id)

    snapshot = _wait_for_event(project_id, lambda evt: evt.get("type") == "snapshot")
    artifacts = snapshot.get("artifacts") or []
    assert any(item.get("filename") == filename for item in artifacts)

    payload = {
        "content": "# Updated\nWith more detail\n",
        "summary": "Manual edit of introduction",
        "section": "Introduction",
        "message_id": "msg-1",
        "change_description": "Refined intro",
    }
    resp = client.patch(
        f"/projects/{project_id}/documents/{filename}",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["filename"] == filename
    assert data["content"] == payload["content"]
    assert data["version"] >= 2
    meta = data.get("meta") or {}
    assert meta.get("manual_edit") is True
    token = headers["Authorization"].split(" ", 1)[1]
    user = decode_token(token)
    assert meta.get("edited_by") == user.email
    assert meta.get("section") == payload["section"]
    assert meta.get("change_description") == payload["change_description"]

    update_event = _wait_for_event(
        project_id,
        lambda evt: evt.get("type") == "updates"
        and any(item.get("type") == "document_update" for item in evt.get("updates") or []),
    )
    updates = update_event.get("updates") or []
    doc_updates = [item for item in updates if item.get("type") == "document_update"]
    assert doc_updates, "Expected at least one document_update event"
    doc_update = doc_updates[-1]
    assert doc_update.get("filename") == filename
    assert doc_update.get("content") == payload["content"]
    # New metadata should be surfaced for live builder integrations
    assert doc_update.get("summary") == payload["summary"]
    assert doc_update.get("change_description") == payload["change_description"]
    assert doc_update.get("section") == payload["section"]
    assert doc_update.get("message_id") == payload["message_id"]
    assert isinstance(doc_update.get("version"), int)
    assert isinstance(doc_update.get("revision"), int)

    # Version advertised in the stream should match the PATCH response
    assert doc_update.get("version") == data["version"]

    reset_project_stream(project_id)
