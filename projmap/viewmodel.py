"""ViewModel builder: transforms raw DB rows into renderable ViewModels."""

from __future__ import annotations

from dataclasses import dataclass, field

from projmap.resolvers import (
    compute_display_priority,
    format_confidence_label,
    format_module_label,
    format_project_version,
    format_source_confidence,
    format_source_label,
    format_status_label,
    format_time_display,
    format_type_label,
    resolve_badges,
    resolve_sort_time,
    resolve_time_label,
    resolve_time_value,
    resolve_visibility,
    truncate_text,
)
from projmap.schemas import format_yyyy_mm


@dataclass
class RowViewModel:
    node_id: str = ""
    type: str = ""
    type_label: str = ""
    project: str = ""
    version: str = ""
    project_version_label: str = ""
    module: str = ""
    module_label: str = ""
    submodule: str | None = None
    topic: str = ""
    title: str = ""
    summary: str = ""
    status: str = ""
    status_label: str = ""
    status_severity: str = ""

    time_value: str = ""
    time_label: str = ""
    time_display: str = ""
    time_basis: str = ""
    time_confidence: float = 0.0
    time_confidence_label: str = ""
    sort_time: str = ""
    timeline_bucket: str = ""

    rationale_short: str = ""
    context_short: str = ""
    scope_short: str = ""

    source_label: str = ""
    source_file: str = ""
    source_heading: str | None = None
    source_line_start: int | None = None
    source_line_end: int | None = None
    source_confidence_label: str = ""

    confidence: float = 0.0
    confidence_label: str = ""
    classification_confidence: float = 0.0
    classification_confidence_label: str = ""

    display_priority: float = 0.0
    is_default_visible: bool = True
    hidden_reason: str | None = None

    badges: list[str] = field(default_factory=list)
    related_counts: dict[str, int] = field(default_factory=dict)

    detail_context: str = ""
    detail_rationale: str = ""
    detail_scope: str = ""
    detail_non_goals: list[str] = field(default_factory=list)
    detail_evidence_quote: str = ""
    detail_edges: list[dict] = field(default_factory=list)

    # Source metadata
    evidence_quote: str = ""
    schema_version: str = ""
    is_legacy: bool = False


def build_row(
    node: dict,
    source: dict | None = None,
    edge_counts: dict | None = None,
    edge_summaries: list[dict] | None = None,
) -> RowViewModel:
    """Build a RowViewModel from a node dict + optional source/edge data."""
    row = RowViewModel()

    # ── Identity ──────────────────────────────────────────────
    row.node_id = node.get("id", "")
    row.type = node.get("type", "raw_extraction_fragment")
    row.type_label = format_type_label(row.type)

    # ── Classification ────────────────────────────────────────
    row.project = node.get("project") or "Unassigned Project"
    row.version = node.get("version") or "-"
    row.project_version_label = format_project_version(row.project, row.version)
    row.module = node.get("module") or "unknown"
    row.module_label = format_module_label(row.module)
    row.submodule = node.get("submodule")
    row.topic = node.get("topic") or node.get("title", "")
    row.classification_confidence = node.get("classification_confidence", 0.0)
    row.classification_confidence_label = format_confidence_label(row.classification_confidence)

    # ── Title / Summary (with fallback) ───────────────────────
    row.title = node.get("title") or node.get("summary") or node.get("content") or "Untitled memory"
    row.summary = node.get("summary") or node.get("content") or row.title

    # ── Status ────────────────────────────────────────────────
    row.status = node.get("status") or "unknown"
    row.status_label = format_status_label(row.status)
    row.status_severity = node.get("status_severity") or _status_severity(row.status)

    # ── Time ──────────────────────────────────────────────────
    decision_time = node.get("decision_time")
    time_basis = node.get("decision_time_basis") or "unknown"
    time_conf = node.get("decision_time_confidence", 0.0)
    first_seen = node.get("first_seen_at")
    extracted_at = node.get("extracted_at")
    source_modified = source.get("source_modified_at") if source else None

    row.time_value = resolve_time_value(decision_time, first_seen, extracted_at, source_modified)
    row.time_label = resolve_time_label(time_basis, time_conf)
    row.time_display = format_time_display(row.time_label, row.time_value)
    row.time_basis = time_basis
    row.time_confidence = time_conf
    row.time_confidence_label = format_confidence_label(time_conf)
    row.sort_time = resolve_sort_time(decision_time, first_seen, extracted_at)
    row.timeline_bucket = format_yyyy_mm(row.sort_time or row.time_value)

    # ── Content shorts ────────────────────────────────────────
    rationale = node.get("rationale")
    context = node.get("context")
    scope = node.get("scope")

    row.rationale_short = truncate_text(rationale, 160) if rationale else "Missing rationale"
    row.context_short = truncate_text(context, 160) if context else "Missing context"
    row.scope_short = truncate_text(scope, 120) if scope else "Scope not specified"

    # ── Source ────────────────────────────────────────────────
    src_file = None
    src_start = None
    src_end = None
    if source:
        src_file = source.get("source_file") or node.get("source_file")
        src_start = source.get("line_start") or node.get("source_line_start")
        src_end = source.get("line_end") or node.get("source_line_end")
        row.source_heading = source.get("source_heading")
        row.source_confidence_label = format_source_confidence(source.get("source_confidence"))
    else:
        src_file = node.get("source_file")
        src_start = node.get("source_line_start")
        src_end = node.get("source_line_end")
        row.source_confidence_label = "Unverified"

    row.source_file = src_file or ""
    row.source_line_start = src_start
    row.source_line_end = src_end
    row.source_label = format_source_label(src_file, src_start, src_end)

    # ── Confidence ────────────────────────────────────────────
    row.confidence = node.get("confidence", 0.0)
    row.confidence_label = format_confidence_label(row.confidence)

    # ── Visibility ────────────────────────────────────────────
    edge_counts = edge_counts or {}
    row.display_priority = node.get("display_priority") or compute_display_priority(
        row.type, row.confidence, sum(edge_counts.values()),
    )
    evidence = (source.get("evidence_quote") if source else None) or node.get("evidence_quote", "")
    row.evidence_quote = evidence

    visible, hidden_reason = resolve_visibility(
        row.type, row.status, row.confidence, evidence, row.display_priority,
    )
    row.is_default_visible = visible
    row.hidden_reason = hidden_reason

    # ── Badges ────────────────────────────────────────────────
    row.badges = resolve_badges(
        row.status, row.time_confidence, row.classification_confidence,
        row.module, bool(row.rationale_short),
        source.get("source_confidence") if source else None,
    )

    # ── Related counts ────────────────────────────────────────
    row.related_counts = edge_counts

    # ── Detail (expand card) ──────────────────────────────────
    row.detail_context = node.get("context", "")
    row.detail_rationale = node.get("rationale", "")
    row.detail_scope = node.get("scope", "")
    row.detail_non_goals = node.get("non_goals", [])
    row.detail_evidence_quote = evidence
    row.detail_edges = edge_summaries or []

    row.schema_version = node.get("schema_version", "")
    row.is_legacy = node.get("is_legacy", False)

    return row


