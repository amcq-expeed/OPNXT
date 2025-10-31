from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Dict, List, Optional, Protocol
from pathlib import Path
import json
from threading import RLock
from ..domain.models import Project, ProjectCreate

# --- v1.0 update ---
_db_mode = os.getenv("DB_MODE", "").lower()
_mongo_repo_cls = None
if _db_mode == "mongo":
    try:
        from .repository_mongo import MongoProjectRepository as _MongoRepoImpl  # type: ignore

        _mongo_repo_cls = _MongoRepoImpl
    except Exception:
        _mongo_repo_cls = None


class ProjectRepository(Protocol):
    def list(self) -> List[Project]: ...
    def get(self, project_id: str) -> Optional[Project]: ...
    def create(self, payload: ProjectCreate) -> Project: ...
    def update_phase(self, project_id: str, new_phase: str) -> Optional[Project]: ...
    def delete(self, project_id: str) -> bool: ...


class InMemoryProjectRepository:
    """Simple in-memory project repository for MVP.

    Replace with MongoDB/GridFS implementation later.
    """

    def __init__(self) -> None:
        self._projects: Dict[str, Project] = {}
        self._counter: int = 0

    def _generate_project_id(self) -> str:
        self._counter += 1
        year = datetime.now(UTC).year
        return f"PRJ-{year}-{self._counter:04d}"

    def list(self) -> List[Project]:
        return list(self._projects.values())

    def get(self, project_id: str) -> Optional[Project]:
        return self._projects.get(project_id)

    def create(self, payload: ProjectCreate) -> Project:
        pid = self._generate_project_id()
        now = datetime.now(UTC)
        project = Project(
            project_id=pid,
            name=payload.name,
            description=payload.description,
            status="initialized",
            current_phase="charter",
            created_at=now,
            updated_at=now,
            metadata={
                "type": payload.type,
                "methodology": payload.methodology,
                "features": payload.features,
            },
        )
        self._projects[pid] = project
        return project

    def update_phase(self, project_id: str, new_phase: str) -> Optional[Project]:
        proj = self._projects.get(project_id)
        if not proj:
            return None
        proj.current_phase = new_phase
        proj.updated_at = datetime.now(UTC)
        self._projects[project_id] = proj
        return proj

    def delete(self, project_id: str) -> bool:
        """Delete a project by id. Returns True if removed."""
        return self._projects.pop(project_id, None) is not None



class FileProjectRepository:
    """Simple JSON file-backed repository for development persistence.

    Structure: a single JSON object mapping project_id -> project dict.
    Thread-safe with a coarse RLock; suitable for dev/test, not high concurrency.
    """

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._lock = RLock()
        # Default to run/projects.json at repo root
        root = Path(__file__).resolve().parents[3]
        default_path = root / "run" / "projects.json"
        self._path = Path(file_path or os.getenv("OPNXT_PROJECTS_FILE", str(default_path)))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._projects: Dict[str, Project] = {}
        self._counter: int = 0
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                # Expect dict of id -> project dict
                self._projects = {}
                max_seq = 0
                for pid, p in (data or {}).items():
                    try:
                        proj = Project(**p)
                        self._projects[pid] = proj
                        # track numeric suffix for counter continuity: PRJ-YYYY-####
                        parts = str(pid).split('-')
                        if len(parts) == 3 and parts[2].isdigit():
                            max_seq = max(max_seq, int(parts[2]))
                    except Exception:
                        continue
                self._counter = max_seq
        except Exception:
            # On any parse error, start clean (dev-friendly)
            self._projects = {}
            self._counter = 0

    def _save(self) -> None:
        try:
            obj = {pid: proj.model_dump() for pid, proj in self._projects.items()}
            self._path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
        except Exception:
            # Best-effort save; in dev we avoid crashing the app
            pass

    def _generate_project_id(self) -> str:
        self._counter += 1
        year = datetime.now(UTC).year
        return f"PRJ-{year}-{self._counter:04d}"

    def list(self) -> List[Project]:
        with self._lock:
            return list(self._projects.values())

    def get(self, project_id: str) -> Optional[Project]:
        with self._lock:
            return self._projects.get(project_id)

    def create(self, payload: ProjectCreate) -> Project:
        with self._lock:
            pid = self._generate_project_id()
            now = datetime.now(UTC)
            project = Project(
                project_id=pid,
                name=payload.name,
                description=payload.description,
                status="initialized",
                current_phase="charter",
                created_at=now,
                updated_at=now,
                metadata={
                    "type": payload.type,
                    "methodology": payload.methodology,
                    "features": payload.features,
                },
            )
            self._projects[pid] = project
            self._save()
            return project

    def update_phase(self, project_id: str, new_phase: str) -> Optional[Project]:
        with self._lock:
            proj = self._projects.get(project_id)
            if not proj:
                return None
            proj.current_phase = new_phase
            proj.updated_at = datetime.now(UTC)
            self._projects[project_id] = proj
            self._save()
            return proj

    def delete(self, project_id: str) -> bool:
        with self._lock:
            ok = self._projects.pop(project_id, None) is not None
            if ok:
                self._save()
            return ok


_repo: ProjectRepository = InMemoryProjectRepository()
_mongo_repo: ProjectRepository | None = None
_file_repo: ProjectRepository | None = None

# --- v1.0 update ---
_db_mode_mongo_enabled = _db_mode == "mongo" and _mongo_repo_cls is not None


def get_repo() -> ProjectRepository:
    global _mongo_repo
    global _file_repo
    impl = os.getenv("OPNXT_REPO_IMPL", "memory").lower()
    if _db_mode_mongo_enabled:
        if _mongo_repo is None:
            _mongo_repo = _mongo_repo_cls()  # type: ignore[operator]
        return _mongo_repo
    if impl == "mongo":
        if _mongo_repo is None:
            # --- v1.0 update ---
            repo_cls = _mongo_repo_cls
            if repo_cls is None:
                try:
                    from .repository_mongo import MongoProjectRepository as _DynamicMongoRepo  # type: ignore

                    repo_cls = _DynamicMongoRepo
                except Exception:
                    repo_cls = None
            if repo_cls is not None:
                _mongo_repo = repo_cls()  # type: ignore[operator]
            else:
                _mongo_repo = InMemoryProjectRepository()
        return _mongo_repo
    if impl == "file":
        if _file_repo is None:
            _file_repo = FileProjectRepository()
        return _file_repo
    return _repo
