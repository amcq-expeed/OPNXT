from __future__ import annotations

import io
import json
from typing import List, Optional, Dict

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status, UploadFile, File
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from ...security.auth import User
from ...security.rbac import Permission, require_permission
from ...services.accelerator_service import (
    _enqueue_immediate_start,
    launch_accelerator_session,
    load_accelerator_context,
    post_accelerator_message,
    promote_accelerator_session,
    stream_accelerator_artifacts,
    list_accelerator_previews,
    list_accelerator_attachments,
    add_accelerator_attachments,
    remove_accelerator_attachment,
    get_accelerator_asset_blob,
    get_accelerator_preview_html,
)
from ...services.catalog_service import get_intent
from .catalog import ChatIntentResponse

router = APIRouter(prefix="/accelerators", tags=["accelerators"])


class AcceleratorSessionResponse(BaseModel):
    session_id: str
    accelerator_id: str
    created_by: str
    created_at: str
    persona: Optional[str]
    project_id: Optional[str]
    promoted_at: Optional[str]
    metadata: dict = Field(default_factory=dict)
    attachments: List[dict] = Field(default_factory=list)
    last_summary: Optional[str] = None


class AcceleratorMessageResponse(BaseModel):
    message_id: str
    session_id: str
    role: str
    content: str
    created_at: str


class LaunchAcceleratorResponse(BaseModel):
    session: AcceleratorSessionResponse
    intent: ChatIntentResponse
    messages: List[AcceleratorMessageResponse]


class AcceleratorPreviewResponse(BaseModel):
    version: int
    filename: str
    created_at: str
    meta: dict = Field(default_factory=dict)
    content: str | None = None


class AcceleratorMessageCreate(BaseModel):
    content: str = Field(min_length=1)
    attachments: List[str] = Field(default_factory=list)


class AcceleratorAttachmentResponse(BaseModel):
    id: str
    filename: str
    content_type: Optional[str] = None
    size: Optional[int] = None
    uploaded_at: Optional[str] = None
    preview: Optional[str] = None
    source: Optional[str] = None


class PromoteAcceleratorRequest(BaseModel):
    project_id: Optional[str] = Field(default=None, description="Existing project to attach the accelerator session to")
    name: Optional[str] = Field(default=None, description="Project name when creating a new project from this accelerator")
    description: Optional[str] = Field(default=None, description="Project description when creating a new project")


class PromoteAcceleratorResponse(BaseModel):
    session: AcceleratorSessionResponse
    project_id: str


def _to_session_response(session) -> AcceleratorSessionResponse:
    metadata = dict(session.metadata or {})
    attachments = metadata.pop("attachments", [])
    last_summary = metadata.pop("last_summary", None)
    return AcceleratorSessionResponse(
        session_id=session.session_id,
        accelerator_id=session.accelerator_id,
        created_by=session.created_by,
        created_at=session.created_at,
        persona=session.persona,
        project_id=session.project_id,
        promoted_at=session.promoted_at,
        metadata=metadata,
        attachments=attachments,
        last_summary=last_summary,
    )


def _to_message_response(message) -> AcceleratorMessageResponse:
    return AcceleratorMessageResponse(
        message_id=message.message_id,
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
    )


def _serialize_attachments(items: List[Dict[str, any]]) -> List[AcceleratorAttachmentResponse]:
    return [AcceleratorAttachmentResponse(**item) for item in items]


