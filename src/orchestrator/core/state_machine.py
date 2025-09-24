from __future__ import annotations

from typing import Dict, List, Optional

# State machine transitions (aligned to SRS Appendix B)
PHASE_TRANSITIONS: Dict[str, List[str]] = {
    "initialization": ["charter"],
    "charter": ["requirements"],
    "requirements": ["specifications"],
    "specifications": ["design"],
    "design": ["implementation"],
    "implementation": ["testing"],
    "testing": ["deployment"],
    "deployment": ["maintenance"],
    "maintenance": ["end"],
}


def next_phase(current: str) -> Optional[str]:
    options = PHASE_TRANSITIONS.get(current, [])
    return options[0] if options else None


def is_valid_transition(current: str, target: str) -> bool:
    return target in PHASE_TRANSITIONS.get(current, [])