def _status_severity(status: str) -> str:
    from projmap.resolvers import STATUS_SEVERITY
    return STATUS_SEVERITY.get(status, "warning")


def build_table_viewmodel(
    rows: list[RowViewModel],
    include_hidden: bool = False,
    group_by: list[str] | None = None,
) -> dict:
    """Build a table ViewModel for renderers."""
    if not include_hidden:
        rows = [r for r in rows if r.is_default_visible]

    rows.sort(key=lambda r: r.sort_time or "", reverse=True)

    visible = len(rows)
    total = len(rows) + (0 if include_hidden else 0)

    return {
        "view_type": "decision_table",
        "title": "Active Decisions by Project / Version / Module",
        "generated_at": _now_iso(),
        "group_by": group_by or ["project", "version", "module"],
        "sort_by": ["sort_time_desc", "display_priority_desc"],
        "summary": {
            "visible_rows": visible,
        },
        "default_columns": [
            "time_display",
            "project_version_label",
            "module_label",
            "type_label",
            "title",
            "status_label",
            "source_label",
        ],
        "rows": [_row_to_dict(r) for r in rows],
    }


def _row_to_dict(r: RowViewModel) -> dict:
    d = {
        "node_id": r.node_id,
        "type": r.type,
        "type_label": r.type_label,
        "project": r.project,
        "version": r.version,
        "project_version_label": r.project_version_label,
        "module": r.module,
        "module_label": r.module_label,
        "submodule": r.submodule or "",
        "topic": r.topic,
        "title": r.title,
        "summary": r.summary,
        "status": r.status,
        "status_label": r.status_label,
        "status_severity": r.status_severity,
        "time_value": r.time_value,
        "time_label": r.time_label,
        "time_display": r.time_display,
        "time_basis": r.time_basis,
        "time_confidence": r.time_confidence,
        "time_confidence_label": r.time_confidence_label,
        "sort_time": r.sort_time,
        "timeline_bucket": r.timeline_bucket,
        "rationale_short": r.rationale_short,
        "context_short": r.context_short,
        "scope_short": r.scope_short,
        "source_label": r.source_label,
        "source_file": r.source_file,
        "source_heading": r.source_heading or "",
        "source_confidence_label": r.source_confidence_label,
        "confidence": r.confidence,
        "confidence_label": r.confidence_label,
        "classification_confidence": r.classification_confidence,
        "classification_confidence_label": r.classification_confidence_label,
        "display_priority": r.display_priority,
        "is_default_visible": r.is_default_visible,
        "hidden_reason": r.hidden_reason or "",
        "badges": r.badges,
        "related_counts": r.related_counts,
    }
    return d


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
