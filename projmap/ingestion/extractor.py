from __future__ import annotations

import json
import os
import uuid
from typing import Any

from projmap.schemas import (
    ChunkRecord,
    ExtractionResult,
    edge_id,
    node_id,
    normalize_content,
)
from projmap.prompts import load as load_prompt


def _get_api_key(env_var: str) -> str:
    key = os.environ.get(env_var, "").strip()
    if not key:
        raise SystemExit(
            f"Missing {env_var}.\nSet it with:\n"
            f"  export {env_var}=\"your-key\""
        )
    return key


def _call_anthropic(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


class AnthropicExtractor:
    def __init__(self, model: str = "claude-sonnet-4-20250514",
                 api_key_env: str = "ANTHROPIC_API_KEY",
                 temperature: float = 0.0,
                 prompt_version: str = "v1") -> None:
        self.model = model
        self.api_key_env = api_key_env
        self.temperature = temperature
        self._api_key: str | None = None
        self._prompt_pack = load_prompt(prompt_version)

    @property
    def api_key(self) -> str:
        if self._api_key is None:
            self._api_key = _get_api_key(self.api_key_env)
        return self._api_key

    def _build_user_prompt(self, chunk: ChunkRecord) -> str:
        examples_text = json.dumps(
            self._prompt_pack.examples.get("good_examples", []),
            indent=2, ensure_ascii=False,
        )
        return (
            f"## Document chunk to extract from\n\n"
            f"Source file: {chunk.file_path}\n"
            f"Chunk index: {chunk.chunk_index}\n"
            f"Heading path: {chunk.heading_path or 'N/A'}\n\n"
            f"Content:\n{chunk.content}\n\n"
            f"## Examples\n\n```json\n{examples_text}\n```"
        )

    def extract(self, chunk: ChunkRecord) -> ExtractionResult:
        system_prompt = self._prompt_pack.prompt_text
        user_prompt = self._build_user_prompt(chunk)
        raw = _call_anthropic(
            self.api_key, self.model,
            system_prompt, user_prompt, self.temperature,
        )
        parsed = _parse_json(raw)
        return ExtractionResult.model_validate(parsed)


def resolve_edges(
    result: ExtractionResult,
    chunk_nodes_ids: dict[str, str],
    file_nodes_ids: dict[str, str] | None = None,
) -> list[tuple[str, str, str, str, float]]:
    file_nodes_ids = file_nodes_ids or {}
    resolved: list[tuple[str, str, str, str, float]] = []

    for edge in result.edges:
        from_nid = _find_node_id(edge.from_content, result.nodes, chunk_nodes_ids, file_nodes_ids)
        to_nid = _find_node_id(edge.to_content, result.nodes, chunk_nodes_ids, file_nodes_ids)
        if from_nid and to_nid:
            resolved.append((from_nid, to_nid, edge.relationship,
                             edge.evidence_quote, edge.confidence))

    return resolved


def _find_node_id(
    content: str,
    chunk_nodes: list,
    chunk_ids: dict[str, str],
    file_ids: dict[str, str],
) -> str | None:
    norm = normalize_content(content)
    if norm in chunk_ids:
        return chunk_ids[norm]
    if norm in file_ids:
        return file_ids[norm]
    return None


def build_node_lookup(result: ExtractionResult) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for n in result.nodes:
        norm = node_id(n.type, n.content)
        key = normalize_content(n.content)
        lookup[key] = norm
    return lookup
