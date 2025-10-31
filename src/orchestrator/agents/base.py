# --- v1.0 update ---
from __future__ import annotations

from typing import Any, Dict


class BaseAgent:
    # --- v1.0 update ---
    name: str = "base"

    # --- v1.0 update ---
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError
