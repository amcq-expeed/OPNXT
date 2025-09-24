from pathlib import Path

from src.orchestrator.tools.traceability import build_traceability


def test_build_traceability_basic():
    data = build_traceability(Path("."))
    assert isinstance(data, dict)
    assert "map" in data and isinstance(data["map"], dict)
    assert "nfr" in data and isinstance(data["nfr"], dict)

    fr = data["map"]
    # JWT auth and RBAC should be present based on existing files
    assert fr["FR-002"]["status"] in {"present", "partial"}
    # Projects CRUD present
    assert fr["FR-003"]["status"] == "present"
    # Requirements traceability now present (this module)
    assert fr["FR-011"]["status"] in {"present", "partial"}

    nfr = data["nfr"]
    assert nfr["jwt"] in {"present", "partial"}
    assert nfr["rbac"] == "present"
    assert nfr["tls"] == "missing"
