from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str
    description: str
    type: Optional[str] = Field(default=None, description="Project type")
    methodology: Optional[str] = Field(default=None, description="Methodology e.g., agile")
    features: Optional[str] = Field(default=None, description="Multiline feature list entered by user")


class Project(BaseModel):
    project_id: str
    name: str
    description: str
    status: str
    current_phase: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    metadata: dict = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    methodology: Optional[str] = None
    features: Optional[str] = None
