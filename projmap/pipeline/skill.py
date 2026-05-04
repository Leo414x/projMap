from __future__ import annotations

from pathlib import Path


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
