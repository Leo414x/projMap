"""Relation discovery evaluation: compare against ground truth."""

from __future__ import annotations

import json
from pathlib import Path

from projmap.config import load_config
from projmap.storage.duckdb_store import DuckDBStore


def eval_relations(project_root: str, ground_truth_path: str) -> dict:
    """Compare discovered edges against hand-labeled ground truth.

    Ground truth format: {"edges": [{"from_id": "...", "to_id": "...", "relation": "..."}, ...]}

    Returns: {true_positives, false_positives, false_negatives,
              precision, recall, f1, fp_details, fn_details}
    """
    try:
        cfg = load_config(project_root)
    except FileNotFoundError:
        return {"ok": False, "error": "Not initialized"}

    gt_path = Path(ground_truth_path)
    if not gt_path.exists():
        return {"ok": False, "error": f"Ground truth file not found: {gt_path}"}

    ground_truth = json.loads(gt_path.read_text())
    gt_edges = set()
    for e in ground_truth.get("edges", []):
        gt_edges.add((e["from_id"], e["to_id"], e["relation"]))

    store = DuckDBStore(cfg.db_path)
    rows = store.conn.execute(
        "SELECT from_node_id, to_node_id, relationship FROM edges WHERE source = ?",
        ["relation_discovery"],
    ).fetchall()
    store.close()

    discovered = {(r[0], r[1], r[2]) for r in rows}

    true_positives = gt_edges & discovered
    false_positives = discovered - gt_edges
    false_negatives = gt_edges - discovered

    tp = len(true_positives)
    fp = len(false_positives)
    fn = len(false_negatives)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "ok": True,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "ground_truth_count": len(gt_edges),
        "discovered_count": len(discovered),
        "fp_details": [{"from_id": e[0], "to_id": e[1], "relation": e[2]} for e in sorted(false_positives)],
        "fn_details": [{"from_id": e[0], "to_id": e[1], "relation": e[2]} for e in sorted(false_negatives)],
    }
