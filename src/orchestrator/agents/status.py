# --- v1.0 update ---
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, Optional


# --- v1.0 update ---
_STATE_PATH = Path(os.getenv("OPNXT_AGENT_STATE_PATH", Path(tempfile.gettempdir()) / "opnxt_agent_state.json"))


# --- v1.0 update ---
def get_run_state(run_id: str) -> Optional[Dict[str, Any]]:
    try:
        if not _STATE_PATH.exists():
            return None
        data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        return data.get(run_id)
    except Exception:
        return None