@router.post(
    "/{intent_id}/sessions",
    response_model=LaunchAcceleratorResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_accelerator_session(
    intent_id: str = Path(..., description="Catalog intent identifier"),
    persona: Optional[str] = Query(default=None, description="Persona label (e.g., pm, engineer) to tailor accelerator copy"),
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
) -> LaunchAcceleratorResponse:
    try:
        session, seeded_messages, intent = launch_accelerator_session(intent_id, user, persona=persona)
    except ValueError as exc:  # unknown intent
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    response = LaunchAcceleratorResponse(
        session=_to_session_response(session),
        intent=ChatIntentResponse.from_dataclass(intent),
        messages=[_to_message_response(m) for m in seeded_messages],
    )
    # safety: enqueue immediate "started" in case service path is bypassed by tests
    try:
        _enqueue_immediate_start(response.session.session_id)
    except Exception:
        pass
    return response


@router.get(
    "/sessions/{session_id}",
    response_model=LaunchAcceleratorResponse,
)
def get_accelerator_session_with_messages(
    session_id: str,
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
) -> LaunchAcceleratorResponse:
    try:
        session, intent, messages = load_accelerator_context(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return LaunchAcceleratorResponse(
        session=_to_session_response(session),
        intent=ChatIntentResponse.from_dataclass(intent),
        messages=[_to_message_response(m) for m in messages],
    )


@router.post(
    "/sessions/{session_id}/messages",
    response_model=AcceleratorMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_accelerator_message(
    session_id: str,
    payload: AcceleratorMessageCreate,
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
) -> AcceleratorMessageResponse:
    try:
        assistant = post_accelerator_message(
            session_id,
            payload.content,
            user,
            attachment_ids=payload.attachments or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _to_message_response(assistant)


@router.get(
    "/sessions/{session_id}/attachments",
    response_model=List[AcceleratorAttachmentResponse],
)
def get_accelerator_attachments(
    session_id: str,
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
) -> List[AcceleratorAttachmentResponse]:
    try:
        attachments = list_accelerator_attachments(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _serialize_attachments(attachments)


@router.post(
    "/sessions/{session_id}/attachments",
    response_model=List[AcceleratorAttachmentResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_accelerator_attachments(
    session_id: str,
    files: List[UploadFile] = File(...),
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
) -> List[AcceleratorAttachmentResponse]:
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided")
    try:
        payloads: List[tuple[str, Optional[str], bytes]] = []
        for file in files:
            try:
                content = await file.read()
            finally:
                await file.close()
            payloads.append((file.filename or "upload", file.content_type, content))
        attachments = add_accelerator_attachments(session_id, payloads, user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _serialize_attachments(attachments)


@router.delete(
    "/sessions/{session_id}/attachments/{attachment_id}",
    response_model=List[AcceleratorAttachmentResponse],
)
def delete_accelerator_attachment(
    session_id: str,
    attachment_id: str,
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
) -> List[AcceleratorAttachmentResponse]:
    try:
        attachments = remove_accelerator_attachment(session_id, attachment_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _serialize_attachments(attachments)


@router.get(
    "/sessions/{session_id}/artifacts/previews",
    response_model=List[AcceleratorPreviewResponse],
)
def get_accelerator_previews(
    session_id: str,
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
) -> List[AcceleratorPreviewResponse]:
    try:
        previews = list_accelerator_previews(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [
        AcceleratorPreviewResponse(
            version=item.get("version", 0),
            filename=str(item.get("filename", "")),
            created_at=str(item.get("created_at", "")),
            meta=dict(item.get("meta") or {}),
            content=item.get("content"),
        )
        for item in previews
    ]


@router.get(
    "/sessions/{session_id}/artifacts/{filename}/download",
)
def download_accelerator_artifact(
    session_id: str,
    filename: str,
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
):
    try:
        blob = get_accelerator_asset_blob(session_id, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found") from exc
    fileobj = io.BytesIO(blob)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(fileobj, media_type="application/octet-stream", headers=headers)


@router.get(
    "/sessions/{session_id}/artifacts/{filename}/raw",
    response_class=PlainTextResponse,
)
def raw_accelerator_artifact(
    session_id: str,
    filename: str,
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
):
    try:
        blob = get_accelerator_asset_blob(session_id, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found") from exc
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Artifact is not UTF-8 text.",
        ) from exc
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")


@router.get(
    "/sessions/{session_id}/artifacts/{filename}/preview",
)
def preview_accelerator_artifact(
    session_id: str,
    filename: str,
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
):
    try:
        html = get_accelerator_preview_html(session_id, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact preview not found") from exc
    return Response(content=html, media_type="text/html")


@router.get(
    "/sessions/{session_id}/artifacts/stream",
    response_class=StreamingResponse,
)
async def stream_session_artifacts(
    session_id: str,
    starting_revision: int = Query(0, ge=0, description="Initial artifact revision"),
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
):
    try:
        load_accelerator_context(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    async def event_stream():  # --- opnxt-stream ---
        async for payload in stream_accelerator_artifacts(session_id, start_revision=starting_revision):
            yield f"data: {json.dumps(payload)}\n\n"

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "http://localhost:3000",
        "Access-Control-Allow-Credentials": "true",
        "X-Accel-Buffering": "no",
    }

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=headers,
    )


@router.post(
    "/sessions/{session_id}/promote",
    response_model=PromoteAcceleratorResponse,
    status_code=status.HTTP_201_CREATED,
)
def promote_accelerator(
    session_id: str,
    payload: PromoteAcceleratorRequest,
    user: User = Depends(require_permission(Permission.PROJECT_WRITE)),
) -> PromoteAcceleratorResponse:
    try:
        session, project = promote_accelerator_session(
            session_id,
            user,
            project_id=payload.project_id,
            name=payload.name,
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return PromoteAcceleratorResponse(
        session=_to_session_response(session),
        project_id=project.project_id,
    )
