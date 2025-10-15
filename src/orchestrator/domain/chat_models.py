from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class ChatSessionCreate(BaseModel):
    project_id: str
    title: Optional[str] = None
    persona: Optional[str] = None


class ChatSession(BaseModel):
    session_id: str
    project_id: str
    title: str
    created_at: str
    updated_at: str
    created_by: str
    persona: Optional[str] = None


Role = Literal["system", "user", "assistant"]


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1)


class ChatMessage(BaseModel):
    message_id: str
    session_id: str
    role: Role
    content: str
    created_at: str


class ChatSessionWithMessages(BaseModel):
    session: ChatSession
    messages: List[ChatMessage]
