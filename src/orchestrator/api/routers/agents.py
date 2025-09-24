from __future__ import annotations

from typing import List
from fastapi import APIRouter, HTTPException, status, Depends, Response

from ...domain.agent_models import Agent, AgentCreate, AgentUpdate
from ...infrastructure.agent_repository import get_agents_repo
from ...security.rbac import require_permission, Permission

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=List[Agent])
def list_agents(user=Depends(require_permission(Permission.AGENT_READ))) -> List[Agent]:
    repo = get_agents_repo()
    return repo.list()


@router.post("", response_model=Agent, status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreate, user=Depends(require_permission(Permission.AGENT_WRITE))) -> Agent:
    repo = get_agents_repo()
    return repo.create(payload)


@router.get("/{agent_id}", response_model=Agent)
def get_agent(agent_id: str, user=Depends(require_permission(Permission.AGENT_READ))) -> Agent:
    repo = get_agents_repo()
    agent = repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}", response_model=Agent)
def update_agent(agent_id: str, patch: AgentUpdate, user=Depends(require_permission(Permission.AGENT_WRITE))) -> Agent:
    repo = get_agents_repo()
    updated = repo.update(agent_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail="Agent not found")
    return updated


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_agent(agent_id: str, user=Depends(require_permission(Permission.ADMIN))) -> Response:
    repo = get_agents_repo()
    ok = repo.delete(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Agent not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
