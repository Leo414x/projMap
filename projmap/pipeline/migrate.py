"""Legacy node migration to v5 schema.

Moved from cli.py to reduce its size. The CLI migrate command delegates here.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from projmap.config import load_config
from projmap.storage.duckdb_store import DuckDBStore
from projmap.display.resolvers import (
    normalize_module, infer_module_from_path, infer_module_from_heading,
    resolve_project, resolve_version, resolve_classification,
    compute_display_priority, resolve_visibility,
)


def now_utc():
    return datetime.now(timezone.utc)


def _infer_module_from_content(content: str) -> str | None:
    c = (content or "").lower()
    mapping = [
        (["paper/shadow", "paper shadow", "paper-shadow", "paper_shadow", "shadow monitoring", "paper only"], "paper_shadow"),
        (["training window", "walk-forward", "walk forward", "lightgbm", "train", "training"], "training"),
        (["evaluation", "oos", "holdout", "metrics", "metric", "validation"], "evaluation"),
        (["labeling", "k horizon", "k mapping", "k ="], "labeling"),
        (["direction", "magnitude", "prediction", "atr", "prediction target"], "modeling"),
        (["decision flow", "consensus", "side monitoring", "tier 1", "tier 2", "tier 3", "signal gate"], "decision_flow"),
        (["risk", "risk allocation"], "risk"),
        (["same side", "cluster", "entry timing", "second entry"], "strategy_comparison"),
        (["cost reference", "2bp"], "paper_shadow"),
        (["section 8", "deploy", "deployment"], "decision_flow"),
        (["backtest", "strategy comparison"], "strategy_comparison"),
        (["feature", "feature engineering"], "feature_engineering"),
        (["data pipeline", "data pipeline"], "data_pipeline"),
        (["embargo"], "training"),
        (["projmap", "extraction", "external extraction"], "external_extraction"),
        (["spec", "document", "authoritative"], "decision_context"),
    ]
    for keywords, module in mapping:
        if any(kw in c for kw in keywords):
            return module
    return None


def _infer_status_from_content(content: str) -> str:
    c = (content or "").lower()
    if "paper/shadow" in c or "paper only" in c or "paper shadow" in c:
        return "paper_only"
    if "diagnostic" in c and "only" in c:
        return "diagnostic_only"
    if "no_go" in c or "not approved" in c:
        return "active"
    if "superseded" in c or "deprecated" in c:
        return "superseded"
    return "active"


def run_migration(dry_run: bool = True) -> dict:
    """Execute legacy migration. Returns stats dict."""
    cfg = load_config(".")
    store = DuckDBStore(cfg.db_path)
    nodes = store.get_all_nodes_as_dicts()

    migrated = 0
    already_v5 = 0
    missing_source = 0
    missing_evidence = 0

    for n in nodes:
        if n.get("schema_version") == "v5":
            already_v5 += 1
            continue

        has_evidence = bool(n.get("evidence_quote"))
        has_source = bool(n.get("source_file"))
        if not has_source:
            missing_source += 1
        if not has_evidence:
            missing_evidence += 1

        content = n.get("content") or ""
        source_file = n.get("source_file") or ""
        source_heading = n.get("source_heading") or n.get("source_line") or ""
        evidence = n.get("evidence_quote") or ""

        # Title: build the best title from available data
        existing_title = n.get("title") or n.get("summary") or ""
        ev_clean = evidence.strip().split("\n")[0].strip().rstrip(".,;:") if evidence else ""

        if existing_title and len(existing_title) > 40:
            title = existing_title
        elif len(ev_clean) > 30 and ev_clean[0].isupper():
            title = ev_clean
        elif content and len(content) > len(ev_clean):
            title = content
        elif ev_clean:
            title = ev_clean
        else:
            title = content or "Untitled memory"

        if len(title) > 200:
            title = title[:197] + "..."

        summary = n.get("summary") or content or title

        # Infer project from source path
        if "v13" in source_file.lower() or "spy" in source_file.lower():
            project = "Trading System"
        elif "projmap" in source_file.lower() or "projmap" in content.lower():
            project = "projMap"
        elif "CLAUDE_CODE_PROMPT" in source_file or ".agents/skills" in source_file:
            project = "projMap"
        else:
            project = "Trading System"

        # Infer version from content and source path
        v_match = re.search(
            r"(?:^|[_./\-\s])([Vv]\d+(?:\.\d+)*)(?:[_./\-\s]|$)",
            content + " " + source_file,
        )
        version = v_match.group(1).upper() if v_match else "-"

        # Infer module from content keywords + source path
        classification = resolve_classification(
            project_hint=project,
            version_hint=version if version != "-" else None,
            module_hint=_infer_module_from_content(content),
            text=content,
            source_path=source_file,
            source_heading=source_heading,
        )

        status = _infer_status_from_content(content)

        ts = now_utc()
        ts_str = str(ts)

        evidence = n.get("evidence_quote", "")
        confidence = n.get("confidence", 0.5)
        priority = compute_display_priority(n.get("type", "decision"), confidence, 0)
        visible, hidden_reason = resolve_visibility(
            n.get("type", "decision"), status, confidence, evidence, priority,
        )

        if not dry_run:
            store.conn.execute(
                """UPDATE nodes SET
                    title = ?,
                    summary = ?,
                    schema_version = 'v5',
                    project = ?,
                    version = ?,
                    module = ?,
                    submodule = '',
                    topic = '',
                    status = ?,
                    classification_confidence = ?,
                    classification_basis = ?,
                    display_priority = ?,
                    is_default_visible = ?,
                    hidden_reason = ?,
                    decision_time_basis = 'extraction_time',
                    decision_time_confidence = 0.2,
                    sort_time = COALESCE(sort_time, ?),
                    first_seen_at = COALESCE(first_seen_at, ?),
                    last_seen_at = COALESCE(last_seen_at, ?),
                    extracted_at = COALESCE(extracted_at, ?)
                WHERE id = ?""",
                [
                    title[:300], summary[:500],
                    project, version,
                    classification["module"],
                    status,
                    classification["classification_confidence"],
                    classification["classification_basis"],
                    priority,
                    visible,
                    hidden_reason or "",
                    ts_str, ts_str, ts_str, ts_str,
                    n["id"],
                ],
            )

        migrated += 1

    store.close()

    return {
        "ok": True,
        "dry_run": dry_run,
        "nodes_scanned": len(nodes),
        "already_v5": already_v5,
        "can_migrate": migrated,
        "missing_source": missing_source,
        "missing_evidence": missing_evidence,
    }
