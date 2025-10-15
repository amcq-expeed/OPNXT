from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from ...security.auth import User
from ...security.rbac import Permission, require_permission
from ...services.telemetry_sink import TelemetryEvent, list_recent_events, record_event

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


class TelemetryEventPayload(BaseModel):
    name: str
    properties: dict[str, object] | None = None


class TelemetryIngestRequest(BaseModel):
    events: List[TelemetryEventPayload]
    source: Optional[str] = None


class TelemetryIngestResponse(BaseModel):
    accepted: int


class TelemetryRecentResponse(BaseModel):
    events: List[TelemetryEvent]


@router.post("/events", response_model=TelemetryIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_events(
    payload: TelemetryIngestRequest,
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
) -> TelemetryIngestResponse:
    count = 0
    actor = user.email if user else None
    for event in payload.events:
        record_event(
            TelemetryEvent(
                name=event.name,
                properties=event.properties or {},
                actor=actor,
            )
        )
        count += 1
    return TelemetryIngestResponse(accepted=count)


@router.get("/events/recent", response_model=TelemetryRecentResponse)
async def recent_events(
    limit: int = 25,
    _: User = Depends(require_permission(Permission.ADMIN)),
) -> TelemetryRecentResponse:
    events = list_recent_events(limit)
    return TelemetryRecentResponse(events=events)
