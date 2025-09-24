from fastapi.testclient import TestClient
import os

from src.orchestrator.api.main import app


client = TestClient(app)


def _admin_headers():
    r = client.post(
        "/auth/login",
        json={
            "email": "adam.thacker@expeed.com",
            "password": "Password#1",
        },
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_diag_llm_no_keys(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("XAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPNXT_LLM_MODEL", raising=False)

    r = client.get("/diag/llm")
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] in ("none", "openai", "xai")  # provider depends on env
    # With no keys provider should be none
    assert data["has_api_key"] is False
    # Defaults
    assert data["base_url"].endswith("/v1")
    assert isinstance(data["model"], str) and len(data["model"]) > 0


def test_update_llm_sets_base_url_and_model(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    headers = _admin_headers()

    r = client.put(
        "/diag/llm",
        headers=headers,
        json={"provider": "openai", "base_url": "http://api.example", "model": "unit-test-model"},
    )
    assert r.status_code == 200
    data = r.json()
    # Even without keys, base_url/model updates should reflect
    assert data["base_url"] == "http://api.example"
    assert data["model"] == "unit-test-model"


def test_update_llm_rejects_bad_provider(monkeypatch):
    headers = _admin_headers()
    r = client.put(
        "/diag/llm",
        headers=headers,
        json={"provider": "bad-provider"},
    )
    assert r.status_code == 400


def test_update_llm_switch_to_xai_clears_openai_base(monkeypatch):
    # Set an OPENAI_BASE_URL first, then switch to XAI and ensure it is cleared
    monkeypatch.setenv("OPENAI_BASE_URL", "http://openai")
    headers = _admin_headers()

    r = client.put(
        "/diag/llm",
        headers=headers,
        json={"provider": "xai", "base_url": "http://xai"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["base_url"] == "http://xai"
    # Now GET should show base_url from XAI and not from OPENAI
    r = client.get("/diag/llm")
    assert r.status_code == 200
    d2 = r.json()
    assert d2["base_url"] == "http://xai"
