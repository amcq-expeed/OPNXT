"""Routing helpers for selecting the appropriate model provider.

The router does not couple directly to concrete SDK clients; instead it
selects a provider configuration that the calling service can use to
instantiate the preferred LLM or retrieval backend. This keeps the
selection policy unit-testable and avoids importing heavyweight SDKs in
the hot path when they are not required.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional, Iterable, Set


@dataclass(frozen=True)
class ProviderSelection:
    """Returned details about the provider that should handle a task."""

    name: str
    model: str
    api_key_env: str
    base_url_env: Optional[str] = None


class ModelRouter:
    """Simple policy-based router for multi-model orchestration."""

    PROVIDER_CONFIG: Dict[str, Dict[str, Optional[str]]] = {
        "openai": {
            "api_key_env": "OPENAI_API_KEY",
            "base_url_env": "OPENAI_BASE_URL",
            "model_env": "OPENAI_MODEL",
            "default_model": "gpt-4o-mini",
        },
        "gemini": {
            "api_key_env": "GEMINI_API_KEY",
            "base_url_env": "GEMINI_BASE_URL",
            "model_env": "GEMINI_MODEL",
            "default_model": "gemini-2.5-flash",
        },
        "xai": {
            "api_key_env": "XAI_API_KEY",
            "base_url_env": "XAI_BASE_URL",
            "model_env": "XAI_MODEL",
            "default_model": "grok-2-latest",
        },
        "search": {
            "api_key_env": "GOOGLE_SEARCH_API_KEY",
            "base_url_env": "GOOGLE_SEARCH_BASE_URL",
            "model_env": "GOOGLE_SEARCH_MODEL",
            "default_model": "google-search-api",
        },
    }

    ROUTING_POLICY: Dict[str, tuple[str, ...]] = {
        # Everyday conversation should prefer the more cost-effective model.
        "conversation": ("gemini", "openai", "xai"),
        # Traceable artifacts (charter, SRS, etc.) prioritise the premium model.
        "governance_artifact": ("openai", "gemini", "xai"),
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

    # ------------------------------------------------------------------
    # Provider resolution helpers
    # ------------------------------------------------------------------
    def _provider_available(self, provider: str) -> bool:
        cfg = self.PROVIDER_CONFIG.get(provider)
        if not cfg:
            return False
        if self._allowed is not None and provider not in self._allowed:
            return False
        api_key_env = cfg["api_key_env"]
        if not api_key_env:
            return False
        return bool(self._env.get(api_key_env))

    def _resolve_selection(self, provider: str) -> ProviderSelection:
        cfg = self.PROVIDER_CONFIG[provider]
        model = self._env.get(cfg["model_env"] or "", cfg["default_model"] or "")
        return ProviderSelection(
            name=provider,
            model=model,
            api_key_env=cfg["api_key_env"],
            base_url_env=cfg.get("base_url_env"),
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

        priority = self.ROUTING_POLICY.get(purpose, self.ROUTING_POLICY["conversation"])
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
