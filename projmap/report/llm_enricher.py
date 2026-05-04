"""LLM-driven report enrichment: titles, groups, status, priority.

Supports two modes:
1. API mode — call LLM directly (needs ANTHROPIC_API_KEY)
2. External mode — prepare-brief / import-brief (no key needed)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from projmap.report.prompts import (
    ENRICH_SYSTEM_PROMPT,
    ENRICH_USER_PROMPT_TEMPLATE,
    QUERY_ENRICH_SYSTEM_PROMPT,
    QUERY_ENRICH_USER_PROMPT_TEMPLATE,
    BRIEF_STATUS_PROMPT,
)

BRIEF_TASK_DIR = "brief_tasks"
BRIEF_RESULT_DIR = "brief_results"
BRIEF_SCHEMA_VERSION = "brief_enrichment_v1"


# ── Node serialization for LLM input ──────────────────────────────

def _serialize_nodes_for_llm(nodes: list[dict]) -> list[dict]:
    """Strip large/internal fields, keep only what the LLM needs."""
    out = []
    for n in nodes:
        out.append({
            "id": n.get("id", ""),
            "type": n.get("type", ""),
            "content": n.get("content", ""),
            "title": n.get("title", ""),
            "summary": n.get("summary", ""),
            "evidence_quote": n.get("evidence_quote", ""),
            "source_file": n.get("source_file", ""),
            "source_heading": n.get("source_heading") or n.get("source_line") or "",
            "status": n.get("status", ""),
            "module": n.get("module", ""),
            "project": n.get("project", ""),
            "version": n.get("version", ""),
        })
    return out


def _parse_enrichment_response(raw: str, node_ids: list[str]) -> list[dict]:
    """Parse LLM enrichment JSON into a list of enrichment dicts keyed by id."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines[1:] if not l.strip().startswith("```")]
        text = "\n".join(lines)

    parsed = json.loads(text)
    if isinstance(parsed, dict) and "enrichments" in parsed:
        parsed = parsed["enrichments"]
    if not isinstance(parsed, list):
        raise ValueError(f"Expected list, got {type(parsed).__name__}")

    # Build lookup by id
    by_id = {}
    for item in parsed:
        nid = item.get("id", "")
        by_id[nid] = {
            "display_title": item.get("display_title", ""),
            "group": item.get("group", "other"),
            "group_label": item.get("group_label", "Other"),
            "report_status": item.get("report_status", "active"),
            "priority_score": float(item.get("priority_score", 5.0)),
            "summary": item.get("summary", ""),
            "match_reason": item.get("match_reason", ""),
        }

    # Return in original order, filling gaps with defaults
    results = []
    for nid in node_ids:
        results.append(by_id.get(nid, _default_enrichment()))
    return results


def _default_enrichment() -> dict:
    """Empty enrichment — signals that LLM enrichment was not available."""
    return {
        "display_title": "",
        "group": "",
        "group_label": "",
        "report_status": "",
        "priority_score": 0.0,
        "summary": "",
        "match_reason": "",
    }


def _parse_status_response(raw: str) -> dict:
    """Parse LLM brief-status response."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines[1:] if not l.strip().startswith("```")]
        text = "\n".join(lines)
    parsed = json.loads(text)
    return {
        "current_status": parsed.get("current_status", "Status unknown"),
        "confidence": float(parsed.get("confidence", 0.5)),
    }


# ── API mode ──────────────────────────────────────────────────────

