from __future__ import annotations

"""RBAC helpers aligned with SRS NFR-004."""
from enum import Enum
from typing import Set, Callable
from fastapi import Depends, HTTPException, status

from .auth import User, get_current_user


class Permission(str, Enum):
    PROJECT_READ = "project:read"
    PROJECT_WRITE = "project:write"
    AGENT_READ = "agent:read"
    AGENT_WRITE = "agent:write"
    DOCUMENT_APPROVE = "document:approve"
    ADMIN = "admin:*"


ROLE_PERMISSIONS = {
    "viewer": {Permission.PROJECT_READ, Permission.AGENT_READ},
    "contributor": {Permission.PROJECT_READ, Permission.PROJECT_WRITE, Permission.AGENT_READ, Permission.AGENT_WRITE},
    "approver": {Permission.PROJECT_READ, Permission.PROJECT_WRITE, Permission.AGENT_READ, Permission.AGENT_WRITE, Permission.DOCUMENT_APPROVE},
    "admin": {Permission.ADMIN},
}


def _user_permissions(user: User) -> Set[Permission]:
    perms: Set[Permission] = set()
    for role in user.roles:
        perms |= ROLE_PERMISSIONS.get(role, set())
    return perms


def _is_authorized(user: User, required: Permission) -> bool:
    perms = _user_permissions(user)
    if Permission.ADMIN in perms:
        return True
    return required in perms


def require_permission(required: Permission) -> Callable[[User], User]:
    """FastAPI dependency to enforce a single permission on a route."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if not _is_authorized(user, required):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency
