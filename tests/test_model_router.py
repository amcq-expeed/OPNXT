"""Unit tests for `ModelRouter` provider selection and metadata."""

from __future__ import annotations

import os
from typing import Dict

import pytest
from unittest.mock import patch

from src.orchestrator.services.model_router import ModelRouter, ProviderSelection


@pytest.fixture(autouse=True)
def clean_env():
    """Ensure each test starts with a clean slate of credentials."""

    original_env = dict(os.environ)
    for key in [
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_SEARCH_API_KEY",
        "LOCAL_API_KEY",
        "LOCAL_BASE_URL",
        "LOCAL_MODEL",
        "LOCAL_MODEL_FALLBACKS",
        "OPNXT_ENABLE_LOCAL_PROVIDER",
        "OPNXT_MODEL_PROVIDER",
        "OPNXT_FORCE_MODEL_PROVIDER",
    ]:
        os.environ.pop(key, None)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(original_env)


def _with_env(values: Dict[str, str]) -> ModelRouter:
    """Helper to instantiate a router with a patched environment."""

    env = dict(os.environ)
    env.update(values)
    return ModelRouter(env=env)


def test_router_prefers_gemini_for_conversation():
    router = _with_env({"GEMINI_API_KEY": "gemini", "OPENAI_API_KEY": "openai"})
    selection = router.select_provider("conversation")
    assert isinstance(selection, ProviderSelection)
    assert selection.name == "gemini"
    assert selection.model == "gemini-2.5-flash"
    assert selection.api_key_env == "GEMINI_API_KEY"


def test_router_prefers_openai_for_governance():
    router = _with_env({"GEMINI_API_KEY": "gemini", "OPENAI_API_KEY": "openai"})
    selection = router.select_provider("governance_artifact")
    assert selection.name == "openai"
    assert selection.model == "gpt-4o-mini"
    assert selection.api_key_env == "OPENAI_API_KEY"


def test_router_falls_back_to_openai_when_gemini_missing():
    router = _with_env({"OPENAI_API_KEY": "openai"})
    selection = router.select_provider("conversation")
    assert selection.name == "openai"


def test_router_falls_back_to_gemini_when_openai_missing():
    router = _with_env({"GEMINI_API_KEY": "gemini"})
    selection = router.select_provider("governance_artifact")
    assert selection.name == "gemini"


def test_router_requires_at_least_one_provider():
    router = ModelRouter(env={})
    with pytest.raises(RuntimeError, match="No active model provider available"):
        router.select_provider("conversation")


def test_router_maybe_select_provider_returns_none_when_unavailable():
    router = ModelRouter(env={})
    assert router.maybe_select_provider("conversation") is None


def test_router_selects_search_for_realtime_grounding():
    router = _with_env({"GOOGLE_SEARCH_API_KEY": "search"})
    selection = router.select_provider("realtime_grounding")
    assert selection.name == "search"
    assert selection.model == "google-search-api"


def test_generate_metadata_exposes_non_secret_fields():
    router = _with_env({"OPENAI_API_KEY": "openai"})
    metadata = router.generate_metadata("governance_artifact", query_for_grounding="status")
    assert metadata["provider"] == "openai"
    assert metadata["model"] == "gpt-4o-mini"
    assert metadata["api_key_env"] == "OPENAI_API_KEY"
    assert metadata["grounding_query"] == "status"


def test_router_uses_local_fallbacks_when_enabled():
    router = _with_env(
        {
            "OPNXT_ENABLE_LOCAL_PROVIDER": "1",
            "LOCAL_BASE_URL": "http://127.0.0.1:11434",
            "LOCAL_MODEL_FALLBACKS": "llama3.2:latest, mixtral:8x22b",
        }
    )
    selection = router.select_provider("conversation")
    assert selection.name == "local"
    assert selection.model == "llama3.2:latest"


def test_router_defaults_to_curated_local_model_when_no_env_models():
    router = _with_env(
        {
            "OPNXT_ENABLE_LOCAL_PROVIDER": "1",
            "LOCAL_BASE_URL": "http://127.0.0.1:11434",
        }
    )
    selection = router.select_provider("conversation")
    assert selection.name == "local"
    assert selection.model == "mixtral:8x22b"
