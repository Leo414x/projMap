"""Markdown renderer: render brief and query results as markdown."""

from __future__ import annotations

from projmap.report.brief_builder import build_brief


def render_brief(brief: dict) -> str:
    """Render a ProjectBrief as markdown."""
    lines = []
    p = brief["project"]
    v = brief["version"]
    label = f"{p} / {v}" if v != "-" else p
    stats = brief["stats"]

    lines.append(f"# projMap Brief · {label}")
    lines.append(f"Nodes: {stats['total_nodes']} | "
                 f"Constraints: {stats['constraints']} | "
                 f"Decisions: {stats['decisions']} | "
                 f"Risks: {stats['risks']}")
    lines.append("")

    # 1. Current Status
    lines.append("## 1. Current Status")
    lines.append(f"**{brief['current_status']}**")
    cs = brief["sections"]["current_status"]
    if cs:
        ev = cs.get("evidence_quote_clean", "")
        if ev:
            lines.append(f'> "{ev}"')
        src = cs.get("source_file", "")
        if src:
            lines.append(f"Source: `{src}`")
    lines.append("")

    # 2. Do-not-cross Constraints
    constraints = brief["sections"]["do_not_cross_constraints"]
    if constraints:
        lines.append("## 2. Do-not-cross Constraints")
        for i, c in enumerate(constraints[:10], 1):
            title = c.get("display_title", c.get("content", "")[:60]).replace("|", "/")
            status = c.get("report_status", "active")
            src = f"`{c.get('source_file', '')}`" if c.get("source_file") else ""
            lines.append(f"{i}. **{title}** [{status}] — {src}")
            s = c.get("summary", "")
            if s:
                lines.append(f"   {s}")
        lines.append("")

    # 3. Key Decisions
    decisions = brief["sections"]["key_decisions"]
    if decisions:
        lines.append("## 3. Key Decisions")
        for i, d in enumerate(decisions[:10], 1):
            title = d.get("display_title", d.get("content", "")[:60]).replace("|", "/")
            status = d.get("report_status", "active")
            src = f"`{d.get('source_file', '')}`" if d.get("source_file") else ""
            lines.append(f"{i}. **{title}** [{status}] — {src}")
            s = d.get("summary", "")
            if s:
                lines.append(f"   {s}")
        lines.append("")

    # 4. Active Risks
    risks = brief["sections"]["active_risks"]
    if risks:
        lines.append("## 4. Active Risks")
        for i, r in enumerate(risks[:10], 1):
            title = r.get("display_title", r.get("content", "")[:60]).replace("|", "/")
            status = r.get("report_status", "active")
            src = f"`{r.get('source_file', '')}`" if r.get("source_file") else ""
            lines.append(f"{i}. **{title}** [{status}] — {src}")
            s = r.get("summary", "")
            if s:
                lines.append(f"   {s}")
        lines.append("")

    # 5. Evidence Sources
    sources = brief["evidence_sources"]
    if sources:
        lines.append("## 5. Evidence Sources")
        for s in sources:
            lines.append(f"- `{s}`")
        lines.append("")

    # 6. Related Groups
    grouped = brief["grouped"]
    if grouped:
        lines.append("## 6. Related Groups")
        for gid, gdata in grouped.items():
            glabel = gdata.get("label", gid) if isinstance(gdata, dict) else gid
            items = gdata.get("nodes", gdata) if isinstance(gdata, dict) else gdata
            count = len(items)
            top = items[0].get("display_title", "")[:60] if items else ""
            lines.append(f"- **{glabel}** ({count}) — {top}")
        lines.append("")

    # 7. Detailed Items
    all_nodes = [n for n in brief["all_nodes"]
                 if n.get("source_scope") != "agent_instruction"]
    if all_nodes:
        lines.append("## 7. Detailed Items")
        lines.append("| Priority | Project | Version | Type | Status | Title | Source |")
        lines.append("|---:|---|---|---|---|---|---|")
        for n in sorted(all_nodes, key=lambda x: x.get("priority_score", 0), reverse=True):
            pri = n.get("priority_score", 0)
            proj = n.get("project", "")
            ver = n.get("version", "")
            typ = n.get("type", "")
            stat = n.get("report_status", "")
            title = n.get("display_title", n.get("content", "")[:40]).replace("|", "/")[:60]
            src = n.get("source_file", "")
            lines.append(f"| {pri} | {proj} | {ver} | {typ} | {stat} | {title} | `{src}` |")
        lines.append("")

    return "\n".join(lines)


def render_query_results(
    nodes: list[dict],
    query: str,
    edge_counts: dict | None = None,
    enrichments: dict[str, dict] | None = None,
) -> str:
    """Render query results as a search-results page."""
    from projmap.report.brief_builder import enrich_node

    enriched = []
    for n in nodes:
        nid = n.get("id", "")
        llm = enrichments.get(nid) if enrichments else None
        enriched.append(enrich_node(n, edge_counts, llm_enrichment=llm))
    enriched.sort(key=lambda n: n.get("priority_score", 0), reverse=True)

    lines = []
    lines.append(f"# Query Results: {query or 'all'}")
    lines.append(f"Matched: {len(enriched)} items")
    lines.append("")

    # 1. Best Matches
    best = [n for n in enriched if n.get("has_evidence")][:5]
    if best:
        lines.append("## 1. Best Matches")
        for i, n in enumerate(best, 1):
            title = n.get("display_title", n.get("content", "")[:60])
            lines.append(f"### {i}. {title}")
            lines.append(f"**Type:** {n.get('type', '')} / **Status:** {n.get('report_status', '')}")
            lines.append(f"**Project:** {n.get('project', '')} / **Version:** {n.get('version', '')}")
            src = n.get("source_file", "")
            if src:
                lines.append(f"**Source:** `{src}`")
            s = n.get("summary", "")
            if s:
                lines.append(f"**Why it matters:** {s}")
            mr = n.get("match_reason", "")
            if mr:
                lines.append(f"**Match reason:** {mr}")
            ev = n.get("evidence_quote_clean", "")
            if ev:
                lines.append(f'> {ev}')
            lines.append("---")
        lines.append("")

    # 2. Related Groups
    from projmap.report.grouping import group_by_enrichment
    grouped = group_by_enrichment(enriched)

    if grouped:
        lines.append("## 2. Related Groups")
        for gid, gdata in grouped.items():
            glabel = gdata.get("label", gid) if isinstance(gdata, dict) else gid
            items = gdata.get("nodes", gdata) if isinstance(gdata, dict) else gdata
            top = items[0].get("display_title", "")[:60] if items else ""
            lines.append(f"- **{glabel}** ({len(items)}) — {top}")
        lines.append("")

    # 3. Detailed Matches
    if enriched:
        lines.append("## 3. Detailed Matches")
        lines.append("| Priority | Type | Status | Title | Project | Source |")
        lines.append("|---:|---|---|---|---|---|")
        for n in enriched:
            pri = n.get("priority_score", 0)
            typ = n.get("type", "")
            stat = n.get("report_status", "")
            title = n.get("display_title", n.get("content", "")[:40]).replace("|", "/")[:60]
            proj = n.get("project", "")
            src = f"`{n.get('source_file', '')}`" if n.get("source_file") else ""
            lines.append(f"| {pri} | {typ} | {stat} | {title} | {proj} | {src} |")
        lines.append("")

    return "\n".join(lines)
