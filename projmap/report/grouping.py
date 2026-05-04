"""Grouping: cluster related nodes by LLM-assigned groups."""

from __future__ import annotations


def group_by_enrichment(
    nodes: list[dict],
    group_key: str = "group",
    label_key: str = "group_label",
) -> dict[str, dict]:
    """Group enriched nodes by their LLM-assigned group.

    Returns {group_id: {"label": str, "nodes": list[dict]}}.
    """
    groups: dict[str, dict] = {}
    for n in nodes:
        gid = n.get(group_key, "other")
        if gid not in groups:
            groups[gid] = {
                "label": n.get(label_key, gid.replace("_", " ").title()),
                "nodes": [],
            }
        groups[gid]["nodes"].append(n)

    for gid in groups:
        groups[gid]["nodes"].sort(
            key=lambda x: x.get("priority_score", 0), reverse=True
        )

    return groups
