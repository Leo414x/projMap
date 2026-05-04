"""Source resolver: determine source_scope from node metadata."""

from __future__ import annotations


def resolve_source_project(source_file: str = "", content: str = "") -> dict:
    """Determine source scope from node metadata."""
    return {"project": "Unknown", "version": "-", "source_scope": "unknown"}
