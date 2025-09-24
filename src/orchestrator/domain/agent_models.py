from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, HttpUrl, Field


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    endpoint_url: Optional[HttpUrl] = None


class Agent(BaseModel):
    agent_id: str
    name: str
    description: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    endpoint_url: Optional[HttpUrl] = None
    status: str = "inactive"
    created_at: datetime
    updated_at: Optional[datetime] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    capabilities: Optional[List[str]] = None
    endpoint_url: Optional[HttpUrl] = None
    status: Optional[str] = None
