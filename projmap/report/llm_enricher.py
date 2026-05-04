"""LLM-driven report enrichment: titles, groups, status, priority.

Supports two modes:
1. API mode — call LLM directly (needs ANTHROPIC_API_KEY)
2. External mode — prepare-brief / import-brief (no key needed)
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from projmap.config import load_config
from projmap.prompts import load as load_prompt, split_prompt_sections

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

    results = []
    for nid in node_ids:
        results.append(by_id.get(nid, _default_enrichment()))
    return results


def _default_enrichment() -> dict:
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


# ── Semantic batching ────────────────────────────────────────────

def _semantic_batch(nodes: list[dict], batch_size: int = 30) -> list[list[dict]]:
    """Batch nodes by type + project + module for semantic coherence."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for n in nodes:
        key = f"{n.get('type', '')}|{n.get('project', '')}|{n.get('module', '')}"
        groups[key].append(n)

    batches: list[list[dict]] = []
    current: list[dict] = []
    for group in sorted(groups.values(), key=len, reverse=True):
        group.sort(key=lambda n: n.get("version", "") or "")
        for node in group:
            current.append(node)
            if len(current) >= batch_size:
                batches.append(current)
                current = []
    if current:
        batches.append(current)
    return batches


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

    purpose = "enrichment_query" if query else "enrichment"
    pack = load_prompt(purpose=purpose)
    system, user_template = split_prompt_sections(pack.prompt_text)

    fmt_kwargs = {"count": len(serialized), "nodes_json": nodes_json}
    if query:
        fmt_kwargs["query"] = query
    user = user_template.format(**fmt_kwargs)

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

    pack = load_prompt(purpose="brief_status")
    system, user_template = split_prompt_sections(pack.prompt_text)

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
    user = user_template.format(sections_json=top_json)

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0.0,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return _parse_status_response(message.content[0].text)


# ── External mode: prepare / import ───────────────────────────────

