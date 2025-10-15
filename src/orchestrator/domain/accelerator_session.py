from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AcceleratorSession:
    accelerator_id: str
    session_id: str
    created_by: str
    created_at: str
    persona: Optional[str] = None
    project_id: Optional[str] = None
    promoted_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class AcceleratorTranscript:
    session_id: str
    messages: List[dict]


@dataclass
class AcceleratorMessage:
    message_id: str
    session_id: str
    role: str
    content: str
    created_at: str
