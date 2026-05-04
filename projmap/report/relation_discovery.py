"""Cross-file relation discovery via LLM.

Supports API mode (direct LLM call) and external agent mode (task files).
Incremental mode skips clusters where all nodes already have discovery edges.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from projmap.config import load_config
from projmap.prompts import load as load_prompt, split_prompt_sections
from projmap.schemas import edge_id
from projmap.storage.duckdb_store import DuckDBStore
from projmap.util import _ok, _err

RELATION_TASK_DIR = "relation_tasks"
RELATION_RESULT_DIR = "relation_results"
SCHEMA_VERSION = "relation_discovery_v1"


# ── Clustering ────────────────────────────────────────────────────

def cluster_candidates(
    nodes: list[dict],
    existing_edge_node_ids: set[str] | None = None,
    max_cluster_size: int = 20,
) -> list[list[dict]]:
    """Group nodes by (type, project, module), cap cluster size.

    In incremental mode, skip clusters where all node IDs already appear
    in existing_edge_node_ids.
    """
    groups: dict[str, list[dict]] = {}
    for n in nodes:
        key = f"{n.get('type', '')}|{n.get('project', '')}|{n.get('module', '')}"
        groups.setdefault(key, []).append(n)

    clusters: list[list[dict]] = []
    for key, group in sorted(groups.items(), key=lambda x: -len(x[1])):
        # Sort by version descending so newer nodes come first
        group.sort(key=lambda n: n.get("version", "") or "", reverse=True)

        if existing_edge_node_ids is not None:
            node_ids = {n.get("id", "") for n in group}
            if node_ids and node_ids.issubset(existing_edge_node_ids):
                continue

        # Cap cluster size
        for i in range(0, len(group), max_cluster_size):
            cluster = group[i:i + max_cluster_size]
            clusters.append(cluster)

    return clusters


def _serialize_cluster_for_llm(cluster: list[dict]) -> list[dict]:
    """Serialize cluster nodes for LLM input."""
    return [
        {
            "id": n.get("id", ""),
            "type": n.get("type", ""),
            "content": n.get("content", ""),
            "title": n.get("title", ""),
            "summary": n.get("summary", ""),
            "version": n.get("version", ""),
            "module": n.get("module", ""),
            "project": n.get("project", ""),
            "evidence_quote": n.get("evidence_quote", ""),
            "source_file": n.get("source_file", ""),
        }
        for n in cluster
    ]


def _parse_edges_response(raw: str, valid_ids: set[str], min_confidence: float) -> list[dict]:
    """Parse LLM relation discovery response, validate IDs, filter confidence."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines[1:] if not l.strip().startswith("```")]
        text = "\n".join(lines)

    parsed = json.loads(text)
    edges_raw = parsed.get("edges", []) if isinstance(parsed, dict) else []

    edges = []
    for e in edges_raw:
        source_id = e.get("source_id", "")
        target_id = e.get("target_id", "")
        if source_id == target_id:
            continue
        if source_id not in valid_ids or target_id not in valid_ids:
            continue
        confidence = float(e.get("confidence", 0.0))
        if confidence < min_confidence:
            continue
        edges.append({
            "source_id": source_id,
            "target_id": target_id,
            "relation": e.get("relation", ""),
            "evidence": e.get("evidence", ""),
            "confidence": confidence,
        })
    return edges


# ── API mode ──────────────────────────────────────────────────────

def discover_relations_api(
    cluster: list[dict],
    model: str = "claude-sonnet-4-20250514",
    api_key_env: str = "ANTHROPIC_API_KEY",
    min_confidence: float = 0.6,
) -> list[dict]:
    """Call LLM to discover relations within a cluster."""
    import anthropic

    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        raise SystemExit(f"Missing {api_key_env}.")

    pack = load_prompt(purpose="relation_discovery")
    system, user_template = split_prompt_sections(pack.prompt_text)

    serialized = _serialize_cluster_for_llm(cluster)
    nodes_json = json.dumps(serialized, ensure_ascii=False, indent=2)
    user = user_template.format(count=len(serialized), nodes_json=nodes_json)

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=0.0,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    valid_ids = {n.get("id", "") for n in cluster}
    return _parse_edges_response(message.content[0].text, valid_ids, min_confidence)


def run_relation_discovery(
    project_root: str = ".",
    model: str = "claude-sonnet-4-20250514",
    api_key_env: str = "ANTHROPIC_API_KEY",
    min_confidence: float = 0.6,
    incremental: bool = True,
) -> dict:
    """Full pipeline: read nodes → cluster → discover → write edges to DuckDB."""
    try:
        cfg = load_config(project_root)
    except FileNotFoundError:
        return _err("NOT_INITIALIZED", "No .projmap/config.toml found.")

    try:
        store = DuckDBStore(cfg.db_path)
    except Exception as exc:
        return _err("DATABASE_ERROR", str(exc))

    nodes = store.get_all_nodes_as_dicts()
    if not nodes:
        store.close()
        return _ok(clusters_processed=0, edges_discovered=0, edges_inserted=0,
                    edges_skipped_low_confidence=0, edges_dropped_unresolved=0)

    existing_ids = None
    if incremental:
        existing_ids = store.get_node_ids_with_edges(source_filter="relation_discovery")

    clusters = cluster_candidates(nodes, existing_edge_node_ids=existing_ids)
    if not clusters:
        store.close()
        return _ok(clusters_processed=0, edges_discovered=0, edges_inserted=0,
                    edges_skipped_low_confidence=0, edges_dropped_unresolved=0,
                    skipped_incremental=len(existing_ids) if existing_ids else 0)

    # Build node lookup for edge ID computation
    node_lookup = {}
    for n in nodes:
        node_lookup[n.get("id", "")] = n

    edges_discovered = 0
    edges_inserted = 0
    edges_dropped_unresolved = 0

    try:
        store.begin()
        for cluster in clusters:
            try:
                discovered = discover_relations_api(
                    cluster, model=model, api_key_env=api_key_env,
                    min_confidence=min_confidence,
                )
            except Exception:
                continue

            edges_discovered += len(discovered)
            for e in discovered:
                from_nid = e["source_id"]
                to_nid = e["target_id"]
                if from_nid not in node_lookup or to_nid not in node_lookup:
                    edges_dropped_unresolved += 1
                    continue

                eid = edge_id(from_nid, to_nid, e["relation"])
                store.insert_edge(
                    eid, from_nid, to_nid, e["relation"],
                    e["evidence"], e["confidence"],
                    node_lookup[from_nid].get("source_file", ""),
                    "", source="relation_discovery",
                )
                edges_inserted += 1

        store.commit()
    except Exception:
        store.rollback()
        store.close()
        raise

    store.close()
    return _ok(
        clusters_processed=len(clusters),
        edges_discovered=edges_discovered,
        edges_inserted=edges_inserted,
        edges_dropped_unresolved=edges_dropped_unresolved,
        incremental=incremental,
    )


# ── External mode: prepare / import ───────────────────────────────

def prepare_relation_tasks(
    project_root: str = ".",
    incremental: bool = True,
) -> dict:
    """Write task JSONs + prompt for external LLM relation discovery."""
    try:
        cfg = load_config(project_root)
    except FileNotFoundError:
        return _err("NOT_INITIALIZED", "No .projmap/config.toml found.")

    root = Path(cfg.root).resolve()
    task_dir = root / ".projmap" / RELATION_TASK_DIR
    result_dir = root / ".projmap" / RELATION_RESULT_DIR

    if task_dir.exists():
        for f in task_dir.iterdir():
            f.unlink()
    if result_dir.exists():
        for f in result_dir.iterdir():
            f.unlink()

    task_dir.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)

    try:
        store = DuckDBStore(cfg.db_path)
    except Exception as exc:
        return _err("DATABASE_ERROR", str(exc))

    nodes = store.get_all_nodes_as_dicts()

    existing_ids = None
    if incremental:
        existing_ids = store.get_node_ids_with_edges(source_filter="relation_discovery")

    store.close()

    clusters = cluster_candidates(nodes, existing_edge_node_ids=existing_ids)

    # Write prompt from registry
    prompt_pack = load_prompt(purpose="relation_discovery")
    (task_dir / "prompt.md").write_text(prompt_pack.prompt_text, encoding="utf-8")

    tasks = []
    for i, cluster in enumerate(clusters):
        task_id = f"relation_task_{i + 1:04d}"
        serialized = _serialize_cluster_for_llm(cluster)
        node_ids = [n.get("id", "") for n in cluster]

        task_data = {
            "schema_version": SCHEMA_VERSION,
            "task_id": task_id,
            "cluster_index": i,
            "node_ids": node_ids,
            "nodes": serialized,
        }
        (task_dir / f"{task_id}.json").write_text(
            json.dumps(task_data, ensure_ascii=False, indent=2)
        )
        tasks.append({
            "task_id": task_id,
            "task_path": f".projmap/{RELATION_TASK_DIR}/{task_id}.json",
            "result_path": f".projmap/{RELATION_RESULT_DIR}/{task_id}.result.json",
            "node_count": len(serialized),
        })

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "prompt_version": prompt_pack.version,
        "prompt_path": f".projmap/{RELATION_TASK_DIR}/prompt.md",
        "project_name": cfg.project_name,
        "project_root": str(root),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "external_relation",
        "task_count": len(tasks),
        "total_nodes": len(nodes),
        "tasks": tasks,
    }
    (task_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2)
    )

    return _ok(
        tasks_created=len(tasks),
        total_nodes=len(nodes),
        task_dir=f".projmap/{RELATION_TASK_DIR}",
        result_dir=f".projmap/{RELATION_RESULT_DIR}",
        manifest_path=f".projmap/{RELATION_TASK_DIR}/manifest.json",
    )


def import_relation_results(
    project_root: str = ".",
    min_confidence: float = 0.6,
) -> dict:
    """Read external relation discovery results and write edges to DuckDB."""
    try:
        cfg = load_config(project_root)
    except FileNotFoundError:
        return _err("NOT_INITIALIZED", "No .projmap/config.toml found.")

    root = Path(cfg.root).resolve()
    task_dir = root / ".projmap" / RELATION_TASK_DIR
    result_dir = root / ".projmap" / RELATION_RESULT_DIR
    manifest_path = task_dir / "manifest.json"

    if not manifest_path.exists():
        return _err("MANIFEST_NOT_FOUND",
                     f"Manifest not found at .projmap/{RELATION_TASK_DIR}/manifest.json")

    manifest = json.loads(manifest_path.read_text())

    try:
        store = DuckDBStore(cfg.db_path)
    except Exception as exc:
        return _err("DATABASE_ERROR", str(exc))

    # Build node lookup
    all_nodes = store.get_all_nodes_as_dicts()
    node_lookup = {n.get("id", ""): n for n in all_nodes}

    results_imported = 0
    results_failed = 0
    edges_inserted = 0
    edges_dropped_unresolved = 0
    warnings: list[str] = []

    for task in manifest.get("tasks", []):
        tid = task["task_id"]
        result_path = result_dir / f"{tid}.result.json"
        if not result_path.exists():
            results_failed += 1
            continue

        try:
            result_data = json.loads(result_path.read_text())
            node_ids = set(task.get("node_ids", []))
            edges = _parse_edges_response(
                json.dumps(result_data), node_ids, min_confidence,
            )

            for e in edges:
                from_nid = e["source_id"]
                to_nid = e["target_id"]
                if from_nid not in node_lookup or to_nid not in node_lookup:
                    edges_dropped_unresolved += 1
                    continue

                eid = edge_id(from_nid, to_nid, e["relation"])
                store.insert_edge(
                    eid, from_nid, to_nid, e["relation"],
                    e["evidence"], e["confidence"],
                    node_lookup[from_nid].get("source_file", ""),
                    "", source="relation_discovery",
                )
                edges_inserted += 1

            results_imported += 1
        except Exception as exc:
            results_failed += 1
            warnings.append(f"{tid}: {exc}")

    store.close()

    return _ok(
        results_imported=results_imported,
        results_failed=results_failed,
        edges_inserted=edges_inserted,
        edges_dropped_unresolved=edges_dropped_unresolved,
        warnings=warnings,
    )
