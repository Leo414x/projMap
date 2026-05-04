# projMap Report Layer 改动明细

生成时间: 2026-05-04

---

## 一、新建文件

### 1. `projmap/report/prompts.py`（新建，120 行）

LLM prompt 定义，用于驱动 report enrichment。

- `ENRICH_SYSTEM_PROMPT` — 通用节点 enrichment prompt，要求 LLM 输出 display_title、group、group_label、report_status、priority_score、summary
- `ENRICH_USER_PROMPT_TEMPLATE` — brief enrichment 的 user prompt 模板，传入节点 JSON
- `QUERY_ENRICH_SYSTEM_PROMPT` — query 搜索结果 enrichment prompt，额外输出 match_reason
- `QUERY_ENRICH_USER_PROMPT_TEMPLATE` — query enrichment 的 user prompt 模板
- `BRIEF_STATUS_PROMPT` — 让 LLM 生成项目整体 current_status 的 prompt

### 2. `projmap/report/llm_enricher.py`（新建，392 行）

LLM 调用核心模块，支持两种模式。

**API 模式：**
- `enrich_nodes_api()` — 调 Anthropic API 批量 enrichment
- `get_brief_status_api()` — 调 API 生成项目 current_status

**External 模式：**
- `prepare_brief_tasks()` — 生成 `.projmap/brief_tasks/` 任务文件，每 30 节点一个 batch
- `import_brief_results()` — 读取 `.projmap/brief_results/` 结果，缓存到 `.projmap/enrichment_cache.json`
- `load_cached_enrichments()` — 加载缓存

**统一入口：**
- `enrich_nodes()` — 先尝试 API → 再读缓存 → 无 enrichment 时返回空值

**运行时生成的文件（在目标项目目录下，不在 projmap 源码内）：**
- `{project}/.projmap/brief_tasks/manifest.json` — 任务清单
- `{project}/.projmap/brief_tasks/brief_task_NNNN.json` — 任务文件（含 system_prompt + user_prompt + node_ids）
- `{project}/.projmap/brief_results/brief_task_NNNN.result.json` — 用户填入的 LLM 结果
- `{project}/.projmap/enrichment_cache.json` — enrichment 缓存

---

## 二、删除文件

| 文件 | 原用途 | 删除原因 |
|---|---|---|
| `projmap/report/title_builder.py` | 硬编码关键词→标题映射（"NO_GO"→"Live deployment blocker"等） | 全部由 LLM 生成，不需要规则映射 |
| `projmap/report/priority.py` | 硬编码 type_weights / status_weights / keyword weights | 全部由 LLM priority_score 决定 |
| `projmap/report/status_resolver.py` | 硬编码 BLOCKED_KEYWORDS / FROZEN_KEYWORDS，STATUS_SEVERITY 权重 | 全部由 LLM report_status 决定 |

---

## 三、修改文件

### 1. `projmap/report/grouping.py`

**改动前：**
- `BUCKET_RULES` — 12 组硬编码关键词到 bucket 的映射（deployment_status / frozen_baseline / spec_governance 等）
- `BUCKET_LABELS` — 12 组硬编码 bucket 显示名
- `assign_semantic_bucket()` — 关键词匹配分组
- `group_nodes()` — 按 bucket 分组
- `group_by_type_fallback()` — 按 type 分组的 fallback

**改动后：**
- 删除全部 `BUCKET_RULES`、`BUCKET_LABELS`、`assign_semantic_bucket()`
- 删除 `group_by_type_fallback()`
- 只保留 `group_by_enrichment()` — 按 LLM 输出的 group/group_label 字段分组

### 2. `projmap/report/source_resolver.py`

**改动前：**
- 硬编码 V13/Trading System 路径规则
- 硬编码 `"v13_technical_spec"` → Trading System
- 硬编码 `"docs/v13"` → Trading System
- 硬编码 content 中 `"v13"` → Trading System
- 硬编码 `"CLAUDE_CODE_PROMPT.md"` → projMap

**改动后：**
- 删除全部领域特定路径规则
- `resolve_source_project()` 只返回 unknown，project/version 由节点自身元数据决定

### 3. `projmap/report/brief_builder.py`

**改动前：**
- 导入 title_builder / priority / status_resolver / grouping 的硬编码模块
- `enrich_node()` 有完整 fallback 路径（无 LLM 时用规则推断 title/status/priority）
- `_build_current_status_fallback()` — 硬编码 fallback
- `build_brief()` 使用 `STATUS_SEVERITY` 加权排序
- `build_brief()` 有 `group_by_type_fallback` 分支

