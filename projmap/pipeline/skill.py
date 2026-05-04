from __future__ import annotations

from pathlib import Path


# ── Skill Installation ─────────────────────────────────────────

SKILL_MD = r'''---
name: projmap-memory
description: Use this skill when the user asks to update, rebuild, refresh, inspect, query, or view projMap project memory. Supports extraction, relation discovery, enrichment, section-aware brief, and AI context output.
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

### Step 1: Check initialization

```bash
projmap status --format json
```

If not initialized, stop and tell the user:
projMap is not initialized. Run `projmap init --install-skill` first.

### Step 2: Run the appropriate command

For viewing decisions: `projmap query "<search_term>"` or `projmap query --all`
For AI agent context: `projmap context`
For diagnostics: `projmap doctor`

If a CLI command is not available, tell the user to upgrade projMap.

### Step 3: Output rules

Show command output directly. Do NOT convert tables into bullet lists.

## Update Workflow

### Initialization rule

If `.projmap/` or `.projmap/config.toml` is missing, do not auto-init.
Stop and tell the user:
projMap is not initialized. Run `projmap init --install-skill` first.

### Steps

1. `projmap status --format json` - confirm initialized.
2. `projmap scan --format json` - discover changed files.
3. `projmap prepare-extraction --limit <N> --format json` - generate tasks + prompt.
   Default limit is 10 unless the user specifies another number.
4. Read `.projmap/extraction_tasks/prompt.md` - this is the extraction prompt.
5. Read `.projmap/extraction_tasks/schema.json` - this is the output schema.
6. Read `.projmap/extraction_tasks/examples.json` - these are quality examples.
7. Read `.projmap/extraction_tasks/task_manifest.json` - this is the task list.
8. For each task in the manifest:
   a. Read the task file at `task_path`.
   b. Follow the instructions in `prompt.md` exactly to extract project memory.
   c. Validate output against `schema.json`.
   d. Write the result JSON to `result_path`.
9. `projmap import-extraction --format json` - import results into graph.
10. `projmap prepare-relations --format json` - generate relation discovery tasks.
11. Read `.projmap/relation_tasks/prompt.md` - this is the relation prompt.
12. For each task in `.projmap/relation_tasks/manifest.json`:
    a. Read the task file.
    b. Follow the prompt to identify cross-node relationships.
    c. Write the result JSON to `result_path`.
13. `projmap import-relations --format json` - import relation edges.
14. `projmap prepare-brief --format json` - generate enrichment tasks.
15. Read `.projmap/brief_tasks/prompt.md` - this is the enrichment prompt.
16. For each task in `.projmap/brief_tasks/manifest.json`:
    a. Read the task file.
    b. Follow the prompt to enrich nodes.
    c. Write the result JSON to `result_path`.
17. `projmap import-brief --format json` - import enrichments.
18. `projmap prepare-brief-sections --format json` - generate section brief tasks.
19. Read `.projmap/brief_section_tasks/prompt.md` - this is the section prompt.
20. For each section (constraints, decisions, risks):
    a. Read the section data file.
    b. Follow the prompt to generate the section.
    c. Write result to `.projmap/brief_section_results/{section}.result.json`.
21. `projmap import-brief-sections --format json` - import section results.
22. `projmap status --format json` - report final state.

### Error handling

If a task extraction fails, skip it and continue with remaining tasks.
Report skipped tasks in the final summary.

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

## Safety rules

- Do not modify business code.
- Do not modify trading logic.
- Do not modify model code.
- Do not modify historical audit artifacts.
- Only write inside `.projmap/`.
- If a result file must be created, write it only under `.projmap/extraction_results/`, `.projmap/relation_results/`, or `.projmap/brief_section_results/`.
- Do not edit source project documents unless the user explicitly asks.

## Update response format

Only report:

```
projMap memory updated.

scanned_files: <number>
extraction_tasks: <number>
results_imported: <number>
results_failed: <number>
nodes_inserted: <number>
edges_inserted: <number>
relation_edges: <number>
sections_generated: <number>

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


from projmap.util import _ok, _err


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
