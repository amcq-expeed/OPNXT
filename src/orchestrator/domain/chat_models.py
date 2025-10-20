from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class ChatSessionCreate(BaseModel):
    project_id: str
    title: Optional[str] = None
    persona: Optional[str] = None


class GuestChatSessionCreate(BaseModel):
    title: Optional[str] = None
    initial_message: Optional[str] = None
    persona: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class ChatSession(BaseModel):
    session_id: str
    project_id: Optional[str]
    title: str
    created_at: str
    updated_at: str
    created_by: str
    persona: Optional[str] = None
    kind: Literal["project", "guest"] = "project"


Role = Literal["system", "user", "assistant"]


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1)
    provider: Optional[str] = None
    model: Optional[str] = None


class ChatMessage(BaseModel):
    message_id: str
    session_id: str
    role: Role
    content: str
    created_at: str
    metadata: Optional[dict] = None


class ChatSessionWithMessages(BaseModel):
    session: ChatSession
    messages: List[ChatMessage]


class ChatModelOption(BaseModel):
    provider: str
    model: str
    label: str
    description: Optional[str] = None
    available: bool
    adaptive: bool = False


class ChatSearchHit(BaseModel):
    session: ChatSession
    message: ChatMessage
    snippet: str


class ChatTemplate(BaseModel):
    template_id: str
    title: str
    description: str
    prompt: str
    tags: List[str] = []