**改动后：**
- 所有 enrichment 字段（display_title / report_status / priority_score / group / group_label / summary / match_reason）全部来自 LLM enrichment
- 删除 `_build_current_status_fallback()`
- 排序只用 `priority_score`（LLM 产出），不用 STATUS_SEVERITY
- 分组只用 `group_by_enrichment()`（LLM 产出）

### 4. `projmap/report/render_markdown.py`

**改动前：**
- `render_brief()` 引用 `BUCKET_LABELS`
- `render_brief()` 用 markdown table 格式输出 constraints/decisions/risks
- `render_query_results()` 有 `group_by_type_fallback` 分支
- `render_query_results()` 无 match_reason / summary 输出

**改动后：**
- 删除 `BUCKET_LABELS` 引用
- Constraints / Decisions / Risks 改为编号列表格式，每项带 summary
- `render_query_results()` 增加 `match_reason` 和 `summary` 输出
- 分组统一用 `group_by_enrichment()`

### 5. `projmap/cli.py`

**改动前 `query` 命令：**
- 直接输出 raw markdown table
- 无 LLM enrichment
- 有 `--include-hidden` 选项
- 引用 `build_row` / `build_table_viewmodel`

**改动后 `query` 命令：**
- 调 `enrich_nodes()` 获取 LLM enrichment
- 调 `render_query_results()` 输出 Best Matches → Related Groups → Detailed Matches
- 删除 `--include-hidden`
- 删除 `build_row` / `build_table_viewmodel` 引用

**改动前 `brief` 命令：**
- 无 LLM enrichment
- 直接 build + render

**改动后 `brief` 命令：**
- 调 `enrich_nodes()` 获取 LLM enrichment
- 调 `get_brief_status_api()` 获取 LLM 生成的 current_status
- 传入 enrichments 和 llm_status 到 `build_brief()`

**新增命令：**
- `projmap prepare-brief` — 生成 external LLM 任务文件
- `projmap import-brief` — 导入 external LLM 结果并缓存

### 6. `projmap/report/evidence_builder.py`

无改动（此文件原本就没有硬编码规则）。

### 7. `projmap/report/__init__.py`

无改动（空文件）。

---

## 四、数据库结构

无改动。Report layer 只读取 DuckDB 中的 nodes，不修改表结构。

---

## 五、运行时产物（在目标项目下，非 projmap 源码）

| 文件 | 产生命令 | 说明 |
|---|---|---|
| `.projmap/brief_tasks/manifest.json` | `projmap prepare-brief` | 任务清单 |
| `.projmap/brief_tasks/brief_task_NNNN.json` | `projmap prepare-brief` | LLM 输入任务 |
| `.projmap/brief_results/brief_task_NNNN.result.json` | 用户手动填入 | LLM 输出结果 |
| `.projmap/enrichment_cache.json` | `projmap import-brief` 或 API 自动缓存 | enrichment 缓存 |

---

## 六、未改动但已知存在硬编码的文件

以下文件在本次 report layer 改动范围之外，硬编码规则为改动前就存在：

| 文件 | 硬编码内容 | 说明 |
|---|---|---|
| `projmap/cli.py` `_infer_module_from_content()` | 关键词→module 映射（paper_shadow / training / evaluation 等 16 组） | `migrate` 命令内部函数，用于旧数据迁移 |
| `projmap/cli.py` `_infer_status_from_content()` | 关键词→status 映射（paper/shadow → paper_only 等） | `migrate` 命令内部函数 |
| `projmap/cli.py` migrate 命令内 | `"v13"` → Trading System, `"spy"` → Trading System 等项目推断 | `migrate` 命令内部逻辑 |

这些属于 `migrate` 命令（旧数据一次性迁移），不在 report layer 范围内。

---

## 七、最终文件清单

```
projmap/report/
├── __init__.py           # 空文件
├── prompts.py            # LLM prompt 定义（新建）
├── llm_enricher.py       # LLM 调用 + external prepare/import（新建）
├── brief_builder.py      # 节点组装 → brief 结构（重写）
├── render_markdown.py    # markdown 渲染（修改）
├── grouping.py           # 按 LLM group 分组（重写）
├── evidence_builder.py   # 证据格式化（未改）
└── source_resolver.py    # source_scope 判断（精简）
```

已删除：
- `title_builder.py`
- `priority.py`
- `status_resolver.py`