def prepare_brief_tasks(
    project_root: str = ".",
    clear: bool = True,
) -> dict:
    """Write enrichment task files for external LLM processing."""
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

    # Write prompt from registry
    prompt_pack = load_prompt(purpose="enrichment")
    (task_dir / "prompt.md").write_text(prompt_pack.prompt_text, encoding="utf-8")

    # Semantic batching instead of index-order
    batches = _semantic_batch(nodes, batch_size=30)
    tasks = []
    for batch in batches:
        task_num = len(tasks) + 1
        task_id = f"brief_task_{task_num:04d}"

        serialized = _serialize_nodes_for_llm(batch)
        node_ids = [n.get("id", "") for n in batch]

        task_data = {
            "schema_version": BRIEF_SCHEMA_VERSION,
            "task_id": task_id,
            "node_ids": node_ids,
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

    manifest = {
        "schema_version": BRIEF_SCHEMA_VERSION,
        "prompt_version": prompt_pack.version,
        "prompt_path": f".projmap/{BRIEF_TASK_DIR}/prompt.md",
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
            items = raw if isinstance(raw, list) else raw.get("enrichments", raw.get("results", []))
            node_ids = task.get("node_ids", [])

            parsed = _parse_enrichment_response(
                json.dumps(items) if isinstance(items, list) else json.dumps(raw),
                node_ids,
            )

            for nid, enrich in zip(node_ids, parsed):
                enrichments[nid] = enrich

            imported += 1
        except Exception:
            failed += 1

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

    if prefer_api and os.environ.get("ANTHROPIC_API_KEY", "").strip():
        try:
            enrichments = enrich_nodes_api(nodes, query=query, model=model)
            try:
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

    cached = load_cached_enrichments(project_root)
    if cached:
        results = []
        for nid in node_ids:
            if nid in cached:
                results.append(cached[nid])
            else:
                results.append(_default_enrichment())
        return results, False

    return [_default_enrichment() for _ in nodes], False


# ── Section-aware brief generation ────────────────────────────────

BRIEF_SECTION_TASK_DIR = "brief_section_tasks"
BRIEF_SECTION_RESULT_DIR = "brief_section_results"
BRIEF_SECTION_SCHEMA_VERSION = "brief_section_v1"

SECTION_DEFINITIONS = {
    "constraints": {
        "node_type": "constraint",
        "edge_types": ["depends-on", "mitigates", "conflicts-with"],
        "description": "Project constraints — things that must be true or must not be violated.",
    },
    "decisions": {
        "node_type": "decision",
        "edge_types": ["supersedes", "depends-on", "implements"],
        "description": "Project decisions — choices made, including supersession chains.",
    },
    "risks": {
        "node_type": "risk",
        "edge_types": ["mitigates", "depends-on"],
        "description": "Project risks — threats and their mitigation status.",
    },
}


def _parse_section_response(raw: str) -> dict:
    """Parse a brief section LLM response."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines[1:] if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return json.loads(text)


def generate_brief_sections_api(
    project_root: str = ".",
    model: str = "claude-sonnet-4-20250514",
    api_key_env: str = "ANTHROPIC_API_KEY",
) -> dict:
    """Generate brief sections by querying DuckDB per section with full graph context."""
    import anthropic

    try:
        cfg = load_config(project_root)
    except FileNotFoundError:
        return {"ok": False, "error": "Not initialized"}

    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        return {"ok": False, "error": f"Missing {api_key_env}"}

    store = DuckDBStore(cfg.db_path)
    client = anthropic.Anthropic(api_key=api_key)

    section_pack = load_prompt(purpose="brief_section")
    section_system, section_user_tmpl = split_prompt_sections(section_pack.prompt_text)

    status_pack = load_prompt(purpose="brief_status")
    status_system, status_user_tmpl = split_prompt_sections(status_pack.prompt_text)

    sections = {}
    for section_name, section_def in SECTION_DEFINITIONS.items():
        node_edges = store.query_nodes_with_edges(
            node_type=section_def["node_type"],
            include_edge_types=section_def["edge_types"],
        )
        if not node_edges:
            sections[section_name] = {"section_summary": "No data available.", "items": []}
            continue

        section_data_json = json.dumps(node_edges, ensure_ascii=False, indent=2)
        user = section_user_tmpl.format(
            section_name=section_name,
            section_description=section_def["description"],
            section_data_json=section_data_json,
        )

        try:
            message = client.messages.create(
                model=model, max_tokens=4096, temperature=0.0,
                system=section_system,
                messages=[{"role": "user", "content": user}],
            )
            sections[section_name] = _parse_section_response(message.content[0].text)
        except Exception as exc:
            sections[section_name] = {"section_summary": f"Error: {exc}", "items": []}

    # Overall status from section summaries
    summaries = {
        name: data.get("section_summary", "")
        for name, data in sections.items()
    }
    sections_json = json.dumps(summaries, ensure_ascii=False, indent=2)
    status_user = status_user_tmpl.format(sections_json=sections_json)

    try:
        message = client.messages.create(
            model=model, max_tokens=1024, temperature=0.0,
            system=status_system,
            messages=[{"role": "user", "content": status_user}],
        )
        overall_status = _parse_status_response(message.content[0].text)
    except Exception:
        overall_status = {"current_status": "Status unavailable", "confidence": 0.0}

    store.close()

    # Cache results
    root = Path(cfg.root).resolve()
    cache_path = root / ".projmap" / "brief_sections_cache.json"
    cache_data = {"sections": sections, "current_status": overall_status}
    cache_path.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2))

    return {"ok": True, "sections": sections, "current_status": overall_status}


def prepare_brief_section_tasks(project_root: str = ".") -> dict:
    """Write section task files for external LLM."""
    from projmap.storage.duckdb_store import DuckDBStore

    try:
        cfg = load_config(project_root)
    except FileNotFoundError:
        return {"ok": False, "error": "Not initialized"}

    root = Path(cfg.root).resolve()
    task_dir = root / ".projmap" / BRIEF_SECTION_TASK_DIR
    result_dir = root / ".projmap" / BRIEF_SECTION_RESULT_DIR

    if task_dir.exists():
        for f in task_dir.iterdir():
            f.unlink()
    if result_dir.exists():
        for f in result_dir.iterdir():
            f.unlink()

    task_dir.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)

    store = DuckDBStore(cfg.db_path)

    # Write prompts from registry
    section_pack = load_prompt(purpose="brief_section")
    (task_dir / "prompt.md").write_text(section_pack.prompt_text, encoding="utf-8")

    status_pack = load_prompt(purpose="brief_status")
    (task_dir / "status_prompt.md").write_text(status_pack.prompt_text, encoding="utf-8")

    tasks = []
    for section_name, section_def in SECTION_DEFINITIONS.items():
        node_edges = store.query_nodes_with_edges(
            node_type=section_def["node_type"],
            include_edge_types=section_def["edge_types"],
        )
        section_data = {
            "section_name": section_name,
            "section_description": section_def["description"],
            "data": node_edges,
        }
        (task_dir / f"{section_name}.json").write_text(
            json.dumps(section_data, ensure_ascii=False, indent=2)
        )
        tasks.append({
            "section_name": section_name,
            "data_path": f".projmap/{BRIEF_SECTION_TASK_DIR}/{section_name}.json",
            "result_path": f".projmap/{BRIEF_SECTION_RESULT_DIR}/{section_name}.result.json",
        })

    store.close()

    manifest = {
        "schema_version": BRIEF_SECTION_SCHEMA_VERSION,
        "project_name": cfg.project_name,
        "project_root": str(root),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "external_brief_sections",
        "tasks": tasks,
    }
    (task_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2)
    )

    return {
        "ok": True,
        "sections_prepared": len(tasks),
        "task_dir": f".projmap/{BRIEF_SECTION_TASK_DIR}",
        "result_dir": f".projmap/{BRIEF_SECTION_RESULT_DIR}",
    }


def import_brief_section_results(project_root: str = ".") -> dict:
    """Read section results from external LLM and cache."""
    try:
        cfg = load_config(project_root)
    except FileNotFoundError:
        return {"ok": False, "error": "Not initialized"}

    root = Path(cfg.root).resolve()
    manifest_path = root / ".projmap" / BRIEF_SECTION_TASK_DIR / "manifest.json"
    result_dir = root / ".projmap" / BRIEF_SECTION_RESULT_DIR

    if not manifest_path.exists():
        return {"ok": False, "error": "No manifest found"}

    manifest = json.loads(manifest_path.read_text())
    sections = {}
    imported = 0
    failed = 0

    for task in manifest.get("tasks", []):
        section_name = task["section_name"]
        result_path = result_dir / f"{section_name}.result.json"
        if not result_path.exists():
            sections[section_name] = {"section_summary": "No result", "items": []}
            failed += 1
            continue
        try:
            data = json.loads(result_path.read_text())
            sections[section_name] = data
            imported += 1
        except Exception:
            sections[section_name] = {"section_summary": "Parse error", "items": []}
            failed += 1

    # Read overall status result if present
    status_result_path = result_dir / "status.result.json"
    current_status = {"current_status": "Unknown", "confidence": 0.0}
    if status_result_path.exists():
        try:
            current_status = _parse_status_response(status_result_path.read_text())
        except Exception:
            pass

    cache_path = root / ".projmap" / "brief_sections_cache.json"
    cache_data = {"sections": sections, "current_status": current_status}
    cache_path.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2))

    return {
        "ok": True,
        "sections_imported": imported,
        "sections_failed": failed,
        "cache_path": ".projmap/brief_sections_cache.json",
    }


def load_cached_brief_sections(project_root: str = ".") -> dict | None:
    """Load cached brief sections. Returns None if no cache exists."""
    try:
        cfg = load_config(project_root)
    except FileNotFoundError:
        return None
    cache_path = Path(cfg.root).resolve() / ".projmap" / "brief_sections_cache.json"
    if not cache_path.exists():
        return None
    return json.loads(cache_path.read_text())
