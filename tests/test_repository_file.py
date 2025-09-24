from src.orchestrator.infrastructure.repository import FileProjectRepository
from src.orchestrator.domain.models import ProjectCreate


def test_file_repo_crud_and_persistence(tmp_path):
    pfile = tmp_path / "projects.json"
    repo = FileProjectRepository(file_path=str(pfile))

    # Initially empty
    assert repo.list() == []

    # Create project
    proj = repo.create(ProjectCreate(name="Unit Test", description="Desc", type=None, methodology=None, features=None))
    assert proj.project_id.startswith("PRJ-")
    assert repo.get(proj.project_id) is not None

    # Update phase
    upd = repo.update_phase(proj.project_id, "requirements")
    assert upd is not None and upd.current_phase == "requirements"

    # Persisted to file and reload into a fresh repo
    repo2 = FileProjectRepository(file_path=str(pfile))
    got = repo2.get(proj.project_id)
    assert got is not None and got.name == "Unit Test"

    # Delete
    ok = repo2.delete(proj.project_id)
    assert ok is True
    assert repo2.get(proj.project_id) is None
