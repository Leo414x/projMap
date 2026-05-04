"""CLI wrapper: parses args, calls api.py, outputs text/json."""

from __future__ import annotations

import json
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from projmap import api

app = typer.Typer(name="projmap", help="Project memory and intelligence map")
console = Console()

FormatOption = Optional[str]


def _output_json(result: dict) -> None:
    import sys
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n")
    sys.stdout.flush()


def _exit_on_error(result: dict) -> None:
    if not result.get("ok"):
        raise typer.Exit(code=1)


# ── init ────────────────────────────────────────────────────────

@app.command()
def init(
    force: bool = typer.Option(False, "--force", help="Force re-initialize"),
    install_skill: Optional[bool] = typer.Option(
        None, "--install-skill/--no-install-skill",
        help="Install projMap Codex / Claude Code skill",
    ),
    strict_evidence: Optional[bool] = typer.Option(
        None, "--strict-evidence/--no-strict-evidence",
        help="Enable strict evidence validation",
    ),
    format: FormatOption = typer.Option(None, "--format", help="Output format: json"),
) -> None:
    """Initialize projMap in the current project."""
    # Resolve defaults for non-interactive / JSON mode
    _strict = strict_evidence if strict_evidence is not None else True
    _skill = install_skill if install_skill is not None else False

    result = api.init_project(
        ".", force=force,
        strict_evidence=_strict,
        install_skill=_skill,
    )

    if format == "json":
        _output_json(result)
        _exit_on_error(result)
        return

    if not result["ok"]:
        console.print(f"[bold red]Error:[/bold red] {result.get('message', 'Unknown error')}")
        raise typer.Exit(code=1)

    if result.get("created"):
        console.print("[bold green]projMap initialized.[/bold green]")
    else:
        console.print("[dim]projMap already initialized.[/dim]")
    console.print(f"Config:   [cyan].projmap/config.toml[/cyan]")
    console.print(f"Database: [cyan]{result.get('database_path', '.projmap/projmap.duckdb')}[/cyan]")

    se = result.get("strict_evidence", True)
    console.print(f"Evidence: [cyan]strict_evidence={se}[/cyan]")

    if result.get("skill_installed"):
        console.print(f"Skill:    [cyan]{result.get('skill_path', '')}[/cyan]")
        console.print()
        console.print("Next:")
        console.print("  Open Codex / Claude Code and say:")
        console.print('  "更新 projMap 记忆，处理前 10 个任务。"')
    else:
        console.print()
        console.print("[dim]To enable no-key Codex / Claude Code rebuild:[/dim]")
        console.print("[dim]  projmap install-skill[/dim]")


# ── scan ────────────────────────────────────────────────────────

