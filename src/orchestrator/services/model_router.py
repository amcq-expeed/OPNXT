"""Routing helpers for selecting the appropriate model provider.

The router does not couple directly to concrete SDK clients; instead it
selects a provider configuration that the calling service can use to
instantiate the preferred LLM or retrieval backend. This keeps the
selection policy unit-testable and avoids importing heavyweight SDKs in
the hot path when they are not required.
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse
from dataclasses import dataclass
from typing import Dict, Optional, Iterable, Set


@dataclass(frozen=True)
class ProviderSelection:
    """Returned details about the provider that should handle a task."""

    name: str
    model: str
    api_key_env: Optional[str]
    base_url_env: Optional[str] = None
    default_base_url: Optional[str] = None
    requires_api_key: bool = True


class ModelRouter:
    """Simple policy-based router for multi-model orchestration."""

    PROVIDER_CONFIG: Dict[str, Dict[str, Optional[str] | bool]] = {
        "openai": {
            "api_key_env": "OPENAI_API_KEY",
            "base_url_env": "OPENAI_BASE_URL",
            "model_env": "OPENAI_MODEL",
            "default_model": "gpt-4o-mini",
            "default_base_url": "https://api.openai.com/v1",
        },
        "gemini": {
            "api_key_env": "GEMINI_API_KEY",
            "base_url_env": "GEMINI_BASE_URL",
            "model_env": "GEMINI_MODEL",
            "default_model": "gemini-2.5-flash",
            "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
        },
        "xai": {
            "api_key_env": "XAI_API_KEY",
            "base_url_env": "XAI_BASE_URL",
            "model_env": "XAI_MODEL",
            "default_model": "grok-2-latest",
            "default_base_url": "https://api.x.ai/v1",
        },
        "search": {
            "api_key_env": "GOOGLE_SEARCH_API_KEY",
            "base_url_env": "GOOGLE_SEARCH_BASE_URL",
            "model_env": "GOOGLE_SEARCH_MODEL",
            "default_model": "google-search-api",
        },
        "local": {
            "api_key_env": "LOCAL_API_KEY",
            "base_url_env": "LOCAL_BASE_URL",
            "model_env": "LOCAL_MODEL",
            "default_model": "gpt-oss:120b",
            "default_base_url": "http://127.0.0.1:11434",
            "requires_api_key": False,
        },
    }

    ROUTING_POLICY: Dict[str, tuple[str, ...]] = {
        # Everyday conversation should prefer cost-effective hosted models first.
        "conversation": ("gemini", "openai", "xai", "local"),
        # Traceable artifacts (charter, SRS, etc.) prioritise the premium model.
        "governance_artifact": ("openai", "gemini", "xai", "local"),
        # Retrieval augmented or real-time lookups use the search pipeline first.
        "realtime_grounding": ("search", "openai"),
    }

    def __init__(
        self,
        env: Optional[Dict[str, str]] = None,
        allowed_providers: Optional[Iterable[str]] = None,
    ) -> None:
        self._env = env or os.environ
        self._allowed: Optional[Set[str]] = set(allowed_providers) if allowed_providers else None
        preferred = (self._env.get("OPNXT_MODEL_PROVIDER") or "").strip().lower()
        force_flag = (self._env.get("OPNXT_FORCE_MODEL_PROVIDER") or "").strip().lower() in ("1", "true", "yes")
        if env is None and preferred and force_flag:
            self._forced_provider = preferred
        else:
            # When a custom env dict is supplied (e.g., unit tests) or force flag not set, ignore forced overrides
            self._forced_provider = None
        self._preferred_provider = preferred if preferred else None

    # ------------------------------------------------------------------
    # Provider resolution helpers
    # ------------------------------------------------------------------
    def _provider_available(self, provider: str) -> bool:
        cfg = self.PROVIDER_CONFIG.get(provider)
        if not cfg:
            return False
        if self._allowed is not None and provider not in self._allowed:
            return False
        requires_key = bool(cfg.get("requires_api_key", True))
        api_key_env = cfg.get("api_key_env")
        if requires_key:
            if not api_key_env:
                return False
            return bool(self._env.get(api_key_env))

        if provider == "local":
            enforced = self._forced_provider == "local"
            enabled_flag = (self._env.get("OPNXT_ENABLE_LOCAL_PROVIDER") or "").strip() == "1"
            if not (enforced or enabled_flag):
                return False
            base_url_env = cfg.get("base_url_env")
            api_key_env = cfg.get("api_key_env")
            has_base = bool(base_url_env and self._env.get(base_url_env))
            has_key = bool(api_key_env and self._env.get(api_key_env))
            return has_base or has_key

        base_url_env = cfg.get("base_url_env") or ""
        base_url = self._env.get(base_url_env, cfg.get("default_base_url") or "")
        if not base_url:
            return False

        parsed = urlparse(base_url)
        host = parsed.hostname
        if not host:
            return False
        if parsed.scheme == "https":
            port = parsed.port or 443
        else:
            port = parsed.port or 80

        try:
            with socket.create_connection((host, port), timeout=1.5):
                return True
        except OSError:
            # Treat network failures as unavailable to encourage fallback.
            return False

    def _resolve_selection(self, provider: str) -> ProviderSelection:
        cfg = self.PROVIDER_CONFIG[provider]
        model_env = cfg.get("model_env") or ""
        model = self._env.get(model_env, cfg.get("default_model") or "")
        return ProviderSelection(
            name=provider,
            model=model,
            api_key_env=cfg.get("api_key_env"),
            base_url_env=cfg.get("base_url_env"),
            default_base_url=cfg.get("default_base_url"),
            requires_api_key=bool(cfg.get("requires_api_key", True)),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def select_provider(self, purpose: str) -> ProviderSelection:
        """Return the provider selected for the supplied purpose.

        Raises
        ------
        RuntimeError
            If no providers configured for the requested purpose are
            currently available.
        """

        priority = list(self.ROUTING_POLICY.get(purpose, self.ROUTING_POLICY["conversation"]))
        if self._preferred_provider and self._preferred_provider in self.PROVIDER_CONFIG:
            priority = [self._preferred_provider] + [p for p in priority if p != self._preferred_provider]
        if self._forced_provider:
            if self._allowed is not None and self._forced_provider not in self._allowed:
                pass
            elif self._provider_available(self._forced_provider):
                return self._resolve_selection(self._forced_provider)
        for provider in priority:
            if self._provider_available(provider):
                return self._resolve_selection(provider)
        raise RuntimeError("No active model provider available for this task.")

    def maybe_select_provider(self, purpose: str) -> Optional[ProviderSelection]:
        """Like :meth:`select_provider` but returns ``None`` on failure."""

        try:
            return self.select_provider(purpose)
        except RuntimeError:
            return None

    def generate_metadata(self, purpose: str, query_for_grounding: Optional[str] = None) -> Dict[str, Optional[str]]:
        """Return metadata describing the chosen provider.

        This helper allows services to log or branch on provider
        selections without exposing API keys directly.
        """

        selection = self.select_provider(purpose)
        return {
            "provider": selection.name,
            "model": selection.model,
            "api_key_env": selection.api_key_env,
            "base_url_env": selection.base_url_env,
            "grounding_query": query_for_grounding,
        }