def enrich_nodes_api(
    nodes: list[dict],
    query: str | None = None,
    model: str = "claude-sonnet-4-20250514",
    api_key_env: str = "ANTHROPIC_API_KEY",
) -> list[dict]:
    """Call LLM API to enrich nodes. Returns list of enrichment dicts."""
    import anthropic

    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        raise SystemExit(f"Missing {api_key_env}. Set it with: export {api_key_env}=\"your-key\"")

    serialized = _serialize_nodes_for_llm(nodes)
    nodes_json = json.dumps(serialized, ensure_ascii=False, indent=2)
    node_ids = [n.get("id", "") for n in nodes]

    if query:
        system = QUERY_ENRICH_SYSTEM_PROMPT
        user = QUERY_ENRICH_USER_PROMPT_TEMPLATE.format(
            query=query, count=len(serialized), nodes_json=nodes_json,
        )
    else:
        system = ENRICH_SYSTEM_PROMPT
        user = ENRICH_USER_PROMPT_TEMPLATE.format(
            count=len(serialized), nodes_json=nodes_json,
        )

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=8192,
        temperature=0.0,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    raw = message.content[0].text
    return _parse_enrichment_response(raw, node_ids)


def get_brief_status_api(
    enriched_nodes: list[dict],
    model: str = "claude-sonnet-4-20250514",
    api_key_env: str = "ANTHROPIC_API_KEY",
) -> dict:
    """Call LLM API to generate current status summary."""
    import anthropic

    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        raise SystemExit(f"Missing {api_key_env}.")

    top_nodes = [
        {
            "display_title": n.get("display_title", ""),
            "report_status": n.get("report_status", ""),
            "summary": n.get("summary", ""),
            "type": n.get("type", ""),
        }
        for n in enriched_nodes[:20]
    ]
    top_json = json.dumps(top_nodes, ensure_ascii=False, indent=2)

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0.0,
        system="Return only valid JSON.",
        messages=[{"role": "user", "content": BRIEF_STATUS_PROMPT.format(top_nodes_json=top_json)}],
    )
    return _parse_status_response(message.content[0].text)


# ── External mode: prepare / import ───────────────────────────────

def prepare_brief_tasks(
    project_root: str = ".",
    clear: bool = True,
) -> dict:
    """Write enrichment task files for external LLM processing."""
    from projmap.config import load_config
    from projmap.storage.duckdb_store import DuckDBStore

    cfg = load_config(project_root)
    root = Path(cfg.root).resolve()
    task_dir = root / ".projmap" / BRIEF_TASK_DIR
    result_dir = root / ".projmap" / BRIEF_RESULT_DIR

    if clear:
        if task_dir.exists():
            for f in task_dir.iterdir():
                f.unlink()
        if result_dir.exists():
            for f in result_dir.iterdir():
                f.unlink()

    task_dir.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)

    store = DuckDBStore(cfg.db_path)
    nodes = store.get_all_nodes_as_dicts()
    store.close()

    # Split into batches of ~30 nodes per task (context limit)
    batch_size = 30
    tasks = []
    for i in range(0, len(nodes), batch_size):
        batch = nodes[i:i + batch_size]
        task_num = len(tasks) + 1
        task_id = f"brief_task_{task_num:04d}"

        serialized = _serialize_nodes_for_llm(batch)
        node_ids = [n.get("id", "") for n in batch]

        task_data = {
            "schema_version": BRIEF_SCHEMA_VERSION,
            "task_id": task_id,
            "node_ids": node_ids,
            "system_prompt": ENRICH_SYSTEM_PROMPT,
            "user_prompt": ENRICH_USER_PROMPT_TEMPLATE.format(
                count=len(serialized),
                nodes_json=json.dumps(serialized, ensure_ascii=False, indent=2),
            ),
            "expected_result_count": len(serialized),
        }

        (task_dir / f"{task_id}.json").write_text(
            json.dumps(task_data, ensure_ascii=False, indent=2)
        )
        tasks.append({
            "task_id": task_id,
            "task_path": f".projmap/{BRIEF_TASK_DIR}/{task_id}.json",
            "result_path": f".projmap/{BRIEF_RESULT_DIR}/{task_id}.result.json",
            "node_count": len(serialized),
        })

    # Write manifest
    manifest = {
        "schema_version": BRIEF_SCHEMA_VERSION,
        "project_name": cfg.project_name,
        "project_root": str(root),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "external_brief",
        "task_count": len(tasks),
        "total_nodes": len(nodes),
        "tasks": tasks,
    }
    manifest_path = task_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    return {
        "ok": True,
        "tasks_created": len(tasks),
        "total_nodes": len(nodes),
        "task_dir": f".projmap/{BRIEF_TASK_DIR}",
        "result_dir": f".projmap/{BRIEF_RESULT_DIR}",
        "manifest_path": f".projmap/{BRIEF_TASK_DIR}/manifest.json",
    }


