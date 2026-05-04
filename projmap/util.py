"""Shared helpers used across api, pipeline, and skill modules."""

from __future__ import annotations

from projmap.schemas import normalize_content


def _ok(**kwargs) -> dict:
    result = {"ok": True, "warnings": [], "errors": []}
    result.update(kwargs)
    return result


def _err(error_code: str, message: str, **kwargs) -> dict:
    result = {"ok": False, "error_code": error_code, "message": message,
              "warnings": [], "errors": []}
    result.update(kwargs)
    return result


def resolve_edge_node(content: str, chunk_lookup: dict[str, str]) -> str | None:
    norm = normalize_content(content)
    return chunk_lookup.get(norm)
