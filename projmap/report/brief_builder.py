"""Brief builder: transform raw nodes into a structured project brief.

LLM enrichment is required. No fallback heuristics.
"""

from __future__ import annotations

from collections import Counter

from projmap.report.source_resolver import resolve_source_project
from projmap.report.grouping import group_by_enrichment
from projmap.report.evidence_builder import build_evidence


def enrich_node(n: dict, edge_counts: dict[str, dict] | None = None,
                llm_enrichment: dict | None = None) -> dict:
    """Add report-layer fields to a raw node dict. Requires LLM enrichment."""
    source_file = n.get("source_file", "")
    node_id = n.get("id", "")

    src_info = resolve_source_project(source_file, n.get("content", ""))
    project = n.get("project") or src_info["project"]
    version = n.get("version") or src_info["version"]

    ev = build_evidence(n)

    edges = edge_counts or {}
    node_edges = edges.get(node_id, {})

    display_title = llm_enrichment.get("display_title", "")
    report_status = llm_enrichment.get("report_status", "")
    priority_score = llm_enrichment.get("priority_score", 0.0)
    group = llm_enrichment.get("group", "")
    group_label = llm_enrichment.get("group_label", "")
    summary = llm_enrichment.get("summary", "")
    match_reason = llm_enrichment.get("match_reason", "")

    return {
        **n,
        "project": project,
        "version": version,
        "source_scope": src_info["source_scope"],
        "report_status": report_status,
        "priority_score": priority_score,
        "display_title": display_title,
        "group": group,
        "group_label": group_label,
        "summary": summary,
        "match_reason": match_reason,
        "has_evidence": ev["has_evidence"],
        "evidence_quote_clean": ev["evidence_quote"],
        "source_label": ev["source_label"],
    }


def build_brief(
    nodes: list[dict],
    edge_counts: dict[str, dict] | None = None,
    project_hint: str | None = None,
    enrichments: dict[str, dict] | None = None,
    llm_status: dict | None = None,
) -> dict:
    """Build a ProjectBrief from raw node dicts. Requires LLM enrichments."""
    enriched = []
    for n in nodes:
        nid = n.get("id", "")
        llm = enrichments.get(nid) if enrichments else None
        enriched.append(enrich_node(n, edge_counts, llm_enrichment=llm))

    project_nodes = [n for n in enriched if n["source_scope"] != "agent_instruction"]
    agent_nodes = [n for n in enriched if n["source_scope"] == "agent_instruction"]

    project_counts = Counter(n["project"] for n in project_nodes)
    dominant_project = project_counts.most_common(1)[0][0] if project_nodes else "Unknown"
    version_counts = Counter(n["version"] for n in project_nodes if n["version"] != "-")
    dominant_version = version_counts.most_common(1)[0][0] if version_counts else "-"

    project_nodes.sort(
        key=lambda n: n["priority_score"],
        reverse=True,
    )

    constraints = [n for n in project_nodes if n["type"] == "constraint"]
    decisions = [n for n in project_nodes if n["type"] == "decision"]
    risks = [n for n in project_nodes if n["type"] == "risk"]

    current_status_node = project_nodes[0] if project_nodes else None
    current_status_text = ""
    if llm_status:
        current_status_text = llm_status.get("current_status", "")
    if not current_status_text and current_status_node:
        current_status_text = current_status_node.get("display_title", "Status unknown")

    sources = sorted(set(n["source_file"] for n in project_nodes if n.get("source_file")))
    grouped = group_by_enrichment(project_nodes)

    return {
        "project": project_hint or dominant_project,
        "version": dominant_version,
        "current_status": current_status_text,
        "sections": {
            "current_status": current_status_node,
            "do_not_cross_constraints": constraints,
            "key_decisions": decisions,
            "active_risks": risks,
        },
        "grouped": grouped,
        "evidence_sources": sources,
        "all_nodes": enriched,
        "stats": {
            "total_nodes": len(nodes),
            "project_nodes": len(project_nodes),
            "agent_instruction_nodes": len(agent_nodes),
            "constraints": len(constraints),
            "decisions": len(decisions),
            "risks": len(risks),
        },
    }
