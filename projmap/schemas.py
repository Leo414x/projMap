from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


# ── Node / Edge types ──────────────────────────────────────────────

NodeType = Literal[
    "decision",
    "constraint",
    "assumption",
    "risk",
    "version",
    "config",
    "implementation_fact",
    "evaluation_result",
    "process_rule",
    "open_question",
    "raw_extraction_fragment",
]

EdgeType = Literal[
    "depends-on",
    "conflicts-with",
    "supersedes",
    "traces-back-to",
    "mitigates",
    "implements",
    "affects",
    "supports",
    "limits",
]

# v5 schema/policy versions
SCHEMA_VERSION = "v5"
PROMPT_VERSION = "decision_context_v3"
DISPLAY_POLICY_VERSION = "v2"
MODULE_ALIAS_VERSION = "v1"
VISIBILITY_POLICY_VERSION = "v1"


# ── Raw LLM output models (v5 expanded) ────────────────────────────

class ExtractedNode(BaseModel):
    type: NodeType
    title: str = Field(default="", max_length=300)
    content: str = Field(min_length=20, max_length=500)
    summary: str = Field(default="", max_length=500)
    context: str = Field(default="", max_length=1000)
    rationale: str = Field(default="", max_length=1000)
    scope: str = Field(default="", max_length=500)
    non_goals: list[str] = Field(default_factory=list)
    status_hint: str | None = None
    project_hint: str | None = None
    version_hint: str | None = None
    module_hint: str | None = None
    submodule_hint: str | None = None
    topic_hint: str | None = None
    entities: list[str] = Field(default_factory=list)
    detail: str = Field(default="", max_length=500)
    source_line: str | int | None = None
    source_heading: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    explicit_date_hint: str | None = None
    classification_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_quote: str = Field(min_length=5, max_length=1000)
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractedEdge(BaseModel):
    from_title: str = Field(default="", max_length=300)
    from_content: str = Field(default="", max_length=500)
    to_title: str = Field(default="", max_length=300)
    to_content: str = Field(default="", max_length=500)
    relationship: EdgeType
    evidence_quote: str = Field(min_length=5, max_length=1000)
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractionResult(BaseModel):
    nodes: list[ExtractedNode] = []
    edges: list[ExtractedEdge] = []


# ── Internal record models ────────────────────────────────────────

class FileRecord(BaseModel):
    path: str
    file_type: str
    content: str
    content_hash: str
    size_bytes: int
    modified_at: datetime | None = None
    status: Literal["new", "changed", "unchanged"]
    is_virtual: bool = False


class ChunkRecord(BaseModel):
    id: str
    file_path: str
    chunk_index: int
    heading_path: str | None = None
    semantic_anchor: str | None = None
    content: str
    content_hash: str
    start_line: int | None = None
    end_line: int | None = None


class RebuildStats(BaseModel):
    scanned_files: int = 0
    new_files: int = 0
    changed_files: int = 0
    unchanged_files: int = 0
    ignored_files: int = 0
    chunks_created: int = 0
    chunks_skipped: int = 0
    extractions_succeeded: int = 0
    extractions_failed: int = 0
    nodes_inserted: int = 0
    nodes_skipped_duplicate: int = 0
    edges_inserted: int = 0
    edges_dropped_unresolved: int = 0
    duration_seconds: float = 0.0


# ── Time basis ─────────────────────────────────────────────────────

TimeBasis = Literal[
    "explicit_doc_date",
    "git_first_seen",
    "git_blame_line",
    "git_commit_date",
    "file_created_at",
    "file_modified_at",
    "extraction_time",
    "unknown",
]


# ── ID helpers ─────────────────────────────────────────────────────

def _sha(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def normalize_content(text: str) -> str:
    t = text.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[.!?,;:]+$", "", t)
    return t


def file_hash(content: str) -> str:
    return _sha(content)


def chunk_id(file_path: str, semantic_anchor: str | None, content_hash: str) -> str:
    anchor = semantic_anchor or "no-anchor"
    return _sha(f"{file_path}:{anchor}:{content_hash}")


def slugify_heading_path(heading_path: str | None) -> str | None:
    if not heading_path:
        return None
    parts = [p.strip().lower() for p in heading_path.split(">") if p.strip()]
    slug_parts = []
    for part in parts:
        part = re.sub(r"[^a-z0-9]+", "-", part)
        part = re.sub(r"-+", "-", part).strip("-")
        if part:
            slug_parts.append(part)
    return "/".join(slug_parts) if slug_parts else None


def node_id(node_type: str, content: str) -> str:
    return _sha(f"{node_type}:{normalize_content(content)}")


def edge_id(from_node_id: str, to_node_id: str, relationship: str) -> str:
    return _sha(f"{from_node_id}:{to_node_id}:{relationship}")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def format_yyyy_mm(dt: datetime | str | None) -> str:
    if dt is None:
        return "unknown"
    if isinstance(dt, str):
        return dt[:7] if len(dt) >= 7 else "unknown"
    return dt.strftime("%Y-%m")
