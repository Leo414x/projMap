"""Evidence builder: format evidence chains for display."""

from __future__ import annotations


def build_evidence(node: dict) -> dict:
    evidence_quote = node.get("evidence_quote", "")
    source_file = node.get("source_file", "")
    source_heading = node.get("source_heading") or node.get("source_line") or ""

    has_evidence = bool(evidence_quote and len(evidence_quote.strip()) > 5)
    source_label = source_file or "Source missing"
    if source_file and source_heading:
        source_label = f"{source_file} · {source_heading}"

    return {
        "has_evidence": has_evidence,
        "evidence_quote": evidence_quote.strip() if has_evidence else "",
        "source_label": source_label,
        "source_file": source_file,
    }
