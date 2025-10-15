from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class ChatIntent:
    intent_id: str
    title: str
    group: str
    description: str
    prefill_prompt: str
    deliverables: List[str] = field(default_factory=list)
    personas: List[str] = field(default_factory=list)
    guardrails: List[str] = field(default_factory=list)
    icon: Optional[str] = None
    requirement_area: Optional[str] = None
    core_functionality: Optional[str] = None
    opnxt_benefit: Optional[str] = None
