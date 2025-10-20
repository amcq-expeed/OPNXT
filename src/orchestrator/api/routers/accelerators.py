from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ...security.auth import User
from ...security.rbac import Permission, require_permission
from ...services.accelerator_service import (
    launch_accelerator_session,
    load_accelerator_context,
    post_accelerator_message,
    promote_accelerator_session,
    stream_accelerator_artifacts,
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


class AcceleratorMessageCreate(BaseModel):
    content: str = Field(min_length=1)


class PromoteAcceleratorRequest(BaseModel):
    project_id: Optional[str] = Field(default=None, description="Existing project to attach the accelerator session to")
    name: Optional[str] = Field(default=None, description="Project name when creating a new project from this accelerator")
    description: Optional[str] = Field(default=None, description="Project description when creating a new project")


class PromoteAcceleratorResponse(BaseModel):
    session: AcceleratorSessionResponse
    project_id: str


def _to_session_response(session) -> AcceleratorSessionResponse:
    return AcceleratorSessionResponse(
        session_id=session.session_id,
        accelerator_id=session.accelerator_id,
        created_by=session.created_by,
        created_at=session.created_at,
        persona=session.persona,
        project_id=session.project_id,
        promoted_at=session.promoted_at,
        metadata=dict(session.metadata or {}),
    )


def _to_message_response(message) -> AcceleratorMessageResponse:
    return AcceleratorMessageResponse(
        message_id=message.message_id,
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
    )


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

    return LaunchAcceleratorResponse(
        session=_to_session_response(session),
        intent=ChatIntentResponse.from_dataclass(intent),
        messages=[_to_message_response(m) for m in seeded_messages],
    )


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
        assistant = post_accelerator_message(session_id, payload.content, user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _to_message_response(assistant)


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

    async def event_stream():
        async for payload in stream_accelerator_artifacts(session_id, start_revision=starting_revision):
            yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
