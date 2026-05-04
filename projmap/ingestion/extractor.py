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

SYSTEM_PROMPT = """\
You are extracting a project decision memory graph.
Extract only information that is explicitly supported by the provided document chunk.
Return strict JSON only. Do not include markdown. Do not include commentary.

Node types:
- decision: a concrete choice, approved plan, frozen direction, or explicit "do not" boundary
- constraint: a rule, limitation, or non-negotiable requirement
- assumption: a belief or condition the project depends on
- risk: a known risk, blocker, or failure mode
- version: a named version, milestone, or frozen baseline
- config: a parameter, threshold, or setting
- implementation_fact: a current implementation detail (not a decision)
- evaluation_result: a metric result, backtest outcome, or study finding
- process_rule: a workflow rule, step order, or review requirement
- open_question: an unresolved question or pending decision

Edge relationship types:
- depends-on: source requires target
- conflicts-with: source contradicts target
- supersedes: source replaces target
- traces-back-to: source evolved from target
- mitigates: source reduces target risk
- implements: source implements target
- affects: source impacts target
- supports: source supports target
- limits: source constrains target

Rules:
- Every node must include evidence_quote from the chunk.
- Every edge must include evidence_quote from the chunk.
- Do not invent facts.
- Do not infer relationships without textual evidence.
- Do not generate IDs.
- If no valid nodes or edges exist, return empty arrays.

CRITICAL — Node content must be SELF-CONTAINED and SPECIFIC:
- Include the subject (project name, system name, model version, etc.) in every node.
- BAD: "K mapping", "Training window", "Embargo setting"
- GOOD: "V13 uses K horizons of 3, 6, and 8 bars for prediction targets"
- Each title and summary must be complete sentences that make sense WITHOUT reading the source.

DECISION classification — only mark as decision when:
- A specific option was chosen or approved
- A direction was frozen or deprecated
- A system boundary was defined ("does NOT do X")
Do NOT mark as decision: plain facts, metric results, default params, TODOs, or background info.

Structured fields per node:
- title: short declarative sentence (e.g. "V13 Section 8.3 approved for Paper/Shadow only")
- summary: one-sentence explanation
- context: what system/module this relates to and why it matters
- rationale: why this choice was made (omit if not stated)
- scope: where this applies (omit if not stated)
- non_goals: list of things explicitly excluded (omit if none stated)
- status_hint: one of active/paper_only/diagnostic_only/frozen/superseded/deprecated
- project_hint / version_hint / module_hint / submodule_hint: if identifiable
- explicit_date_hint: if a specific date is mentioned (YYYY-MM-DD)
- entities: key terms mentioned (system names, model names, section numbers)
"""

USER_PROMPT_TEMPLATE = """\
Extract project memory nodes and edges from this document chunk.

Source file: {source_file}
Chunk index: {chunk_index}

Content:
{chunk_content}

Return JSON in this exact shape:
{{
  "nodes": [
    {{
      "type": "decision | constraint | assumption | risk | version | config | implementation_fact | evaluation_result | process_rule | open_question",
      "title": "complete self-contained declarative sentence",
      "content": "one complete self-contained sentence including subject and context",
      "summary": "one sentence explanation",
      "context": "what system/module and why it matters",
      "rationale": "why this choice was made (or empty)",
      "scope": "where this applies (or empty)",
      "non_goals": ["excluded thing"],
      "status_hint": "active | paper_only | diagnostic_only | frozen | superseded | deprecated",
      "project_hint": "project name if identifiable",
      "version_hint": "version if identifiable (e.g. V13)",
      "module_hint": "module if identifiable",
      "submodule_hint": "submodule if identifiable",
      "topic_hint": "short topic label",
      "entities": ["V13", "Section 8.3"],
      "evidence_quote": "short direct quote from chunk",
      "source_heading": "heading from chunk",
      "line_start": null,
      "line_end": null,
      "explicit_date_hint": "YYYY-MM-DD or null",
      "classification_confidence": 0.8,
      "confidence": 0.85
    }}
  ],
  "edges": [
    {{
      "from_title": "must match title of a node",
      "from_content": "must match content of a node",
      "to_title": "must match title of a node",
      "to_content": "must match content of a node",
      "relationship": "depends-on | conflicts-with | supersedes | traces-back-to | mitigates | implements | affects | supports | limits",
      "evidence_quote": "short direct quote from chunk",
      "confidence": 0.8
    }}
  ]
}}
"""


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
                 temperature: float = 0.0) -> None:
        self.model = model
        self.api_key_env = api_key_env
        self.temperature = temperature
        self._api_key: str | None = None

    @property
    def api_key(self) -> str:
        if self._api_key is None:
            self._api_key = _get_api_key(self.api_key_env)
        return self._api_key

    def extract(self, chunk: ChunkRecord) -> ExtractionResult:
        user_prompt = USER_PROMPT_TEMPLATE.format(
            source_file=chunk.file_path,
            chunk_index=chunk.chunk_index,
            chunk_content=chunk.content,
        )
        raw = _call_anthropic(
            self.api_key, self.model,
            SYSTEM_PROMPT, user_prompt, self.temperature,
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
