import time as real_time

from fastapi.testclient import TestClient

from src.orchestrator.api.main import app
from src.orchestrator.infrastructure.accelerator_store import get_accelerator_store
from src.orchestrator.services import accelerator_service

from .utils import otp_login


client = TestClient(app)


def _auth_headers():
    headers, _ = otp_login(client, "adam.thacker@expeed.com")
    return headers


def test_design_build_guidance_generates_code_artifacts(monkeypatch):
    headers = _auth_headers()

    stub_payload = {
        "code": {
            "path": "src/orchestrator/services/clinical_rules.py",
            "language": "python",
            "content": "def evaluate_intake(intake, rules):\n    return []",
        },
        "tests": {
            "path": "tests/test_clinical_rules.py",
            "language": "python",
            "content": "def test_evaluate_intake():\n    assert True",
        },
        "config": {
            "path": "config/rules.yaml",
            "language": "yaml",
            "content": "- id: sample\n  when: []\n  alert:\n    type: info",
        },
        "notes": ["stubbed output"],
        "source": "test",
    }

    monkeypatch.setattr(
        accelerator_service,
        "_generate_code_payload",
        lambda session, intent, latest_input: stub_payload,
    )
    monkeypatch.setattr(accelerator_service.time, "sleep", lambda _: None)

    launch = client.post("/accelerators/design-build-guidance/sessions", headers=headers)
    assert launch.status_code == 201
    session_id = launch.json()["session"]["session_id"]

    msg = client.post(
        f"/accelerators/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "Please scaffold the rules engine."},
    )
    assert msg.status_code == 201

    store = get_accelerator_store()
    for _ in range(100):
        artifacts = store.list_artifacts(session_id)
        kinds = {item.get("meta", {}).get("type") for item in artifacts}
        if {"code", "test", "config"}.issubset(kinds):
            break
        real_time.sleep(0.05)
    else:
        raise AssertionError("Code artifacts were not generated in time")

    artifacts = store.list_artifacts(session_id)
    paths = {item.get("filename") for item in artifacts}
    assert stub_payload["code"]["path"] in paths
    assert stub_payload["tests"]["path"] in paths
    assert stub_payload["config"]["path"] in paths
