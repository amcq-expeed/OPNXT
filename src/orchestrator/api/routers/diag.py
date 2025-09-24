from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...security.rbac import require_permission, Permission

router = APIRouter(prefix="/diag", tags=["diagnostics"])

try:
    from langchain_openai import ChatOpenAI  # type: ignore
    LIB_PRESENT = True
except Exception:  # pragma: no cover - optional import
    ChatOpenAI = None  # type: ignore
    LIB_PRESENT = False


def _provider() -> str:
    if os.getenv("XAI_API_KEY"):
        return "xai"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "none"


def _base_url() -> str:
    return (
        os.getenv("XAI_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    )


def _model() -> str:
    return os.getenv("OPNXT_LLM_MODEL") or os.getenv("OPENAI_MODEL") or os.getenv("XAI_MODEL") or "gpt-4o-mini"


@router.get("/llm")
async def diag_llm():
    prov = _provider()
    has_key = prov != "none"
    return {
        "provider": prov,
        "has_api_key": has_key,
        "base_url": _base_url(),
        "model": _model(),
        "library_present": LIB_PRESENT,
        "ready": bool(LIB_PRESENT and has_key),
    }


class LLMUpdateRequest(BaseModel):
    provider: str | None = None  # e.g., "openai" or "xai"
    base_url: str | None = None
    model: str | None = None


@router.put("/llm")
def update_llm(req: LLMUpdateRequest, user=Depends(require_permission(Permission.ADMIN))):
    """Admin-only: update runtime LLM settings. Defaults to OpenAI-compatible envs.

    We mutate os.environ as a runtime override source used by services.
    """
    prov = (req.provider or _provider()).lower()
    if prov not in ("openai", "xai", "none"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported provider")

    # Update base URL
    if req.base_url:
        if prov == "xai":
            os.environ["XAI_BASE_URL"] = req.base_url
        else:  # default to openai
            os.environ["OPENAI_BASE_URL"] = req.base_url

    # Update model (shared override knob OPNXT_LLM_MODEL)
    if req.model:
        os.environ["OPNXT_LLM_MODEL"] = req.model

    # If provider explicitly set, ensure only one provider flag is active
    if req.provider:
        if prov == "xai":
            # Clear OPENAI-specific only if explicitly switching (best-effort, keep API keys as-is)
            os.environ.pop("OPENAI_BASE_URL", None)
        elif prov == "openai":
            os.environ.pop("XAI_BASE_URL", None)

    # Return updated diagnostic
    return {
        "provider": _provider(),
        "has_api_key": _provider() != "none",
        "base_url": _base_url(),
        "model": _model(),
        "library_present": LIB_PRESENT,
        "ready": bool(LIB_PRESENT and (_provider() != "none")),
    }
