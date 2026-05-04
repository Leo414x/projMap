"""Prompt Registry — single source of truth for ALL projMap LLM prompts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PromptPack:
    """A versioned prompt bundle."""
    purpose: str
    version: str
    prompt_text: str
    schema: dict[str, Any] | None = None
    examples: list[dict] | None = None


_PROMPTS_DIR = Path(__file__).parent
_VERSION_RE = re.compile(r"^v\d+$")

# Only extraction purpose has schema + examples files
_HAS_SCHEMA = {"extraction"}
_HAS_EXAMPLES = {"extraction"}


def load(purpose: str = "extraction", version: str = "v1") -> PromptPack:
    """Load a prompt pack by purpose and version.

    Backward compatible: load("v1") is treated as load(purpose="extraction", version="v1").
    """
    # Legacy compat: if purpose looks like a version string, treat it as the old API
    if _VERSION_RE.match(purpose) and version == "v1":
        version = purpose
        purpose = "extraction"

    prompt_path = _PROMPTS_DIR / f"{purpose}_{version}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    prompt_text = prompt_path.read_text(encoding="utf-8")

    schema = None
    if purpose in _HAS_SCHEMA:
        schema_path = _PROMPTS_DIR / f"{purpose}_schema_{version}.json"
        if not schema_path.exists():
            schema_path = _PROMPTS_DIR / f"schema_{version}.json"
        if schema_path.exists():
            schema = json.loads(schema_path.read_text(encoding="utf-8"))

    examples = None
    if purpose in _HAS_EXAMPLES:
        examples_path = _PROMPTS_DIR / f"{purpose}_examples_{version}.json"
        if not examples_path.exists():
            examples_path = _PROMPTS_DIR / f"examples_{version}.json"
        if examples_path.exists():
            examples = json.loads(examples_path.read_text(encoding="utf-8"))

    return PromptPack(
        purpose=purpose,
        version=version,
        prompt_text=prompt_text,
        schema=schema,
        examples=examples,
    )


def split_prompt_sections(prompt_text: str) -> tuple[str, str]:
    """Split a prompt .md file into system and user template sections.

    Looks for '## System' and '## User template' headers.
    Returns (system, user_template). If headers not found, returns ("", full_text).
    """
    if "## System" not in prompt_text or "## User template" not in prompt_text:
        return "", prompt_text

    parts = prompt_text.split("## User template", 1)
    system_part = parts[0]
    user = parts[1].strip() if len(parts) > 1 else ""

    system_block = system_part.split("## System", 1)
    system = system_block[1].strip() if len(system_block) > 1 else ""

    # Remove content after the next ## header (e.g. ## User template)
    lines = system.split("\n")
    clean = []
    for line in lines:
        if line.startswith("## ") and "System" not in line:
            break
        clean.append(line)
    system = "\n".join(clean).strip()

    return system, user


def prompt_version_from_config(cfg: Any, purpose: str = "extraction") -> str:
    """Read prompt version from projmap config. Falls back to 'v1'."""
    # New format: prompt_versions dict
    pv = getattr(cfg, "prompt_versions", None)
    if pv and isinstance(pv, dict):
        v = pv.get(purpose)
        if v:
            return v

    # Legacy format: prompt_version field (extraction only)
    if purpose == "extraction":
        return getattr(cfg, "prompt_version", "v1") or "v1"

    return "v1"