def import_brief_results(project_root: str = ".") -> dict:
    """Read external LLM enrichment results and cache them."""
    from projmap.config import load_config

    cfg = load_config(project_root)
    root = Path(cfg.root).resolve()
    task_dir = root / ".projmap" / BRIEF_TASK_DIR
    result_dir = root / ".projmap" / BRIEF_RESULT_DIR
    manifest_path = task_dir / "manifest.json"

    if not manifest_path.exists():
        return {"ok": False, "error": f"No manifest at .projmap/{BRIEF_TASK_DIR}/manifest.json"}

    manifest = json.loads(manifest_path.read_text())
    enrichments = {}
    imported = 0
    failed = 0

    for task in manifest.get("tasks", []):
        tid = task["task_id"]
        result_path = result_dir / f"{tid}.result.json"
        if not result_path.exists():
            continue

        try:
            raw = json.loads(result_path.read_text())
            # Support both direct array and {"enrichments": [...]} formats
            items = raw if isinstance(raw, list) else raw.get("enrichments", raw.get("results", []))
            node_ids = task.get("node_ids", [])

            parsed = _parse_enrichment_response(
                json.dumps(items) if isinstance(items, list) else json.dumps(raw),
                node_ids,
            )

            for nid, enrich in zip(node_ids, parsed):
                enrichments[nid] = enrich

            imported += 1
        except Exception as e:
            failed += 1

    # Cache enrichments
    cache_path = root / ".projmap" / "enrichment_cache.json"
    cache_path.write_text(json.dumps(enrichments, ensure_ascii=False, indent=2))

    return {
        "ok": True,
        "tasks_imported": imported,
        "tasks_failed": failed,
        "enrichments_loaded": len(enrichments),
        "cache_path": f".projmap/enrichment_cache.json",
    }


def load_cached_enrichments(project_root: str = ".") -> dict[str, dict]:
    """Load previously cached enrichments. Returns {node_id: enrichment}."""
    from projmap.config import load_config

    cfg = load_config(project_root)
    cache_path = Path(cfg.root).resolve() / ".projmap" / "enrichment_cache.json"
    if not cache_path.exists():
        return {}

    return json.loads(cache_path.read_text())


# ── Unified enrichment entry point ────────────────────────────────

def enrich_nodes(
    nodes: list[dict],
    project_root: str = ".",
    query: str | None = None,
    model: str = "claude-sonnet-4-20250514",
    prefer_api: bool = True,
) -> tuple[list[dict], bool]:
    """Enrich nodes using API or cached external results.

    Returns (enrichments_list, used_api).
    enrichments_list is parallel to nodes list.
    """
    node_ids = [n.get("id", "") for n in nodes]

    # Try API first
    if prefer_api and os.environ.get("ANTHROPIC_API_KEY", "").strip():
        try:
            enrichments = enrich_nodes_api(nodes, query=query, model=model)
            # Cache the results
            try:
                from projmap.config import load_config
                cfg = load_config(project_root)
                cache_path = Path(cfg.root).resolve() / ".projmap" / "enrichment_cache.json"
                existing = {}
                if cache_path.exists():
                    existing = json.loads(cache_path.read_text())
                for nid, enrich in zip(node_ids, enrichments):
                    existing[nid] = enrich
                cache_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
            except Exception:
                pass
            return enrichments, True
        except Exception:
            pass

    # Fall back to cached external results
    cached = load_cached_enrichments(project_root)
    if cached:
        results = []
        for nid in node_ids:
            if nid in cached:
                results.append(cached[nid])
            else:
                results.append(_default_enrichment())
        return results, False

    # No enrichment available — return defaults
    return [_default_enrichment() for _ in nodes], False
