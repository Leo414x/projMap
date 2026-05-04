"""Stable internal API for CLI / agents / future MCP.

All functions return JSON-compatible dicts with ok/warnings/errors.
No printing, no Rich, no Typer dependency.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from projmap.config import ProjmapConfig, init_projmap, load_config
from projmap.ingestion.scanner import scan_files
from projmap.ingestion.chunker import chunk_text
from projmap.ingestion.extractor import AnthropicExtractor
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


from projmap.util import _ok, _err, resolve_edge_node


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
    file_node_lookups: dict[str, dict[str, str]] = {}

    try:
        store.begin()
        for frec in records_changed:
            # Delete old data for this file
            store.delete_chunks_for_file(frec.path)
            store.delete_nodes_for_file(frec.path)
            store.delete_edges_for_file(frec.path)

            file_node_lookups.pop(frec.path, None)

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

            if frec.path not in file_node_lookups:
                file_node_lookups[frec.path] = {}
            file_node_lookups[frec.path].update(node_lookup)

            # Insert edges — resolve against file-level lookup (cross-chunk)
            file_lookup = file_node_lookups[frec.path]
            for edge in result.edges:
                from_nid = resolve_edge_node(edge.from_content, file_lookup)
                to_nid = resolve_edge_node(edge.to_content, file_lookup)
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

        store.commit()
    except Exception:
        store.rollback()
        cache.save()
        store.close()
        raise
    cache.save()
    stats.duration_seconds = round(time.time() - start, 2)
    store.close()

    return _ok(
        project_root=str(Path(project_root).resolve()),
        dry_run=False,
        force=force,
        **stats.model_dump(),
    )




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


# ── Re-exports from pipeline submodules ──────────────────────────
# Extraction and skill logic live in projmap.pipeline.* but are
# re-exported here so `from projmap import api` still works.

from projmap.pipeline.extraction import prepare_extraction, import_extraction  # noqa: E402
from projmap.pipeline.skill import install_skill_fn, SKILL_MD  # noqa: E402