@app.command()
def scan(
    format: FormatOption = typer.Option(None, "--format", help="Output format: json"),
) -> None:
    """Scan project files and show hash status."""
    result = api.scan_project(".")

    if format == "json":
        _output_json(result)
        _exit_on_error(result)
        return

    if not result["ok"]:
        console.print(f"[bold red]Error:[/bold red] {result.get('message', 'Unknown error')}")
        raise typer.Exit(code=1)

    table = Table(title="Scan Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("Files found", str(result["scanned_files"]))
    table.add_row("New", str(result["new_files"]), style="green")
    table.add_row("Changed", str(result["changed_files"]), style="yellow")
    table.add_row("Unchanged", str(result["unchanged_files"]), style="dim")
    console.print(table)

    files = result.get("files", [])
    if files:
        ftable = Table(title="Candidate files")
        ftable.add_column("File", style="cyan")
        ftable.add_column("Status", style="bold")
        ftable.add_column("Size", justify="right")
        for f in sorted(files, key=lambda x: x["path"]):
            s = f["status"]
            style = {"new": "green", "changed": "yellow", "unchanged": "dim"}[s]
            ftable.add_row(f["path"], f"[{style}]{s}[/{style}]", str(f["size_bytes"]))
        console.print(ftable)


# ── rebuild ─────────────────────────────────────────────────────

@app.command()
def rebuild(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be processed"),
    force: bool = typer.Option(False, "--force", help="Force rebuild all files"),
    format: FormatOption = typer.Option(None, "--format", help="Output format: json"),
) -> None:
    """Incremental rebuild: extract nodes/edges from changed files."""
    result = api.rebuild_project(".", dry_run=dry_run, force=force)

    if format == "json":
        _output_json(result)
        _exit_on_error(result)
        return

    if not result["ok"]:
        console.print(f"[bold red]Error:[/bold red] {result.get('message', 'Unknown error')}")
        raise typer.Exit(code=1)

    if result.get("dry_run"):
        console.print("[bold]Dry run - files to process:[/bold]")
        for f in result.get("files_to_process", []):
            console.print(f"  {f['path']} ({f['status']})")
        return

    # Text summary
    table = Table(title="Rebuild Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Scanned files", str(result.get("scanned_files", 0)))
    table.add_row("New files", str(result.get("new_files", 0)), style="green")
    table.add_row("Changed files", str(result.get("changed_files", 0)), style="yellow")
    table.add_row("Unchanged files", str(result.get("unchanged_files", 0)), style="dim")
    table.add_row("Chunks created", str(result.get("chunks_created", 0)))
    table.add_row("Extractions succeeded", str(result.get("extractions_succeeded", 0)), style="green")
    table.add_row("Extractions failed", str(result.get("extractions_failed", 0)), style="red")
    table.add_row("Nodes inserted", str(result.get("nodes_inserted", 0)), style="green")
    table.add_row("Nodes skipped (duplicate)", str(result.get("nodes_skipped_duplicate", 0)), style="dim")
    table.add_row("Edges inserted", str(result.get("edges_inserted", 0)), style="green")
    table.add_row("Edges dropped (unresolved)", str(result.get("edges_dropped_unresolved", 0)), style="yellow")
    table.add_row("Duration", f"{result.get('duration_seconds', 0)}s")
    console.print(table)


# ── status ──────────────────────────────────────────────────────

@app.command()
def status(
    format: FormatOption = typer.Option(None, "--format", help="Output format: json"),
) -> None:
    """Show current graph status."""
    result = api.get_status(".")

    if format == "json":
        _output_json(result)
        _exit_on_error(result)
        return

    if not result["ok"]:
        console.print(f"[bold red]Error:[/bold red] {result.get('message', 'Unknown error')}")
        raise typer.Exit(code=1)

    console.print("[bold]projMap Status[/bold]")
    console.print(f"Project: [cyan]{result.get('project', 'unknown')}[/cyan]")
    console.print(f"Database: [cyan]{result.get('database_path', '')}[/cyan]")
    console.print()
    console.print(f"  Files tracked:  {result.get('files_tracked', 0)}")
    console.print(f"  Chunks:         {result.get('chunks', 0)}")
    console.print(f"  Nodes:          {result.get('nodes', 0)}")
    console.print(f"  Edges:          {result.get('edges', 0)}")
    console.print(f"  Extractions:    {result.get('extractions', 0)}")

    node_types = result.get("node_types", {})
    if node_types:
        console.print()
        console.print("[bold]Node types:[/bold]")
        for ntype, count in node_types.items():
            console.print(f"  - {ntype}: {count}")

    last_rb = result.get("last_rebuild")
    if last_rb:
        console.print()
        console.print(f"[dim]Last rebuild: {last_rb}[/dim]")

# ── prepare-extraction ──────────────────────────────────────────

@app.command("prepare-extraction")
def prepare_extraction(
    force: bool = typer.Option(False, "--force", help="Force for all candidate files"),
    limit: int | None = typer.Option(None, "--limit", help="Limit number of tasks"),
    clear: bool = typer.Option(True, "--clear/--no-clear", help="Clear old tasks before generating"),
    format: FormatOption = typer.Option(None, "--format", help="Output format: json"),
) -> None:
    """Prepare extraction tasks for external LLM (no API key needed)."""
    result = api.prepare_extraction(".", force=force, limit=limit, clear=clear)

    if format == "json":
        _output_json(result)
        _exit_on_error(result)
        return

    if not result["ok"]:
        console.print(f"[bold red]Error:[/bold red] {result.get('message', 'Unknown error')}")
        raise typer.Exit(code=1)

    console.print(f"[bold green]Prepared {result['tasks_created']} extraction tasks.[/bold green]")
    console.print(f"Task dir:    [cyan]{result['task_dir']}[/cyan]")
    console.print(f"Result dir:  [cyan]{result['result_dir']}[/cyan]")
    console.print(f"Manifest:    [cyan]{result['manifest_path']}[/cyan]")
    console.print(f"Scanned:     {result['scanned_files']} files "
                  f"({result['new_files']} new, {result['changed_files']} changed)")


# ── import-extraction ───────────────────────────────────────────

@app.command("import-extraction")
def import_extraction_cmd(
    strict_evidence: Optional[bool] = typer.Option(
        None, "--strict-evidence/--no-strict-evidence",
        help="Override project config strict evidence setting",
    ),
    allow_partial: bool = typer.Option(True, "--allow-partial/--no-allow-partial",
                                       help="Continue on partial failures"),
    min_confidence: float = typer.Option(0.55, "--min-confidence",
                                          help="Minimum confidence threshold"),
    format: FormatOption = typer.Option(None, "--format", help="Output format: json"),
) -> None:
    """Import extraction results from external LLM."""
    result = api.import_extraction(
        ".", strict_evidence=strict_evidence,
        allow_partial=allow_partial, min_confidence=min_confidence,
    )

    if format == "json":
        _output_json(result)
        _exit_on_error(result)
        return

    if not result["ok"]:
        console.print(f"[bold red]Error:[/bold red] {result.get('message', 'Unknown error')}")
        raise typer.Exit(code=1)

    table = Table(title="Import Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Tasks total", str(result.get("tasks_total", 0)))
    table.add_row("Results found", str(result.get("result_files_found", 0)))
    table.add_row("Imported", str(result.get("results_imported", 0)), style="green")
    table.add_row("Failed", str(result.get("results_failed", 0)), style="red")
    table.add_row("Nodes inserted", str(result.get("nodes_inserted", 0)), style="green")
    table.add_row("Nodes skipped (dup)", str(result.get("nodes_skipped_duplicate", 0)), style="dim")
    table.add_row("Nodes skipped (low conf)", str(result.get("nodes_skipped_low_confidence", 0)), style="dim")
    table.add_row("Edges inserted", str(result.get("edges_inserted", 0)), style="green")
    table.add_row("Edges dropped (unresolved)", str(result.get("edges_dropped_unresolved", 0)), style="yellow")
    table.add_row("Edges skipped (low conf)", str(result.get("edges_skipped_low_confidence", 0)), style="dim")
    table.add_row("Evidence failures", str(result.get("evidence_failures", 0)), style="yellow")
    console.print(table)

    for w in result.get("warnings", []):
        console.print(f"[yellow]Warning:[/yellow] {w}")


if __name__ == "__main__":
    app()


# ── install-skill ───────────────────────────────────────────────

@app.command("install-skill")
def install_skill(
    force: bool = typer.Option(False, "--force", help="Force overwrite existing skill"),
    print_output: bool = typer.Option(False, "--print", help="Print skill content without writing"),
    path: Optional[str] = typer.Option(None, "--path", help="Custom skill file path"),
    format: FormatOption = typer.Option(None, "--format", help="Output format: json"),
) -> None:
    """Install projMap Skill for Codex / Claude Code."""
    result = api.install_skill_fn(
        ".", force=force, print_only=print_output, path=path,
    )

    if format == "json":
        _output_json(result)
        _exit_on_error(result)
        return

    if not result["ok"]:
        console.print(f"[bold red]Error:[/bold red] {result.get('message', 'Unknown error')}")
        raise typer.Exit(code=1)

    if print_output:
        console.print(result.get("content", ""))
        return

    if result.get("created"):
        console.print(f"[bold green]Skill installed:[/bold green] [cyan]{result['skill_path']}[/cyan]")
    else:
        console.print(f"[dim]Skill already exists:[/dim] [cyan]{result.get('skill_path', '')}[/cyan]")
        for w in result.get("warnings", []):
            console.print(f"[yellow]{w}[/yellow]")


# ── query ───────────────────────────────────────────────────────

@app.command()
def query(
    search: str = typer.Argument("", help="Search query"),
    format: FormatOption = typer.Option(None, "--format", help="Output format: json"),
) -> None:
    """Query project memory — search results with grouped evidence."""
    from projmap.config import load_config
    from projmap.storage.duckdb_store import DuckDBStore
    from projmap.report.render_markdown import render_query_results
    from projmap.report.llm_enricher import enrich_nodes

    try:
        cfg = load_config(".")
    except FileNotFoundError:
        console.print("[bold red]Error:[/bold red] Not initialized. Run `projmap init` first.")
        raise typer.Exit(code=1)

    store = DuckDBStore(cfg.db_path)
    nodes = store.get_all_nodes_as_dicts()
    edge_counts_map = store.get_edge_counts_by_node()
    store.close()

    if search:
        filtered = []
        for n in nodes:
            searchable = f"{n.get('title', '')} {n.get('summary', '')} {n.get('content', '')} {n.get('module', '')} {n.get('project', '')} {n.get('evidence_quote', '')}".lower()
            if search.lower() in searchable:
                filtered.append(n)
        nodes = filtered

    if format == "json":
        _output_json({"ok": True, "query": search, "matched": len(nodes)})
        return

    enrichments_list, _ = enrich_nodes(nodes, project_root=".", query=search)
    enrichments = {n.get("id", ""): e for n, e in zip(nodes, enrichments_list)}

    output = render_query_results(nodes, search, edge_counts_map, enrichments=enrichments)
    console.print(output)


# ── brief ───────────────────────────────────────────────────────

@app.command()
def brief(
    format: FormatOption = typer.Option(None, "--format", help="Output format: json"),
) -> None:
    """Show project brief — current status, constraints, decisions, risks."""
    from projmap.config import load_config
    from projmap.storage.duckdb_store import DuckDBStore
    from projmap.report.brief_builder import build_brief
    from projmap.report.render_markdown import render_brief
    from projmap.report.llm_enricher import enrich_nodes, get_brief_status_api

    try:
        cfg = load_config(".")
    except FileNotFoundError:
        console.print("[bold red]Error:[/bold red] Not initialized. Run `projmap init` first.")
        raise typer.Exit(code=1)

    store = DuckDBStore(cfg.db_path)
    nodes = store.get_all_nodes_as_dicts()
    edge_counts_map = store.get_edge_counts_by_node()
    store.close()

    enrichments_list, used_api = enrich_nodes(nodes, project_root=".")
    enrichments_dict = {n.get("id", ""): e for n, e in zip(nodes, enrichments_list)}

    llm_status = None
    if used_api:
        try:
            enriched_for_status = [{**n, **e} for n, e in zip(nodes, enrichments_list)]
            llm_status = get_brief_status_api(enriched_for_status)
        except Exception:
            pass

    result = build_brief(
        nodes, edge_counts_map,
        project_hint=cfg.project_name,
        enrichments=enrichments_dict,
        llm_status=llm_status,
    )

    if format == "json":
        _output_json({"ok": True, "stats": result["stats"]})
        return

    output = render_brief(result)
    console.print(output)


# ── prepare-brief ───────────────────────────────────────────────

@app.command("prepare-brief")
def prepare_brief(
    format: FormatOption = typer.Option(None, "--format", help="Output format: json"),
) -> None:
    """Prepare enrichment task files for external LLM processing."""
    from projmap.report.llm_enricher import prepare_brief_tasks

    result = prepare_brief_tasks(".")

    if format == "json":
        _output_json(result)
        return

    if not result.get("ok"):
        console.print(f"[bold red]Error:[/bold red] {result.get('error', 'Unknown')}")
        raise typer.Exit(code=1)

    console.print(f"[bold green]Prepared {result['tasks_created']} enrichment tasks.[/bold green]")
    console.print(f"Total nodes:  {result['total_nodes']}")
    console.print(f"Task dir:     [cyan]{result['task_dir']}[/cyan]")
    console.print(f"Result dir:   [cyan]{result['result_dir']}[/cyan]")
    console.print(f"Manifest:     [cyan]{result['manifest_path']}[/cyan]")


# ── import-brief ────────────────────────────────────────────────

@app.command("import-brief")
def import_brief(
    format: FormatOption = typer.Option(None, "--format", help="Output format: json"),
) -> None:
    """Import enrichment results from external LLM."""
    from projmap.report.llm_enricher import import_brief_results

    result = import_brief_results(".")

    if format == "json":
        _output_json(result)
        return

    if not result.get("ok"):
        console.print(f"[bold red]Error:[/bold red] {result.get('error', 'Unknown')}")
        raise typer.Exit(code=1)

    console.print(f"[bold green]Imported {result['tasks_imported']} tasks.[/bold green]")
    console.print(f"Enrichments loaded: {result['enrichments_loaded']}")
    console.print(f"Failed: {result['tasks_failed']}", style="yellow" if result['tasks_failed'] else "dim")
    console.print(f"Cache: [cyan]{result['cache_path']}[/cyan]")


# ── context ─────────────────────────────────────────────────────

@app.command("context")
def context_cmd(
    format: FormatOption = typer.Option(None, "--format", help="Output format: json"),
) -> None:
    """Output AI context summary for coding agents."""
    from projmap.config import load_config
    from projmap.storage.duckdb_store import DuckDBStore
    from projmap.viewmodel import build_row

    try:
        cfg = load_config(".")
    except FileNotFoundError:
        console.print("[bold red]Error:[/bold red] Not initialized. Run `projmap init` first.")
        raise typer.Exit(code=1)

    store = DuckDBStore(cfg.db_path)
    nodes = store.get_all_nodes_as_dicts()
    edge_counts_map = store.get_edge_counts_by_node()

    rows = []
    for n in nodes:
        sources = store.get_sources_for_node(n["id"])
        source = sources[0] if sources else None
        edge_counts = edge_counts_map.get(n["id"], {})
        row = build_row(n, source, edge_counts)
        rows.append(row)
    store.close()

    visible = [r for r in rows if r.is_default_visible]

    if format == "json":
        _output_json({"ok": True, "rows": len(visible)})
        return

    # Constraint section
    constraints = [r for r in visible if r.type == "constraint"]
    decisions = [r for r in visible if r.type == "decision"]
    configs = [r for r in visible if r.type == "config"]
    evals = [r for r in visible if r.type == "evaluation_result"]
    hidden = [r for r in rows if not r.is_default_visible]

    sections = []

    if constraints:
        lines = ["| Rule | Reason | Source |", "|---|---|---|"]
        for c in constraints[:20]:
            reason = c.rationale_short or c.context_short or "-"
            lines.append(f"| {c.title} | {reason} | {c.source_label} |")
        sections.append(("Do Not Violate", "\n".join(lines)))

    if decisions:
        lines = ["| Time | Project / Version | Module | Decision | Status | Source |", "|---|---|---|---|---|---|"]
        for d in decisions[:30]:
            lines.append(f"| {d.time_display} | {d.project_version_label} | {d.module_label} | {d.title} | {d.status_label} | {d.source_label} |")
        sections.append(("Active Decisions", "\n".join(lines)))

    if configs:
        lines = ["| Module | Config | Status | Source |", "|---|---|---|---|"]
        for c in configs[:15]:
            lines.append(f"| {c.module_label} | {c.title} | {c.status_label} | {c.source_label} |")
        sections.append(("Current Configs", "\n".join(lines)))

    if evals:
        lines = ["| Module | Result | Source |", "|---|---|---|"]
        for e in evals[:15]:
            lines.append(f"| {e.module_label} | {e.title} | {e.source_label} |")
        sections.append(("Evaluation Results", "\n".join(lines)))

    supersedes = [r for r in hidden if r.hidden_reason and "superseded" in (r.hidden_reason or "")]
    if supersedes:
        lines = ["| Item | Source |", "|---|---|"]
        for s in supersedes[:10]:
            lines.append(f"| {s.title} | {s.source_label} |")
        sections.append(("Superseded / Deprecated", "\n".join(lines)))

    console.print("[bold]projMap Context[/bold]\n")
    for title, body in sections:
        console.print(f"[bold]{title}[/bold]")
        console.print(body)
        console.print()


# ── doctor ──────────────────────────────────────────────────────

@app.command()
def doctor(
    format: FormatOption = typer.Option(None, "--format", help="Output format: json"),
) -> None:
    """Run coverage diagnostics."""
    from projmap.config import load_config
    from projmap.storage.duckdb_store import DuckDBStore
    from projmap.viewmodel import build_row

    try:
        cfg = load_config(".")
    except FileNotFoundError:
        console.print("[bold red]Error:[/bold red] Not initialized. Run `projmap init` first.")
        raise typer.Exit(code=1)

    store = DuckDBStore(cfg.db_path)
    nodes = store.get_all_nodes_as_dicts()
    edge_counts_map = store.get_edge_counts_by_node()

    rows = []
    for n in nodes:
        sources = store.get_sources_for_node(n["id"])
        source = sources[0] if sources else None
        edge_counts = edge_counts_map.get(n["id"], {})
        row = build_row(n, source, edge_counts)
        rows.append(row)
    store.close()

    total = len(rows)
    with_source = sum(1 for r in rows if r.source_file)
    with_evidence = sum(1 for r in rows if r.evidence_quote)
    high_time = sum(1 for r in rows if r.time_confidence >= 0.65)
    low_time = sum(1 for r in rows if r.time_confidence < 0.5)
    missing_rationale = sum(1 for r in rows if not r.rationale_short)
    unknown_module = sum(1 for r in rows if r.module == "unknown")
    hidden = sum(1 for r in rows if not r.is_default_visible)

    report = {
        "total_nodes": total,
        "with_source": with_source,
        "source_pct": round(with_source / max(total, 1) * 100, 1),
        "with_evidence": with_evidence,
        "evidence_pct": round(with_evidence / max(total, 1) * 100, 1),
        "high_time_confidence": high_time,
        "low_time_confidence": low_time,
        "missing_rationale": missing_rationale,
        "unknown_module": unknown_module,
        "hidden": hidden,
    }

    if format == "json":
        _output_json({"ok": True, **report})
        return

    console.print("[bold]projMap Doctor — Coverage[/bold]\n")
    table = Table(title="Coverage")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Total nodes", str(total))
    table.add_row("With source", f"{with_source} ({report['source_pct']}%)", style="green")
    table.add_row("With evidence", f"{with_evidence} ({report['evidence_pct']}%)", style="green")
    table.add_row("High time confidence", str(high_time), style="green")
    table.add_row("Low time confidence", str(low_time), style="yellow")
    table.add_row("Missing rationale", str(missing_rationale), style="red")
    table.add_row("Unknown module", str(unknown_module), style="yellow")
    table.add_row("Hidden by default", str(hidden), style="dim")
    console.print(table)


# ── migrate ─────────────────────────────────────────────────────

@app.command()
def migrate(
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Dry run by default"),
    format: FormatOption = typer.Option(None, "--format", help="Output format: json"),
) -> None:
    """Migrate legacy nodes to v5 schema with project/version/module inference."""
    from projmap.config import load_config
    from projmap.storage.duckdb_store import DuckDBStore
    from projmap.resolvers import (
        normalize_module, infer_module_from_path, infer_module_from_heading,
        resolve_project, resolve_version, resolve_classification,
        compute_display_priority, resolve_visibility,
    )

    try:
        cfg = load_config(".")
    except FileNotFoundError:
        console.print("[bold red]Error:[/bold red] Not initialized. Run `projmap init` first.")
        raise typer.Exit(code=1)

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
        # Clean evidence: take first meaningful line
        ev_clean = evidence.strip().split("\n")[0].strip().rstrip(".,;:") if evidence else ""

        if existing_title and len(existing_title) > 40:
            # Already has a good long title
            title = existing_title
        elif len(ev_clean) > 30 and ev_clean[0].isupper():
            # Evidence is a reasonable sentence
            title = ev_clean
        elif content and len(content) > len(ev_clean):
            # Content label is better than evidence fragment
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
        import re
        # Match V13 even inside filenames like v13_model_card.md (underscore is \w)
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

        # Infer status from content
        status = _infer_status_from_content(content)

        # Time: use extraction/first_seen timestamps, mark as Observed
        ts = now_utc()
        ts_str = str(ts)

        # Visibility
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

    result = {
        "ok": True,
        "dry_run": dry_run,
        "nodes_scanned": len(nodes),
        "already_v5": already_v5,
        "can_migrate": migrated,
        "missing_source": missing_source,
        "missing_evidence": missing_evidence,
    }

    if format == "json":
        _output_json(result)
        return

    label = "Dry Run" if dry_run else "Executed"
    console.print(f"[bold]Legacy Migration — {label}[/bold]\n")
    console.print(f"  Nodes scanned:     {len(nodes)}")
    console.print(f"  Already v5:        {already_v5}")
    console.print(f"  Can migrate:       {migrated}")
    console.print(f"  Missing source:    {missing_source}", style="yellow")
    console.print(f"  Missing evidence:  {missing_evidence}", style="yellow")
    if dry_run:
        console.print("\n[dim]Run with --execute to apply migration.[/dim]")


def now_utc():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def _infer_module_from_content(content: str) -> str | None:
    """Infer module hint from content keywords."""
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
    """Infer status from content keywords."""
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
