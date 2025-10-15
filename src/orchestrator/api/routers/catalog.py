from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ...domain.chat_intents import ChatIntent
from ...security.auth import User
from ...security.rbac import Permission, require_permission
from ...services.catalog_service import list_intents

router = APIRouter(prefix="/catalog", tags=["catalog"])


class ChatIntentResponse(BaseModel):
    intent_id: str
    title: str
    group: str
    description: str
    prefill_prompt: str
    deliverables: List[str] = []
    personas: List[str] = []
    guardrails: List[str] = []
    icon: Optional[str] = None
    requirement_area: Optional[str] = None
    core_functionality: Optional[str] = None
    opnxt_benefit: Optional[str] = None

    @classmethod
    def from_dataclass(cls, intent: ChatIntent) -> "ChatIntentResponse":
        return cls(
            intent_id=intent.intent_id,
            title=intent.title,
            group=intent.group,
            description=intent.description,
            prefill_prompt=intent.prefill_prompt,
            deliverables=list(intent.deliverables),
            personas=list(intent.personas),
            guardrails=list(intent.guardrails),
            icon=intent.icon,
            requirement_area=intent.requirement_area,
            core_functionality=intent.core_functionality,
            opnxt_benefit=intent.opnxt_benefit,
        )


@router.get("/intents", response_model=List[ChatIntentResponse])
def get_intents(
    persona: Optional[str] = Query(default=None, description="Filter intents prioritised for a persona (e.g., pm, engineer)"),
    user: User = Depends(require_permission(Permission.PROJECT_READ)),
) -> List[ChatIntentResponse]:
    intents = list_intents(persona=persona)
    return [ChatIntentResponse.from_dataclass(intent) for intent in intents]
