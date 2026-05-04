"""Stable internal API for CLI / agents / future MCP.

All functions return JSON-compatible dicts with ok/warnings/errors.
No printing, no Rich, no Typer dependency.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from projmap.config import ProjmapConfig, init_projmap, load_config
from projmap.scanner import scan_files
from projmap.chunker import chunk_text
from projmap.extractor import AnthropicExtractor
from projmap.schemas import (
    ExtractionResult,
    RebuildStats,
    edge_id,
    file_hash,
    node_id,
    normalize_content,
)
from projmap.storage.cache import FileHashCache
from projmap.storage.duckdb_store import DuckDBStore


def _ok(**kwargs) -> dict:
    result = {"ok": True, "warnings": [], "errors": []}
    result.update(kwargs)
    return result


def _err(error_code: str, message: str, **kwargs) -> dict:
    result = {"ok": False, "error_code": error_code, "message": message,
              "warnings": [], "errors": []}
    result.update(kwargs)
    return result


def _path_str(p: Path) -> str:
    return str(p)


def init_project(
    project_root: str = ".",
    force: bool = False,
    strict_evidence: bool = True,
    install_skill: bool = False,
) -> dict:
    """Initialize .projmap directory, config, and DuckDB."""
    root = Path(project_root).resolve()
    proj_dir = root / ".projmap"
    config_path = proj_dir / "config.toml"

    if proj_dir.exists() and config_path.exists() and not force:
        cfg = load_config(project_root)
        result = _ok(
            project_root=str(root),
            config_path=".projmap/config.toml",
            database_path=cfg.database_path,
            extraction_mode=cfg.extraction_mode,
            strict_evidence=cfg.strict_evidence,
            created=False,
        )
    else:
        try:
            init_projmap(project_root, strict_evidence=strict_evidence)
            cfg = load_config(project_root)
            result = _ok(
                project_root=str(root),
                config_path=".projmap/config.toml",
                database_path=cfg.database_path,
                extraction_mode=cfg.extraction_mode,
                strict_evidence=cfg.strict_evidence,
                created=True,
            )
        except Exception as exc:
            return _err("CONFIG_LOAD_FAILED", str(exc))

    if install_skill:
        skill_result = install_skill_fn(project_root)
        result["skill_installed"] = skill_result["ok"]
        if skill_result["ok"]:
            result["skill_path"] = skill_result.get("skill_path", "")
            if skill_result.get("warnings"):
                result["warnings"].extend(skill_result["warnings"])

    return result


def scan_project(project_root: str = ".") -> dict:
    """Scan project files and return status without calling LLM."""
    try:
        cfg = load_config(project_root)
    except FileNotFoundError:
        return _err("NOT_INITIALIZED", "No .projmap/config.toml found. Run `projmap init` first.")

    try:
        store = DuckDBStore(cfg.db_path)
        known = {**store.get_all_file_hashes()}
        store.close()
    except Exception as exc:
        return _err("DATABASE_ERROR", str(exc))

    try:
        records = scan_files(cfg, known)
    except Exception as exc:
        return _err("SCAN_FAILED", str(exc))

    files = []
    for r in records:
        files.append({
            "path": r.path,
            "file_type": r.file_type,
            "status": r.status,
            "content_hash": r.content_hash,
            "size_bytes": r.size_bytes,
            "is_virtual": r.is_virtual,
        })

    return _ok(
        project_root=str(Path(project_root).resolve()),
        scanned_files=len(records),
        new_files=sum(1 for f in files if f["status"] == "new"),
        changed_files=sum(1 for f in files if f["status"] == "changed"),
        unchanged_files=sum(1 for f in files if f["status"] == "unchanged"),
        files=files,
    )


def rebuild_project(
    project_root: str = ".",
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """Incremental rebuild: extract nodes/edges from changed files."""
    try:
        cfg = load_config(project_root)
    except FileNotFoundError:
        return _err("NOT_INITIALIZED", "No .projmap/config.toml found. Run `projmap init` first.")

    try:
        store = DuckDBStore(cfg.db_path)
    except Exception as exc:
        return _err("DATABASE_ERROR", str(exc))

    cache = FileHashCache(Path(cfg.root) / cfg.cache_dir)
    known = {**store.get_all_file_hashes(), **cache.as_dict()}

    records = scan_files(cfg, known)

    if force:
        for r in records:
            if r.status == "unchanged":
                r.status = "changed"
        records_changed = records
    else:
        records_changed = [r for r in records if r.status in ("new", "changed")]

    stats = RebuildStats(
        scanned_files=len(records),
        new_files=sum(1 for r in records if r.status == "new"),
        changed_files=sum(1 for r in records if r.status == "changed"),
        unchanged_files=sum(1 for r in records if r.status == "unchanged"),
    )

    if dry_run:
        store.close()
        return _ok(
            project_root=str(Path(project_root).resolve()),
            dry_run=True,
            force=force,
            **stats.model_dump(),
            files_to_process=[{"path": r.path, "status": r.status} for r in records_changed],
        )

    if not records_changed:
        store.close()
        cache.save()
        return _ok(
            project_root=str(Path(project_root).resolve()),
            dry_run=False,
            force=force,
            **stats.model_dump(),
        )

    # Check API key
    extractor = AnthropicExtractor(
        model=cfg.llm_model,
        api_key_env=cfg.api_key_env,
        temperature=cfg.temperature,
    )
    try:
        _ = extractor.api_key
    except SystemExit as exc:
        store.close()
        return _err("MISSING_API_KEY", str(exc))

    start = time.time()

    for frec in records_changed:
        # Delete old data for this file
        store.delete_chunks_for_file(frec.path)
        store.delete_nodes_for_file(frec.path)
        store.delete_edges_for_file(frec.path)

        # Chunk
        chunks = chunk_text(
            frec.content, frec.path,
            max_chars=cfg.max_chars,
            overlap_chars=cfg.overlap_chars,
        )
        stats.chunks_created += len(chunks)

        for chunk in chunks:
            store.insert_chunk(
                chunk.id, chunk.file_path, chunk.chunk_index,
                chunk.heading_path, chunk.semantic_anchor,
                chunk.content, chunk.content_hash,
                chunk.start_line, chunk.end_line,
            )

            # Extract
            try:
                result = extractor.extract(chunk)
            except Exception as exc:
                ext_id = str(uuid.uuid4())
                store.insert_extraction(
                    ext_id, chunk.id, frec.path, cfg.llm_model,
                    None, None, "api_error", str(exc),
                )
                stats.extractions_failed += 1
                continue

            raw = result.model_dump_json()

            # Validate
            try:
                ExtractionResult.model_validate_json(raw)
            except Exception as exc:
                ext_id = str(uuid.uuid4())
                store.insert_extraction(
                    ext_id, chunk.id, frec.path, cfg.llm_model,
                    raw, None, "validation_failed", str(exc),
                )
                stats.extractions_failed += 1
                continue

            # Insert nodes
            node_lookup: dict[str, str] = {}
            for n in result.nodes:
                nid = node_id(n.type, n.content)
                norm = normalize_content(n.content)
                node_lookup[norm] = nid
                inserted = store.insert_node(
                    nid, n.type, n.content, n.detail or "",
                    frec.path, chunk.id, n.source_line,
                    n.evidence_quote, n.confidence,
                    file_hash(n.content),
                )
                if inserted:
                    stats.nodes_inserted += 1
                else:
                    stats.nodes_skipped_duplicate += 1

            # Insert edges
            for edge in result.edges:
                from_nid = _resolve_edge_node(edge.from_content, node_lookup)
                to_nid = _resolve_edge_node(edge.to_content, node_lookup)
                if not from_nid or not to_nid:
                    stats.edges_dropped_unresolved += 1
                    continue
                eid = edge_id(from_nid, to_nid, edge.relationship)
                store.insert_edge(
                    eid, from_nid, to_nid, edge.relationship,
                    edge.evidence_quote, edge.confidence,
                    frec.path, chunk.id,
                )
                stats.edges_inserted += 1

            ext_id = str(uuid.uuid4())
            store.insert_extraction(
                ext_id, chunk.id, frec.path, cfg.llm_model,
                raw, raw, "success", None,
            )
            stats.extractions_succeeded += 1

        # Update file record
        store.upsert_file(
            frec.path, frec.file_type, frec.content_hash,
            frec.size_bytes, frec.modified_at, frec.status,
            extracted=True,
        )
        cache.set(frec.path, frec.content_hash)

    cache.save()
    stats.duration_seconds = round(time.time() - start, 2)
    store.close()

    return _ok(
        project_root=str(Path(project_root).resolve()),
        dry_run=False,
        force=force,
        **stats.model_dump(),
    )


def _resolve_edge_node(content: str, chunk_lookup: dict[str, str]) -> str | None:
    norm = normalize_content(content)
    return chunk_lookup.get(norm)


def get_status(project_root: str = ".") -> dict:
    """Return current projMap graph status."""
    try:
        cfg = load_config(project_root)
    except FileNotFoundError:
        return _err("NOT_INITIALIZED", "No .projmap/config.toml found. Run `projmap init` first.")

    try:
        store = DuckDBStore(cfg.db_path)
        counts = store.counts()
        node_types = store.node_type_counts()
        last_rb = store.last_rebuild()
        store.close()
    except Exception as exc:
        return _err("DATABASE_ERROR", str(exc))

    return _ok(
        project=cfg.project_name,
        project_root=str(Path(project_root).resolve()),
        database_path=cfg.database_path,
        files_tracked=counts.get("files", 0),
        chunks=counts.get("chunks", 0),
        nodes=counts.get("nodes", 0),
        edges=counts.get("edges", 0),
        extractions=counts.get("extractions", 0),
        node_types=node_types,
        last_rebuild=last_rb,
    )


def get_context(task: str, project_root: str = ".", limit: int = 20) -> dict:
    """Phase 2 placeholder."""
    return {
        "ok": False,
        "status": "not_implemented",
        "message": "projmap context will be implemented in Phase 2",
        "warnings": [],
        "errors": [],
    }


# ── External Extraction Mode ───────────────────────────────────

TASK_DIR = "extraction_tasks"
RESULT_DIR = "extraction_results"
SCHEMA_VERSION = "external_extraction_v1"

NODE_TYPES = ["decision", "risk", "assumption", "version", "constraint",
             "config", "evaluation_result", "process_rule", "open_question"]
EDGE_TYPES = ["depends-on", "conflicts-with", "supersedes", "traces-back-to",
              "mitigates", "implements", "affects", "supports", "limits"]

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


# ── Skill Installation ─────────────────────────────────────────

SKILL_MD = r'''---
name: projmap-memory
description: Use this skill when the user asks to update, rebuild, refresh, inspect, query, or view projMap project memory. Supports extraction, querying decisions, and AI context output.
---

# projMap Memory Skill

## When to use

### Update mode (extraction):
- 更新 projMap 记忆
- 运行 projMap 外部重建
- 刷新项目记忆图谱
- 更新项目记忆
- refresh projMap memory
- run projmap external rebuild
- update project memory graph

### Query mode (view decisions):
- 看一下 decision
- 有哪些决策
- 查看项目记忆
- 列出 decisions
- show me decisions
- list decisions
- what are the constraints
- show project memory
- projMap context
- projMap query
- projMap doctor

## Mode detection

If the user wants to VIEW/QUERY decisions or memory: follow the Query Workflow.
If the user wants to UPDATE/REFRESH memory: follow the Update Workflow.

## Query Workflow

Use this when the user wants to see decisions, constraints, risks, or project memory.

### Step 1: Check initialization

```bash
projmap status --format json
```

If not initialized, stop and tell the user.

### Step 2: Run the appropriate command

**For viewing decisions:**

Try `projmap query "<search_term>"` first. If that command is not available, query DuckDB:

```bash
python3 -c "
import duckdb
con = duckdb.connect('.projmap/projmap.duckdb', read_only=True)
rows = con.execute('SELECT type, title, project, version, module, status, source_file FROM nodes WHERE is_default_visible = true ORDER BY sort_time DESC NULLS LAST LIMIT 100').fetchall()
print('| Type | Status | Title | Project | Version | Module | Source |')
print('|---|---|---|---|---|---|---|')
for r in rows:
    t = (r[1] or '')[:60].replace('|','/')
    print(f'| {r[0]} | {r[5] or \"unknown\"} | {t} | {r[2] or \"\"} | {r[3] or \"\"} | {r[4] or \"\"} | {r[6] or \"\"} |')
con.close()
"
```

Output is a markdown table. Show it directly to the user.

**For AI agent context (all constraints + decisions + configs):**

Try `projmap context` first. If not available, query DuckDB:

```bash
python3 -c "
import duckdb
con = duckdb.connect('.projmap/projmap.duckdb', read_only=True)
for ntype in ['constraint', 'decision', 'config', 'risk']:
    rows = con.execute(f\"SELECT title, source_file FROM nodes WHERE type='{ntype}' AND is_default_visible=true ORDER BY sort_time DESC LIMIT 20\").fetchall()
    if rows:
        print(f'\\n## {ntype.title()}s')
        print('| Title | Source |')
        print('|---|---|')
        for r in rows:
            print(f'| {(r[0] or \"(untitled)\")[:80]} | {r[1] or \"\"} |')
con.close()
"
```

**For coverage diagnostics:**

Try `projmap doctor` first. If not available, query DuckDB directly.

### Step 3: Output rules

1. Show the command output directly as a table.
2. Do NOT convert the table into a bullet list.

## Update Workflow

Use this when the user wants to update/refresh memory.

## User experience

Do not expose internal task files, manifests, result JSON, schemas, or implementation details unless there is an error.

The user only wants to know whether projMap memory was updated and the final graph counts.

## Output discipline

Do not narrate intermediate steps.
Do not print generated Python.
Do not show extraction JSON.
Do not show task content.
Do not show task manifests.
Do not show shell command details unless an error requires user action.

Only show the final summary after all commands complete.

If recovery is needed, perform it silently unless user action is required.

## Initialization rule

If `.projmap/` or `.projmap/config.toml` is missing, do not auto-init.

Stop and tell the user:

projMap is not initialized. Run `projmap init --install-skill` first.

## Safety rules

- Do not modify business code.
- Do not modify trading logic.
- Do not modify model code.
- Do not modify historical audit artifacts.
- Only write inside `.projmap/`.
- If a result file must be created, write it only under `.projmap/extraction_results/`.
- Do not edit source project documents unless the user explicitly asks.
- Default task limit is 10 unless the user specifies another number.

## Update Workflow Steps

1. Run:

```bash
projmap status --format json
```

2. If projMap is not initialized, stop and tell the user.

3. Run:

```bash
projmap scan --format json
```

4. Determine task limit:
   - If user specified a number, use that number.
   - Otherwise use `10`.

5. Run:

```bash
projmap prepare-extraction --limit <N> --format json
```

6. Read:

```
.projmap/extraction_tasks/task_manifest.json
```

7. For each task in the manifest:
   - Read the task file.
   - Extract only explicit project memory.
   - Generate the matching result file at `result_path`.

8. Each result file must follow the `external_extraction_v1` schema used by projMap.

9. Extraction rules:
   - Extract only facts explicitly supported by the task content.
   - Every node and edge must include `evidence_quote`.
   - `evidence_quote` must be copied exactly from the chunk.
   - Do not invent IDs.
   - If a chunk has no useful project memory, return empty arrays.
   - Each `content` must be a complete self-contained sentence including subject (project/system name). BAD: "K mapping". GOOD: "V13 uses K horizons of 3, 6, and 8 bars".
   - Keep `detail` under 500 characters.
   - For `decision` type nodes, also output `title`, `context`, `rationale`, `scope`, `status_hint`, `project_hint`, `version_hint`, `module_hint`.

10. Run:

```bash
projmap import-extraction --format json
```

`strict_evidence` is controlled by `.projmap/config.toml`.

11. Run:

```bash
projmap status --format json
```

## Update response format

Only report:

```
projMap memory updated.

scanned_files: <number>
tasks_created: <number>
results_imported: <number>
results_failed: <number>
nodes_inserted: <number>
edges_inserted: <number>

Current graph:
nodes: <number>
edges: <number>
node_types:
- decision: <number>
- risk: <number>
- assumption: <number>
- version: <number>
- constraint: <number>
```

If there is an error, report only:
- error_code
- short explanation
- next action
'''

DEFAULT_SKILL_PATH = ".agents/skills/projmap-memory/SKILL.md"


def install_skill_fn(
    project_root: str = ".",
    force: bool = False,
    print_only: bool = False,
    path: str | None = None,
) -> dict:
    """Install projMap Skill for Codex / Claude Code."""
    root = Path(project_root).resolve()
    skill_path = root / (path or DEFAULT_SKILL_PATH)

    if print_only:
        return _ok(
            content=SKILL_MD,
            skill_path=str(skill_path.relative_to(root)) if skill_path.is_relative_to(root) else str(skill_path),
            print_only=True,
            created=False,
        )

    if skill_path.exists() and not force:
        return _ok(
            skill_path=str(skill_path.relative_to(root)) if skill_path.is_relative_to(root) else str(skill_path),
            created=False,
            warnings=["Skill file already exists. Use --force to overwrite."],
        )

    try:
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(SKILL_MD)
    except Exception as exc:
        return _err("SKILL_INSTALL_FAILED", str(exc))

    rel = str(skill_path.relative_to(root)) if skill_path.is_relative_to(root) else str(skill_path)
    return _ok(
        skill_path=rel,
        created=True,
    )
