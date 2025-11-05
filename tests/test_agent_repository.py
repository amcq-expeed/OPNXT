from datetime import datetime, timezone

import pytest

from src.orchestrator.domain.agent_models import AgentCreate, AgentUpdate
from src.orchestrator.infrastructure.agent_repository import InMemoryAgentRepository


@pytest.fixture
def repo():
    return InMemoryAgentRepository()


def test_create_assigns_incremental_id_and_defaults(repo):
    payload = AgentCreate(
        name="Test Agent",
        description="Handles testing",
        capabilities=["search"],
    )

    created = repo.create(payload)

    assert created.agent_id.startswith(f"AGT-{datetime.now(timezone.utc).year}-")
    assert created.status == "inactive"
    assert created.capabilities == ["search"]
    assert created.created_at.tzinfo is not None
    assert repo.get(created.agent_id) == created


def test_update_merges_fields_and_sets_timestamp(repo):
    initial = repo.create(
        AgentCreate(name="Original", description="First", capabilities=["plan"])
    )

    updated = repo.update(
        initial.agent_id,
        AgentUpdate(description="Updated", status="active", capabilities=["plan", "execute"]),
    )

    assert updated.description == "Updated"
    assert updated.status == "active"
    assert updated.capabilities == ["plan", "execute"]
    assert updated.updated_at >= updated.created_at


def test_delete_returns_false_when_missing(repo):
    assert repo.delete("unknown") is False


def test_list_returns_all_agents(repo):
    created = [
        repo.create(AgentCreate(name=f"Agent {idx}"))
        for idx in range(2)
    ]

    agents = repo.list()
    assert {agent.agent_id for agent in agents} == {agent.agent_id for agent in created}
