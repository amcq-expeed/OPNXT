from __future__ import annotations

# --- v1.0 update ---
import os
from contextlib import contextmanager

from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from src.orchestrator.infrastructure import repository, doc_store, chat_store


# --- v1.0 update ---
@contextmanager
def _env_override(**values: str):
    original = {k: os.environ.get(k) for k in values}
    try:
        os.environ.update({k: v for k, v in values.items() if v is not None})
        yield
    finally:
        for key, val in original.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val


# --- v1.0 update ---
def _reset_singletons() -> None:
    repository._repo = repository.InMemoryProjectRepository()
    repository._mongo_repo = None
    repository._file_repo = None
    doc_store._doc_store_singleton = None
    chat_store._store = None


# --- v1.0 update ---
client = TestClient(app)


# --- v1.0 update ---
def _seed_project(name: str = "Agent Test") -> str:
    repo = repository.get_repo()
    project = repo.create(repository.ProjectCreate(name=name, description="Demo"))
    return project.project_id


# --- v1.0 update ---
def test_orchestrate_returns_bundle_without_llm_keys() -> None:
    _reset_singletons()
    project_id = _seed_project()
    payload = {
        "goal": "Generate MVP docs",
        "project_id": project_id,
        "options": {"stack_prefs": {"frontend": "Next.js", "backend": "FastAPI"}},
    }
    response = client.post("/orchestrate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {"run_id", "outputs", "timeline"}
    outputs = data["outputs"]
    assert isinstance(outputs, dict)
    for key in ["docs", "design", "code", "tests", "devops"]:
        assert key in outputs
    serialized = str(outputs)
    assert "OPENAI_API_KEY" not in serialized
    assert data["timeline"]


# --- v1.0 update ---
def test_orchestrate_pipeline_order() -> None:
    _reset_singletons()
    project_id = _seed_project("Pipeline Order")
    response = client.post(
        "/orchestrate",
        json={
            "goal": "Plan full build",
            "project_id": project_id,
        },
    )
    assert response.status_code == 200
    timeline = response.json()["timeline"]
    agent_sequence = [step.get("agent") for step in timeline]
    assert agent_sequence == [
        "requirements",
        "architect",
        "dev",
        "qa",
        "devops",
    ]


# --- v1.0 update ---
def test_repository_switches_with_env() -> None:
    _reset_singletons()
    with _env_override(DB_MODE="memory", OPNXT_REPO_IMPL="memory"):
        repo = repository.get_repo()
        assert isinstance(repo, repository.InMemoryProjectRepository)

    _reset_singletons()
    with _env_override(DB_MODE="mongo"):
        repo = repository.get_repo()
        assert repo is not None

    _reset_singletons()
    with _env_override(OPNXT_REPO_IMPL="mongo"):
        repo = repository.get_repo()
        assert repo is not None
