from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from ..domain.agent_models import Agent, AgentCreate, AgentUpdate


class InMemoryAgentRepository:
    """Simple in-memory Agent repository for MVP.

    Replace with persistent implementation later.
    """

    def __init__(self) -> None:
        self._agents: Dict[str, Agent] = {}
        self._counter: int = 0

    def _generate_agent_id(self) -> str:
        self._counter += 1
        year = datetime.utcnow().year
        return f"AGT-{year}-{self._counter:04d}"

    def list(self) -> List[Agent]:
        return list(self._agents.values())

    def get(self, agent_id: str) -> Optional[Agent]:
        return self._agents.get(agent_id)

    def create(self, payload: AgentCreate) -> Agent:
        aid = self._generate_agent_id()
        now = datetime.utcnow()
        agent = Agent(
            agent_id=aid,
            name=payload.name,
            description=payload.description,
            capabilities=list(payload.capabilities or []),
            endpoint_url=payload.endpoint_url,
            status="inactive",
            created_at=now,
            updated_at=now,
        )
        self._agents[aid] = agent
        return agent

    def update(self, agent_id: str, patch: AgentUpdate) -> Optional[Agent]:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        data = agent.model_dump()
        upd = patch.model_dump(exclude_unset=True)
        data.update({k: v for k, v in upd.items() if v is not None})
        data["updated_at"] = datetime.utcnow()
        self._agents[agent_id] = Agent(**data)
        return self._agents[agent_id]

    def delete(self, agent_id: str) -> bool:
        return self._agents.pop(agent_id, None) is not None


_agents_repo = InMemoryAgentRepository()


def get_agents_repo() -> InMemoryAgentRepository:
    return _agents_repo
