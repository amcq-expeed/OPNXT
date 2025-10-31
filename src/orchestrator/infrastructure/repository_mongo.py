# --- v1.0 update ---
from __future__ import annotations

# --- v1.0 update ---
import asyncio
from datetime import UTC, datetime
import os
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - optional dependency
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection  # type: ignore
except Exception:  # pragma: no cover - dependency optional
    AsyncIOMotorClient = None  # type: ignore
    AsyncIOMotorCollection = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from pymongo import ReturnDocument  # type: ignore
except Exception:  # pragma: no cover - dependency optional
    ReturnDocument = None  # type: ignore

from ..domain.models import Project, ProjectCreate


# --- v1.0 update ---
_SHARED_FALLBACK_REPO: "InMemoryProjectRepository" | None = None


class MongoProjectRepository:
    def __init__(self) -> None:
        self._client: AsyncIOMotorClient | None = None
        self._collection: AsyncIOMotorCollection | None = None
        self._fallback: "InMemoryProjectRepository" | None = None
        self._connect()

    # --- v1.0 update ---
    def list(self) -> List[Project]:
        if self._collection is None:
            return self._fallback_repo().list()
        try:
            docs = self._run(self._collection.find().sort("created_at", 1).to_list(length=5000))
            return [self._to_project(doc) for doc in docs]
        except Exception:
            return self._fallback_repo().list()

    # --- v1.0 update ---
    def get(self, project_id: str) -> Optional[Project]:
        if self._collection is None:
            return self._fallback_repo().get(project_id)
        try:
            doc = self._run(self._collection.find_one({"project_id": project_id}))
            if not doc:
                return None
            return self._to_project(doc)
        except Exception:
            return self._fallback_repo().get(project_id)

    # --- v1.0 update ---
    def create(self, payload: ProjectCreate) -> Project:
        if self._collection is None:
            return self._fallback_repo().create(payload)
        project = self._build_project(payload)
        try:
            awaitable = self._collection.insert_one(self._from_project(project))
            self._run(awaitable)
            return project
        except Exception:
            return self._fallback_repo().create(payload)

    # --- v1.0 update ---
    def update_phase(self, project_id: str, new_phase: str) -> Optional[Project]:
        if self._collection is None:
            return self._fallback_repo().update_phase(project_id, new_phase)
        try:
            updated_at = datetime.now(UTC)
            kwargs: Dict[str, Any] = {
                "project_id": project_id,
            }
            update_doc = {"$set": {"current_phase": new_phase, "updated_at": updated_at}}
            if ReturnDocument is not None:
                result = self._run(
                    self._collection.find_one_and_update(
                        kwargs,
                        update_doc,
                        return_document=ReturnDocument.AFTER,
                    )
                )
            else:
                result = self._run(
                    self._collection.find_one_and_update(
                        kwargs,
                        update_doc,
                        return_document=True,
                    )
                )
            if not result:
                return None
            return self._to_project(result)
        except Exception:
            return self._fallback_repo().update_phase(project_id, new_phase)

    # --- v1.0 update ---
    def delete(self, project_id: str) -> bool:
        if self._collection is None:
            return self._fallback_repo().delete(project_id)
        try:
            res = self._run(self._collection.delete_one({"project_id": project_id}))
            return bool(res and res.deleted_count)
        except Exception:
            return self._fallback_repo().delete(project_id)

    # --- v1.0 update ---
    def _connect(self) -> None:
        if AsyncIOMotorClient is None:
            return
        try:
            mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
            mongo_db = os.getenv("MONGO_DB", "opnxt")
            self._client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=500)
            self._run(self._client.server_info())
            self._collection = self._client[mongo_db]["projects"]
            self._run(self._collection.create_index("project_id", unique=True))
        except Exception:
            self._client = None
            self._collection = None

    # --- v1.0 update ---
    def _fallback_repo(self):
        global _SHARED_FALLBACK_REPO
        if _SHARED_FALLBACK_REPO is None:
            from .repository import InMemoryProjectRepository  # type: ignore

            _SHARED_FALLBACK_REPO = InMemoryProjectRepository()
        if self._fallback is None:
            self._fallback = _SHARED_FALLBACK_REPO
        return self._fallback

    # --- v1.0 update ---
    def _run(self, coro: Any) -> Any:
        if not asyncio.iscoroutine(coro):
            return coro
        try:
            return asyncio.run(coro)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

    # --- v1.0 update ---
    def _build_project(self, payload: ProjectCreate) -> Project:
        now = datetime.now(UTC)
        project_id = self._generate_project_id()
        return Project(
            project_id=project_id,
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

    # --- v1.0 update ---
    def _generate_project_id(self) -> str:
        year = datetime.now(UTC).year
        counter = 0
        if self._collection is not None:
            try:
                latest = self._run(
                    self._collection.find({}, {"project_id": 1})
                    .sort("project_id", -1)
                    .limit(1)
                    .to_list(length=1)
                )
                if latest:
                    last_id = str(latest[0].get("project_id", ""))
                    parts = last_id.split("-")
                    if len(parts) == 3 and parts[2].isdigit():
                        counter = int(parts[2])
            except Exception:
                counter = 0
        return f"PRJ-{year}-{counter + 1:04d}"

    # --- v1.0 update ---
    def _to_project(self, doc: Dict[str, Any]) -> Project:
        doc = dict(doc)
        doc.pop("_id", None)
        return Project(**doc)

    # --- v1.0 update ---
    def _from_project(self, project: Project) -> Dict[str, Any]:
        data = project.model_dump()
        data["created_at"] = project.created_at
        data["updated_at"] = project.updated_at
        return data
