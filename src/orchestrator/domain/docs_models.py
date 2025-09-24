from __future__ import annotations

from typing import List, Optional, Dict
from pydantic import BaseModel


class DocumentArtifact(BaseModel):
    filename: str
    content: str
    path: Optional[str] = None  # relative path where saved, if any


class DocGenResponse(BaseModel):
    project_id: str
    saved_to: Optional[str] = None
    artifacts: List[DocumentArtifact]


class DocGenOptions(BaseModel):
    traceability_overlay: bool = True
    paste_requirements: Optional[str] = None
    answers: Optional[Dict[str, List[str]]] = None
    summaries: Optional[Dict[str, str]] = None


class EnrichRequest(BaseModel):
    prompt: str


class EnrichResponse(BaseModel):
    answers: Dict[str, List[str]]
    summaries: Dict[str, str]


class AIGenRequest(BaseModel):
    input_text: str = ""
    doc_types: Optional[List[str]] = None
    include_backlog: bool = False


class ProjectContext(BaseModel):
    """Arbitrary context pack stored per project for doc generation and planning.

    Keys like 'answers', 'summaries', and any custom overlays are allowed.
    """
    data: Dict[str, object] = {}


class ImpactRequest(BaseModel):
    changed: List[str]  # list of FR IDs (e.g., ["FR-003", "FR-011"]) or doc keys
    strategy: str | None = "heuristic"


class ImpactItem(BaseModel):
    kind: str  # 'document' | 'code'
    name: str
    confidence: float = 0.7


class ImpactResponse(BaseModel):
    project_id: str
    impacts: List[ImpactItem]


class DocumentVersionInfo(BaseModel):
    version: int
    created_at: str
    meta: Dict[str, object] = {}


class DocumentVersionsResponse(BaseModel):
    project_id: str
    versions: Dict[str, List[DocumentVersionInfo]]


class DocumentVersionResponse(BaseModel):
    filename: str
    version: int
    content: str


class UploadAnalyzeItem(BaseModel):
    filename: str
    text_length: int
    requirements: List[str]


class UploadAnalyzeResponse(BaseModel):
    project_id: str
    items: List[UploadAnalyzeItem]


class UploadApplyRequest(BaseModel):
    requirements: List[str] = []
    category: str = "Requirements"
    append_only: bool = True
