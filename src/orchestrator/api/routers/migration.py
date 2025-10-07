from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...security.auth import get_current_user, User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["migration"])


class ProjectMigrationRequest(BaseModel):
    guestUserId: str
    projectId: str


@router.post("/migrate-project", status_code=status.HTTP_200_OK)
def migrate_project(req: ProjectMigrationRequest, user: User = Depends(get_current_user)) -> dict[str, str]:
    """Handle migration of guest artifacts into a permanent user workspace.

    This is a placeholder implementation that enforces authentication and logs the
    migration intent. The actual copy/delete operations should be implemented by the
    backend team once the storage integration is finalized.
    """
    if user.email == "guest@example.com":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Anonymous guests must upgrade before migration.",
        )

    logger.info(
        "Migration requested by %s for project %s (guest UID: %s)",
        user.email,
        req.projectId,
        req.guestUserId,
    )

    # TODO: Implement storage migration from the guest path to the permanent user path.

    return {"status": "ok", "message": "Migration acknowledged. Backend implementation pending."}
