"""Prompt Registry — single source of truth for extraction prompts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PromptPack:
    """A versioned prompt bundle."""
    version: str
    prompt_text: str
    schema: dict[str, Any]
    examples: list[dict]


_PROMPTS_DIR = Path(__file__).parent


def load(version: str = "v1") -> PromptPack:
    """Load a prompt pack by version.

    Raises:
        FileNotFoundError: If the specified version files don't exist.
    """
    prompt_path = _PROMPTS_DIR / f"extraction_{version}.md"
    schema_path = _PROMPTS_DIR / f"schema_{version}.json"
    examples_path = _PROMPTS_DIR / f"examples_{version}.json"

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    if not examples_path.exists():
        raise FileNotFoundError(f"Examples file not found: {examples_path}")

    prompt_text = prompt_path.read_text(encoding="utf-8")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    examples = json.loads(examples_path.read_text(encoding="utf-8"))

    return PromptPack(
        version=version,
        prompt_text=prompt_text,
        schema=schema,
        examples=examples,
    )


def prompt_version_from_config(cfg: Any) -> str:
    """Read prompt version from projmap config. Falls back to 'v1'."""
    return getattr(cfg, "prompt_version", "v1") or "v1"
