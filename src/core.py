"""Core logic stubs for OPNXT SDLC automation system."""

from typing import Dict


def summarize_project(description: str) -> Dict[str, str]:
    """Return a minimal structured summary for a given project description.

    This is a placeholder for future LLM-powered implementations.
    """
    return {
        "title": (description.split(". ")[0] if description else "Untitled Project"),
        "summary": description or "No description provided.",
    }
