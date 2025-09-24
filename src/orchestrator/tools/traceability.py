from __future__ import annotations

"""Traceability matrix generator for OPNXT.

This module builds a lightweight functional and NFR traceability map by scanning
for the presence of modules, routers, and utilities that satisfy planned items.

It is intentionally heuristic-based (file and symbol presence) to avoid running
application code during CI. It can be extended to parse OpenAPI routes, inspect
Docstrings, or integrate with a richer SRS model.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Any
import json
import xml.etree.ElementTree as ET

# ---- Types ----

@dataclass
class TraceItem:
    title: str
    status: str  # present | partial | missing
    code: List[str]


# ---- Core builder ----

def _exists(project_root: Path, rel: str) -> bool:
    return (project_root / rel).exists()


def _any_exists(project_root: Path, paths: List[str]) -> bool:
    return any(_exists(project_root, p) for p in paths)


def build_traceability(project_root: Path) -> Dict[str, Any]:
    """Build the traceability structure in-memory.

    Returns a dict with keys: source_of_truth, map, nfr
    """
    # Normalize to repo root (allow being called from anywhere)
    project_root = project_root.resolve()

    # Sources of truth (requirements/specs/backlog)
    source_of_truth = [
        "docs/Claude/orchestrator_charter.md",
        "docs/Claude/orchestrator_brd.md",
        "docs/Claude/orchestrator_srs.md",
        "docs/Claude/orchestrator_tdd.md",
        "docs/Claude/ai_sdlc_platform_architecture.md",
        "docs/Claude/orchestrator_backlog.md",
    ]

    # Helper refs
    AUTH_FILES = [
        "src/orchestrator/api/routers/auth.py",
        "src/orchestrator/security/auth.py",
        "src/orchestrator/security/rbac.py",
    ]
    PROJECT_FILES = [
        "src/orchestrator/api/routers/projects.py",
        "src/orchestrator/domain/models.py",
        "src/orchestrator/infrastructure/repository.py",
    ]
    STATE_MACHINE = ["src/orchestrator/core/state_machine.py"]
    DOC_GEN = ["src/sdlc_generator.py"]
    UI_FILES = [
        "frontend/pages/projects.tsx",
        "frontend/pages/projects/[id].tsx",
        "frontend/pages/agents.tsx",
        "frontend/pages/login.tsx",
        "frontend/lib/api.ts",
    ]
    CHAT_UI = ["frontend/pages/projects/[id].tsx"]
    DOC_VIEW = ["frontend/pages/projects/[id].tsx"]
    LLM_INTEG = ["src/orchestrator/services/doc_ai.py"]
    AGENT_DISC = ["src/discovery_agent.py"]
    AGENT_REGISTRY = [
        "src/orchestrator/api/routers/agents.py",
        "src/orchestrator/infrastructure/agent_repository.py",
        "src/orchestrator/domain/agent_models.py",
    ]

    def _file_contains(project_root: Path, rel: str, needle: str) -> bool:
        try:
            p = project_root / rel
            if not p.exists():
                return False
            text = p.read_text(encoding="utf-8", errors="ignore")
            return needle in text
        except Exception:
            return False


    def _status_for(fr_id: str) -> Tuple[str, List[str]]:
        if fr_id == "FR-001":
            # Consider User Registration present if auth router defines /register
            auth_router = "src/orchestrator/api/routers/auth.py"
            if _exists(project_root, auth_router) and _file_contains(project_root, auth_router, "/register"):
                return ("present", [auth_router])
            return ("missing", [])
        if fr_id == "FR-002":
            code = [p for p in AUTH_FILES if _exists(project_root, p)]
            return ("present" if len(code) >= 2 else ("partial" if code else "missing"), code)
        if fr_id == "FR-003":
            code = [p for p in PROJECT_FILES if _exists(project_root, p)]
            return ("present" if len(code) >= 2 else ("partial" if code else "missing"), code)
        if fr_id == "FR-004":
            code = [p for p in STATE_MACHINE if _exists(project_root, p)] + [p for p in PROJECT_FILES if _exists(project_root, p)]
            return ("present" if _any_exists(project_root, STATE_MACHINE) else ("partial" if code else "missing"), code)
        if fr_id == "FR-005":
            code = [p for p in AGENT_DISC if _exists(project_root, p)] + [p for p in AGENT_REGISTRY if _exists(project_root, p)]
            # Selection logic is not fully implemented yet
            status = "partial" if code else "missing"
            return (status, code)
        if fr_id == "FR-006":
            # Context management present if context_store exists and /context routes defined
            ctx_store = _exists(project_root, "src/orchestrator/services/context_store.py")
            proj_router = "src/orchestrator/api/routers/projects.py"
            ctx_routes = _exists(project_root, proj_router) and (
                _file_contains(project_root, proj_router, "/context")
            )
            if ctx_store and ctx_routes:
                return ("present", ["src/orchestrator/services/context_store.py", proj_router])
            return ("partial" if (ctx_store or ctx_routes) else "missing", [p for p in ["src/orchestrator/services/context_store.py", proj_router] if _exists(project_root, p)])
        if fr_id == "FR-007":
            return ("missing", [])
        if fr_id == "FR-008":
            code = [p for p in DOC_GEN if _exists(project_root, p)]
            return ("present" if code else "missing", code)
        if fr_id == "FR-009":
            # Document version control present if doc_store exists and version endpoints present
            doc_store = _exists(project_root, "src/orchestrator/infrastructure/doc_store.py")
            proj_router = "src/orchestrator/api/routers/projects.py"
            version_routes = _exists(project_root, proj_router) and (
                _file_contains(project_root, proj_router, "/documents/versions")
            )
            if doc_store and version_routes:
                return ("present", ["src/orchestrator/infrastructure/doc_store.py", proj_router])
            return ("partial" if (doc_store or version_routes) else "missing", [p for p in ["src/orchestrator/infrastructure/doc_store.py", proj_router] if _exists(project_root, p)])
        if fr_id == "FR-010":
            # Document storage: partial with in-memory store; present when persistent storage is implemented
            doc_store = _exists(project_root, "src/orchestrator/infrastructure/doc_store.py")
            return ("partial" if doc_store else "missing", ["src/orchestrator/infrastructure/doc_store.py"] if doc_store else [])
        if fr_id == "FR-011":
            # This generator counts as initial implementation
            code = ["src/orchestrator/tools/traceability.py"]
            return ("present", [p for p in code if _exists(project_root, p)])
        if fr_id == "FR-012":
            # Change impact analysis present if /impacts route exists in projects router
            proj_router = "src/orchestrator/api/routers/projects.py"
            if _exists(project_root, proj_router) and _file_contains(project_root, proj_router, "/impacts"):
                return ("present", [proj_router])
            return ("missing", [])
        if fr_id == "FR-013":
            code = [p for p in UI_FILES if _exists(project_root, p)]
            return ("present" if code else "missing", code)
        if fr_id == "FR-014":
            code = [p for p in CHAT_UI if _exists(project_root, p)]
            return ("present" if code else "missing", code)
        if fr_id == "FR-015":
            code = [p for p in DOC_VIEW if _exists(project_root, p)]
            return ("present" if code else "missing", code)
        if fr_id == "FR-016":
            code = [p for p in LLM_INTEG if _exists(project_root, p)]
            return ("present" if code else "missing", code)
        if fr_id == "FR-017":
            return ("missing", [])
        return ("missing", [])

    # Build FR map
    titles: Dict[str, str] = {
        "FR-001": "User Registration",
        "FR-002": "Authentication (JWT)",
        "FR-003": "Project Creation API",
        "FR-004": "Project State Management",
        "FR-005": "Agent Selection",
        "FR-006": "Context Management",
        "FR-007": "Agent Communication",
        "FR-008": "Document Generation",
        "FR-009": "Document Version Control",
        "FR-010": "Document Storage (DB/GridFS)",
        "FR-011": "Requirements Traceability",
        "FR-012": "Change Impact Analysis",
        "FR-013": "Dashboard UI",
        "FR-014": "Chat Interface",
        "FR-015": "Document Viewer",
        "FR-016": "LLM Integration (OpenAI/Claude)",
        "FR-017": "Webhook Support",
    }

    fr_map: Dict[str, Dict[str, Any]] = {}
    for fr_id, title in titles.items():
        status, code = _status_for(fr_id)
        fr_map[fr_id] = {"title": title, "status": status, "code": code}

    # Compute coverage if coverage.xml exists
    coverage_current: Any = "low"
    cov_xml = project_root / "coverage.xml"
    if cov_xml.exists():
        try:
            root = ET.parse(cov_xml).getroot()
            # coverage.xml root has attribute line-rate in coverage.py reports
            line_rate = root.attrib.get("line-rate")
            if line_rate is not None:
                pct = round(float(line_rate) * 100.0, 1)
                coverage_current = pct
        except Exception:
            coverage_current = "unknown"

    metrics_present = _exists(project_root, "src/orchestrator/observability/metrics.py")

    # NFRs
    nfr = {
        "jwt": "present" if _any_exists(project_root, AUTH_FILES) else "missing",
        "rbac": "present" if _exists(project_root, "src/orchestrator/security/rbac.py") else "missing",
        "tls": "missing",  # no TLS termination in-repo
        "observability": (
            "present" if metrics_present else ("partial" if _exists(project_root, "src/orchestrator/api/main.py") else "missing")
        ),
        "p95_latency_ms": {
            "targets": {"chat": 3000, "doc_gen": 10000, "dashboard": 2000},
            "measurement": "metrics_exposed" if metrics_present else "not_implemented",
        },
        "tests": {"coverage_target": 80, "current": coverage_current},
    }

    return {
        "source_of_truth": source_of_truth,
        "map": fr_map,
        "nfr": nfr,
    }


def generate_traceability_map(project_root: Path | None = None, out_path: Path | None = None) -> Path:
    """Generate and write the traceability map JSON to disk.

    Args:
        project_root: repo root (defaults to cwd)
        out_path: output json path (defaults to reports/traceability-map.json)
    Returns:
        Path to the written JSON file
    """
    project_root = (project_root or Path(".")).resolve()
    data = build_traceability(project_root)
    if out_path is None:
        out_path = project_root / "reports" / "traceability-map.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    path = generate_traceability_map()
    print(f"Traceability map written to {path}")
