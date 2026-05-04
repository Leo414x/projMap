"""External extraction pipeline: prepare tasks, import results.

Scan, chunk, and generate extraction task files for an external LLM,
then read result files back, validate, and write to DuckDB.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from projmap.config import load_config
from projmap.ingestion.scanner import scan_files
from projmap.ingestion.chunker import chunk_text
from projmap.schemas import (
    ExtractionResult,
    edge_id,
    node_id,
    normalize_content,
    file_hash,
)
from projmap.storage.cache import FileHashCache
from projmap.storage.duckdb_store import DuckDBStore


# ── Constants ────────────────────────────────────────────────────────

TASK_DIR = "extraction_tasks"
RESULT_DIR = "extraction_results"
SCHEMA_VERSION = "external_extraction_v1"

NODE_TYPES = [
    "decision", "risk", "assumption", "version", "constraint",
    "config", "evaluation_result", "process_rule", "open_question",
]
EDGE_TYPES = [
    "depends-on", "conflicts-with", "supersedes", "traces-back-to",
    "mitigates", "implements", "affects", "supports", "limits",
]

EXTRACTION_RULES = [
    "Extract project memory: decisions, constraints, risks, assumptions, configs, evaluation results from this chunk.",
    "A decision is when a specific choice was made (approved, frozen, deprecated, selected a value/architecture/threshold). Do NOT extract plain facts or descriptions as decisions.",
    "A constraint is a rule that must not be violated (e.g., 'do not X', 'must Y', 'V13 must not reuse prior model code').",
    "A risk is an identified danger or uncertainty (e.g., 'holdout returned NO_GO', 'may have blind spots').",
    "Every node must include `evidence_quote`: an exact quote from the chunk that supports the extraction.",
    "Every node must include `content`: a complete self-contained sentence. BAD: 'K mapping'. GOOD: 'V13 uses K horizons of 3, 6, and 8 bars for prediction targets.'",
    "Every node must include `title`: a short label (under 60 chars) that summarizes the node. E.g., 'K mapping', 'Training window', 'Deployment status'.",
    "For `decision` type nodes, also include: `context` (background), `rationale` (why), `scope` (what it covers), `status_hint` (active/paper_only/diagnostic_only/superseded).",
    "For `decision` type nodes, include: `project_hint` (e.g., 'Trading System'), `version_hint` (e.g., 'V13'), `module_hint` (e.g., 'training', 'evaluation', 'decision_flow').",
    "Do not invent IDs. The system generates them.",
    "If a chunk genuinely has no project memory, return empty arrays. But most technical document chunks contain at least 1-3 extractable items.",
    "Example output for a decision node:",
    '  {"type":"decision","title":"K mapping","content":"V13 uses K horizons of 3, 6, and 8 bars.","evidence_quote":"K = {3, 6, 8}","confidence":0.85,"status_hint":"active","module_hint":"labeling"}',
]


# ── Helpers ──────────────────────────────────────────────────────────

def _ok(**kwargs) -> dict:
    result = {"ok": True, "warnings": [], "errors": []}
    result.update(kwargs)
    return result


def _err(error_code: str, message: str, **kwargs) -> dict:
    result = {"ok": False, "error_code": error_code, "message": message,
              "warnings": [], "errors": []}
    result.update(kwargs)
    return result


def _resolve_edge_node(content: str, chunk_lookup: dict[str, str]) -> str | None:
    norm = normalize_content(content)
    return chunk_lookup.get(norm)


# ── Prepare ──────────────────────────────────────────────────────────

def prepare_extraction(
    project_root: str = ".",
    force: bool = False,
    limit: int | None = None,
    clear: bool = True,
) -> dict:
    """Scan, chunk, and generate extraction task files for external LLM."""
    try:
        cfg = load_config(project_root)
    except FileNotFoundError:
        return _err("NOT_INITIALIZED", "No .projmap/config.toml found. Run `projmap init` first.")

    root = Path(cfg.root).resolve()
    task_dir = root / ".projmap" / TASK_DIR
    result_dir = root / ".projmap" / RESULT_DIR

    # Clear old tasks/results
    if clear:
        if task_dir.exists():
            for f in task_dir.iterdir():
                f.unlink()
        if result_dir.exists():
            for f in result_dir.iterdir():
                f.unlink()

    task_dir.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)

    # Scan
    try:
        store = DuckDBStore(cfg.db_path)
        cache = FileHashCache(root / cfg.cache_dir)
        known = {**store.get_all_file_hashes(), **cache.as_dict()}
        records = scan_files(cfg, known)
        store.close()
    except Exception as exc:
        return _err("DATABASE_ERROR", str(exc))

    if force:
        records_changed = records
    else:
        records_changed = [r for r in records if r.status in ("new", "changed")]

    # Chunk and generate tasks
    tasks = []
    chunks_created = 0

    for frec in records_changed:
        chunks = chunk_text(
            frec.content, frec.path,
            max_chars=cfg.max_chars,
            overlap_chars=cfg.overlap_chars,
        )
        chunks_created += len(chunks)

        for chunk in chunks:
            task_num = len(tasks) + 1
            task_id = f"task_{task_num:06d}"

            tasks.append({
                "task_id": task_id,
                "task_path": f".projmap/{TASK_DIR}/{task_id}.json",
                "result_path": f".projmap/{RESULT_DIR}/{task_id}.result.json",
                "chunk_id": chunk.id,
                "file_path": chunk.file_path,
                "chunk_index": chunk.chunk_index,
                "heading_path": chunk.heading_path,
                "semantic_anchor": chunk.semantic_anchor,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "content_hash": chunk.content_hash,
            })

            # Write task file
            task_file = {
                "schema_version": SCHEMA_VERSION,
                "task_id": task_id,
                "chunk_id": chunk.id,
                "file_path": chunk.file_path,
                "chunk_index": chunk.chunk_index,
                "heading_path": chunk.heading_path,
                "semantic_anchor": chunk.semantic_anchor,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "content_hash": chunk.content_hash,
                "instructions": {
                    "node_types": NODE_TYPES,
                    "edge_types": EDGE_TYPES,
                    "rules": EXTRACTION_RULES,
                },
                "content": chunk.content,
            }
            (task_dir / f"{task_id}.json").write_text(
                json.dumps(task_file, ensure_ascii=False, indent=2)
            )

            if limit is not None and len(tasks) >= limit:
                break
        if limit is not None and len(tasks) >= limit:
            break

    # Write manifest
    from datetime import datetime, timezone
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "project_name": cfg.project_name,
        "project_root": str(root),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "external",
        "task_count": len(tasks),
        "tasks": tasks,
    }
    manifest_path = task_dir / "task_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    return _ok(
        mode="external",
        project_root=str(root),
        scanned_files=len(records),
        new_files=sum(1 for r in records if r.status == "new"),
        changed_files=sum(1 for r in records if r.status == "changed"),
        unchanged_files=sum(1 for r in records if r.status == "unchanged"),
        chunks_created=chunks_created,
        tasks_created=len(tasks),
        task_dir=f".projmap/{TASK_DIR}",
        result_dir=f".projmap/{RESULT_DIR}",
        manifest_path=f".projmap/{TASK_DIR}/task_manifest.json",
    )


# ── Import ───────────────────────────────────────────────────────────

def import_extraction(
    project_root: str = ".",
    strict_evidence: bool | None = None,
    allow_partial: bool = True,
    min_confidence: float = 0.55,
) -> dict:
    """Read result files from external LLM, validate, and write to DuckDB."""
    try:
        cfg = load_config(project_root)
    except FileNotFoundError:
        return _err("NOT_INITIALIZED", "No .projmap/config.toml found. Run `projmap init` first.")

    if strict_evidence is None:
        strict_evidence = cfg.strict_evidence

    root = Path(cfg.root).resolve()
    task_dir = root / ".projmap" / TASK_DIR
    result_dir = root / ".projmap" / RESULT_DIR
    manifest_path = task_dir / "task_manifest.json"

    if not manifest_path.exists():
        return _err("TASK_MANIFEST_NOT_FOUND",
                     f"Manifest not found at .projmap/{TASK_DIR}/task_manifest.json. "
                     "Run `projmap prepare-extraction` first.")

    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != SCHEMA_VERSION:
        return _err("RESULT_SCHEMA_INVALID",
                     f"Unexpected manifest schema_version: {manifest.get('schema_version')}")

    # Build task lookup: task_id -> task info + chunk content
    task_lookup: dict[str, dict] = {}
    for t in manifest.get("tasks", []):
        tid = t["task_id"]
        task_file_path = task_dir / f"{tid}.json"
        if not task_file_path.exists():
            continue
        task_data = json.loads(task_file_path.read_text())
        task_lookup[tid] = {**t, "_content": task_data.get("content", "")}

    if not task_lookup:
        return _err("NO_TASKS_TO_IMPORT", "No task files found.")

    # Process results
    results_imported = 0
    results_failed = 0
    nodes_inserted = 0
    nodes_skipped_duplicate = 0
    nodes_skipped_low_confidence = 0
    edges_inserted = 0
    edges_dropped_unresolved = 0
    edges_skipped_low_confidence = 0
    evidence_failures = 0
    warnings: list[str] = []

    try:
        store = DuckDBStore(cfg.db_path)
    except Exception as exc:
        return _err("DATABASE_ERROR", str(exc))

    # Track nodes per file for edge resolution
    file_node_lookups: dict[str, dict[str, str]] = {}

    for t in manifest.get("tasks", []):
        tid = t["task_id"]
        chunk_id = t["chunk_id"]
        file_path = t["file_path"]

        if tid not in task_lookup:
            continue

        task_info = task_lookup[tid]
        chunk_content = task_info["_content"]

        result_path = result_dir / f"{tid}.result.json"
        if not result_path.exists():
            results_failed += 1
            warnings.append(f"Result file missing for {tid}")
            continue

        # Read and parse result
        try:
            result_data = json.loads(result_path.read_text())
        except json.JSONDecodeError as exc:
            results_failed += 1
            ext_id = str(uuid.uuid4())
            store.insert_extraction(ext_id, chunk_id, file_path, "external",
                                    result_path.read_text(), None,
                                    "json_parse_failed", str(exc))
            warnings.append(f"{tid}: JSON parse error")
            continue

        # Validate basic structure
        if result_data.get("schema_version") != SCHEMA_VERSION:
            results_failed += 1
            warnings.append(f"{tid}: schema_version mismatch")
            continue

        # Validate task_id / chunk_id / file_path match
        if (result_data.get("task_id") != tid or
                result_data.get("chunk_id") != chunk_id or
                result_data.get("file_path") != file_path):
            results_failed += 1
            ext_id = str(uuid.uuid4())
            store.insert_extraction(ext_id, chunk_id, file_path, "external",
                                    json.dumps(result_data), None,
                                    "task_mismatch",
                                    f"task_id/chunk_id/file_path mismatch")
            warnings.append(f"{tid}: task_id/chunk_id/file_path mismatch")
            continue

        # Pydantic validate
        try:
            extraction = ExtractionResult(
                nodes=result_data.get("nodes", []),
                edges=result_data.get("edges", []),
            )
        except Exception as exc:
            results_failed += 1
            ext_id = str(uuid.uuid4())
            store.insert_extraction(ext_id, chunk_id, file_path, "external",
                                    json.dumps(result_data), None,
                                    "validation_failed", str(exc))
            warnings.append(f"{tid}: validation failed — {exc}")
            continue

        # Insert nodes
        node_lookup: dict[str, str] = {}
        for n in extraction.nodes:
            # Confidence filter
            if n.confidence < min_confidence:
                nodes_skipped_low_confidence += 1
                continue

            # Evidence check
            if strict_evidence and n.evidence_quote not in chunk_content:
                evidence_failures += 1
                continue

            nid = node_id(n.type, n.content)
            norm = normalize_content(n.content)
            node_lookup[norm] = nid

            inserted = store.insert_node(
                nid, n.type, n.content, n.detail or "",
                file_path, chunk_id, n.source_line,
                n.evidence_quote, n.confidence,
                file_hash(n.content),
            )
            if inserted:
                nodes_inserted += 1
            else:
                nodes_skipped_duplicate += 1

        # Track for cross-chunk edge resolution
        if file_path not in file_node_lookups:
            file_node_lookups[file_path] = {}
        file_node_lookups[file_path].update(node_lookup)

        # Insert edges
        for edge in extraction.edges:
            if edge.confidence < min_confidence:
                edges_skipped_low_confidence += 1
                continue

            if strict_evidence and edge.evidence_quote not in chunk_content:
                evidence_failures += 1
                continue

            from_nid = _resolve_edge_node(edge.from_content, node_lookup)
            to_nid = _resolve_edge_node(edge.to_content, node_lookup)
            if not from_nid or not to_nid:
                edges_dropped_unresolved += 1
                continue
            eid = edge_id(from_nid, to_nid, edge.relationship)
            store.insert_edge(
                eid, from_nid, to_nid, edge.relationship,
                edge.evidence_quote, edge.confidence,
                file_path, chunk_id,
            )
            edges_inserted += 1

        # Record successful extraction
        raw = json.dumps(result_data, ensure_ascii=False)
        ext_id = str(uuid.uuid4())
        store.insert_extraction(ext_id, chunk_id, file_path, "external",
                                raw, raw, "success", None)
        results_imported += 1

        # Update file record
        store.upsert_file(file_path, "", task_info.get("content_hash", ""),
                          0, None, "changed", extracted=True)

    store.close()

    if results_failed > 0 and not allow_partial:
        return _err("IMPORT_PARTIAL_FAILURE",
                     f"{results_failed} results failed",
                     tasks_total=manifest.get("task_count", 0),
                     result_files_found=results_imported + results_failed,
                     results_imported=results_imported,
                     results_failed=results_failed,
                     warnings=warnings)

    ok = True
    if results_failed > 0:
        ok = True  # allow_partial
        warnings.insert(0, f"{results_failed} result files failed validation")
    if edges_dropped_unresolved > 0:
        warnings.append(f"{edges_dropped_unresolved} edges dropped because node references could not be resolved")

    return _ok(
        mode="external",
        strict_evidence=strict_evidence,
        tasks_total=manifest.get("task_count", 0),
        result_files_found=results_imported + results_failed,
        results_imported=results_imported,
        results_failed=results_failed,
        nodes_inserted=nodes_inserted,
        nodes_skipped_duplicate=nodes_skipped_duplicate,
        nodes_skipped_low_confidence=nodes_skipped_low_confidence,
        edges_inserted=edges_inserted,
        edges_dropped_unresolved=edges_dropped_unresolved,
        edges_skipped_low_confidence=edges_skipped_low_confidence,
        evidence_failures=evidence_failures,
        warnings=warnings,
    )
